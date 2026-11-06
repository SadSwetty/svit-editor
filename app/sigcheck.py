"""
Svit Editor — перевірка цифрового підпису оновлень (Ed25519, RFC 8032), чистий Python без залежностей.

Кожен реліз містить у .app/Contents/Resources файли manifest.json (sha256 усіх файлів пакета)
і manifest.sig (підпис маніфесту приватним ключем автора). Програма знає лише ПУБЛІЧНИЙ ключ
і встановлює оновлення тільки якщо підпис правильний і кожен файл збігається з маніфестом.
"""
import hashlib
import json
from pathlib import Path

# публічний ключ автора релізів (hex). Приватний ключ зберігається окремо і ніколи не потрапляє в програму.
PUBLIC_KEY_HEX = "74dd62baf66c29333727086b8c89dd4f0b38d92ebfe9a7b1f7aadb152c7c24b8"

# ---------------------------------------------------------------- Ed25519 (RFC 8032, еталонна реалізація)
_p = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_d = -121665 * pow(121666, _p - 2, _p) % _p
_I = pow(2, (_p - 1) // 4, _p)


def _sha512(m):
    return hashlib.sha512(m).digest()


def _inv(x):
    return pow(x, _p - 2, _p)


def _recover_x(y, sign):
    if y >= _p:
        return None
    x2 = (y * y - 1) * _inv(_d * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_p + 3) // 8, _p)
    if (x * x - x2) % _p != 0:
        x = x * _I % _p
    if (x * x - x2) % _p != 0:
        return None
    if (x & 1) != sign:
        x = _p - x
    return x


_gy = 4 * _inv(5) % _p
_G = (_recover_x(_gy, 0), _gy, 1, _recover_x(_gy, 0) * _gy % _p)


def _add(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % _p
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % _p
    C = 2 * P[3] * Q[3] * _d % _p
    D = 2 * P[2] * Q[2] % _p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _p, G * H % _p, F * G % _p, E * H % _p)


def _mul(s, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _equal(P, Q):
    return (P[0] * Q[2] - Q[0] * P[2]) % _p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % _p == 0


def _compress(P):
    zinv = _inv(P[2])
    x, y = P[0] * zinv % _p, P[1] * zinv % _p
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _p)


def _secret_expand(secret):
    h = _sha512(secret)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(secret):
    a, _ = _secret_expand(secret)
    return _compress(_mul(a, _G))


def sign(secret, msg):
    a, prefix = _secret_expand(secret)
    A = _compress(_mul(a, _G))
    r = int.from_bytes(_sha512(prefix + msg), "little") % _L
    R = _compress(_mul(r, _G))
    h = int.from_bytes(_sha512(R + A + msg), "little") % _L
    s = (r + h * a) % _L
    return R + int.to_bytes(s, 32, "little")


def verify(public, msg, signature):
    if len(public) != 32 or len(signature) != 64:
        return False
    A = _decompress(public)
    if not A:
        return False
    Rs = signature[:32]
    R = _decompress(Rs)
    if not R:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    h = int.from_bytes(_sha512(Rs + public + msg), "little") % _L
    return _equal(_mul(s, _G), _add(R, _mul(h, A)))


# ---------------------------------------------------------------- маніфест пакета
SKIP = {"manifest.json", "manifest.sig"}


def file_hashes(app_dir):
    """sha256 кожного файлу всередині .app (шляхи відносно .app, без самого маніфесту)."""
    app_dir = Path(app_dir)
    out = {}
    for f in sorted(app_dir.rglob("*")):
        if f.is_symlink():
            out[str(f.relative_to(app_dir))] = "symlink"
            continue
        if f.is_file() and f.name not in SKIP:
            out[str(f.relative_to(app_dir))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def make_manifest(app_dir, version, secret):
    app_dir = Path(app_dir)
    res = app_dir / "Contents" / "Resources"
    man = {"version": version, "files": file_hashes(app_dir)}
    data = json.dumps(man, sort_keys=True, ensure_ascii=False, indent=1).encode("utf-8")
    (res / "manifest.json").write_bytes(data)
    (res / "manifest.sig").write_text(sign(secret, data).hex())


def check_app(app_dir, expect_version=None):
    """Перевіряє розпакований .app. Повертає (True, '') або (False, причина)."""
    app_dir = Path(app_dir)
    res = app_dir / "Contents" / "Resources"
    if PUBLIC_KEY_HEX.startswith("__"):
        return False, "у цій збірці немає ключа перевірки"
    try:
        data = (res / "manifest.json").read_bytes()
        sig = bytes.fromhex((res / "manifest.sig").read_text().strip())
    except Exception:
        return False, "оновлення не підписане"
    if not verify(bytes.fromhex(PUBLIC_KEY_HEX), data, sig):
        return False, "підпис оновлення неправильний"
    man = json.loads(data.decode("utf-8"))
    if expect_version and str(man.get("version")) != str(expect_version):
        return False, "версія в підписі не збігається"
    actual = file_hashes(app_dir)
    if actual != man.get("files"):
        extra = sorted(set(actual) - set(man.get("files", {})))[:3]
        changed = sorted(k for k in actual if k in man.get("files", {}) and actual[k] != man["files"][k])[:3]
        return False, "файли оновлення змінені (%s)" % ", ".join(extra + changed or ["бракує файлів"])
    return True, ""
