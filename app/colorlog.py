"""
Svit Editor — один лог для всього матеріалу.
Визначаємо, в якому профілі знято кожне відео (Sony пише це в сам файл MP4: CaptureGammaEquation /
CaptureColorPrimaries), і для тих, що не в обраному лозі, робимо LUT-перетворення в цей лог.
Відео, які вже в обраному лозі, не чіпаємо.
"""
import re
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------- цілі
TARGETS = {
    "slog3_sg3": {"gamma": "slog3", "gamut": "sg3", "label": "S-Log3 / S-Gamut3"},
    "slog3_sg3c": {"gamma": "slog3", "gamut": "sg3c", "label": "S-Log3 / S-Gamut3.Cine"},
    "hlg_2020": {"gamma": "hlg", "gamut": "2020", "label": "HLG3 / BT.2020"},
}
GAMMA_LABEL = {"rec709": "Rec.709", "slog3": "S-Log3", "slog2": "S-Log2", "hlg": "HLG"}
GAMUT_LABEL = {"709": "Rec.709", "2020": "BT.2020", "sg3": "S-Gamut3", "sg3c": "S-Gamut3.Cine", "sg": "S-Gamut"}

# ---------------------------------------------------------------- як визначаємо профіль

_RX_GAMMA = re.compile(rb'CaptureGammaEquation"\s+value="([^"]+)"')
_RX_PRIM = re.compile(rb'CaptureColorPrimaries"\s+value="([^"]+)"')


def _map_gamma(v):
    v = (v or "").lower()
    if "s-log3" in v or "slog3" in v:
        return "slog3"
    if "s-log2" in v or "slog2" in v:
        return "slog2"
    if "hlg" in v or "2100" in v or "b67" in v:
        return "hlg"
    if v:
        return "rec709"        # rec709, rec709-xvycc, s-cinetone, cine1…4, still — «звичайний» (не лог)
    return None


def _map_gamut(v):
    v = (v or "").lower().replace("_", "-")
    if "gamut3-cine" in v or "gamut3cine" in v or "gamut3.cine" in v:
        return "sg3c"
    if "gamut3" in v:
        return "sg3"
    if "s-gamut" in v or "sgamut" in v:
        return "sg"
    if "2020" in v:
        return "2020"
    if "709" in v:
        return "709"
    return None


def _read_xml(path):
    p = Path(path)
    blobs = []
    for side in (p.with_name(p.stem + "M01.XML"), p.with_name(p.stem + "M01.xml"), p.with_suffix(".XML"),
                 p.with_suffix(".xml")):
        try:
            if side.exists() and side.stat().st_size < 2_000_000:
                blobs.append(side.read_bytes())
        except Exception:
            pass
    try:
        size = p.stat().st_size
        with open(p, "rb") as f:
            blobs.append(f.read(4_000_000))                    # XML у Sony MP4 — у коробці meta
            if size > 4_000_000:
                f.seek(max(0, size - 12_000_000))
                blobs.append(f.read())
    except Exception:
        pass
    for b in blobs:
        g = _RX_GAMMA.search(b)
        if g:
            pr = _RX_PRIM.search(b)
            return g.group(1).decode("latin-1"), (pr.group(1).decode("latin-1") if pr else "")
    return None, None


def _read_tags(path):
    """Запасний шлях: теги кольору в самому відеопотоці (HLG тут видно завжди)."""
    try:
        import av
        c = av.open(str(path))
        try:
            vs = c.streams.video[0]
            cc = vs.codec_context
            trc = getattr(cc, "color_trc", None)
            prim = getattr(cc, "color_primaries", None)
            trc, prim = int(trc) if trc is not None else None, int(prim) if prim is not None else None
        finally:
            c.close()
    except Exception:
        return None, None
    gamma = "hlg" if trc == 18 else None
    gamut = "2020" if prim == 9 else ("709" if prim == 1 else None)
    return gamma, gamut


def detect(path):
    """→ {"gamma": rec709|slog3|slog2|hlg|None, "gamut": …|None, "how": meta|tags|None, "raw": "…"}"""
    g, pr = _read_xml(path)
    if g:
        gamma, gamut = _map_gamma(g), _map_gamut(pr)
        if gamma == "rec709" and not gamut:
            gamut = "709"
        if gamma == "hlg" and not gamut:
            gamut = "2020"
        return {"gamma": gamma, "gamut": gamut, "how": "meta", "raw": f"{g} / {pr}".strip(" /")}
    gamma, gamut = _read_tags(path)
    if gamma:
        return {"gamma": gamma, "gamut": gamut or "2020", "how": "tags", "raw": "HLG (теги відео)"}
    return {"gamma": None, "gamut": None, "how": None, "raw": ""}


def label(prof):
    if not prof or not prof.get("gamma"):
        return "невідомо"
    return GAMMA_LABEL.get(prof["gamma"], prof["gamma"]) + (
        " / " + GAMUT_LABEL.get(prof["gamut"], prof["gamut"]) if prof.get("gamut") else "")


def plan_for(prof, target):
    """Що робити з джерелом: same — уже в цьому лозі, convert — перетворити, skip — не вмію/не знаю."""
    t = TARGETS[target]
    g, gm = prof.get("gamma"), prof.get("gamut")
    if not g:
        return "unknown"
    if g == t["gamma"]:
        return "same"         # уже в цьому лозі (навіть з іншим гамутом) — лог-файли не чіпаємо
    if g in ("rec709", "slog3", "hlg"):
        return "convert"
    return "skip"            # S-Log2 тощо — не чіпаємо


# ---------------------------------------------------------------- математика кольору

_PRIM = {
    "709": ((0.640, 0.330), (0.300, 0.600), (0.150, 0.060)),
    "2020": ((0.708, 0.292), (0.170, 0.797), (0.131, 0.046)),
    "sg3": ((0.730, 0.280), (0.140, 0.855), (0.100, -0.050)),
    "sg": ((0.730, 0.280), (0.140, 0.855), (0.100, -0.050)),
    "sg3c": ((0.766, 0.275), (0.225, 0.800), (0.089, -0.087)),
}
_D65 = (0.3127, 0.3290)


def _rgb2xyz(gamut):
    prim = _PRIM[gamut]
    m = np.array([[x / y, 1.0, (1 - x - y) / y] for x, y in prim]).T
    wx, wy = _D65
    w = np.array([wx / wy, 1.0, (1 - wx - wy) / wy])
    s = np.linalg.solve(m, w)
    return m * s


def gamut_matrix(src, dst):
    return np.linalg.inv(_rgb2xyz(dst)) @ _rgb2xyz(src)


HLG_WHITE = 0.265        # 100% білого Rec.709 = 75% сигналу HLG (рекомендація BT.2408)
_A, _B, _C = 0.17883277, 0.28466892, 0.55991073


def slog3_encode(x):
    x = np.asarray(x, np.float64)
    hi = (420.0 + np.log10(np.maximum(x, 0.01125) + 0.01) * 261.5 - np.log10(0.19) * 261.5) / 1023.0
    lo = (x * (171.2102946929 - 95.0) / 0.01125 + 95.0) / 1023.0
    return np.where(x >= 0.01125, hi, lo)


def slog3_decode(y):
    y = np.asarray(y, np.float64)
    hi = 10 ** ((y * 1023.0 - 420.0) / 261.5) * 0.19 - 0.01
    lo = (y * 1023.0 - 95.0) * 0.01125 / (171.2102946929 - 95.0)
    return np.where(y >= 171.2102946929 / 1023.0, hi, lo)


def rec709_decode(v):
    v = np.asarray(v, np.float64)
    return np.where(v < 0.081, v / 4.5, ((np.maximum(v, 0.081) + 0.099) / 1.099) ** (1 / 0.45))


def hlg_encode(e):
    e = np.clip(np.asarray(e, np.float64), 0, 1)
    return np.where(e <= 1 / 12, np.sqrt(3 * e), _A * np.log(np.maximum(12 * e - _B, 1e-9)) + _C)


def hlg_decode(v):
    v = np.clip(np.asarray(v, np.float64), 0, 1)
    return np.where(v <= 0.5, v * v / 3, (np.exp((v - _C) / _A) + _B) / 12)


def _to_linear(rgb, gamma):
    """Код → сцена (лінійно, 0.18 = середній сірий, 1.0 = білий Rec.709)."""
    if gamma == "rec709":
        return rec709_decode(rgb)
    if gamma == "slog3":
        return slog3_decode(rgb)
    if gamma == "hlg":
        return hlg_decode(rgb) / HLG_WHITE
    raise ValueError(gamma)


def _from_linear(lin, gamma):
    if gamma == "slog3":
        return slog3_encode(lin)
    if gamma == "hlg":
        return hlg_encode(lin * HLG_WHITE)
    raise ValueError(gamma)


def convert(rgb, src_gamma, src_gamut, target):
    """rgb (…, 3) у профілі джерела → коди обраного логу."""
    t = TARGETS[target]
    lin = _to_linear(rgb, src_gamma)
    m = gamut_matrix(src_gamut or ("2020" if src_gamma == "hlg" else "709" if src_gamma == "rec709" else "sg3c"),
                     t["gamut"])
    lin = lin @ m.T
    return np.clip(_from_linear(lin, t["gamma"]), 0.0, 1.0)


def write_cube(path, src_gamma, src_gamut, target, size=33):
    n = size
    ax = np.linspace(0.0, 1.0, n)
    b, g, r = np.meshgrid(ax, ax, ax, indexing="ij")          # у .cube найшвидше змінюється червоний
    rgb = np.stack([r, g, b], axis=-1).reshape(-1, 3)
    out = convert(rgb, src_gamma, src_gamut, target)
    title = f"Svit {GAMMA_LABEL.get(src_gamma, src_gamma)} to {TARGETS[target]['label']}"
    lines = [f'TITLE "{title}"', f"LUT_3D_SIZE {n}", "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1"]
    lines += ["%.6f %.6f %.6f" % tuple(px) for px in out]
    Path(path).write_text("\n".join(lines) + "\n", encoding="ascii")
    return path
