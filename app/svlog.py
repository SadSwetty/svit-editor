"""
Svit Editor — журнал роботи і звіти про збої.

Усе, що відбувається у вікні, пишеться в ~/.svit-editor/logs/ui_<час>.log.
DaVinci-частина пише свій журнал davinci_<час>.log у ту ж папку.
Коли щось ламається — збираємо звіт «Svit Editor звіт <час>.txt» з усіх журналів
і відкриваємо його в TextEdit, щоб його можна було одразу скопіювати й надіслати.
"""
import os
import platform
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

HOME = Path.home() / ".svit-editor"
LOG_DIR = HOME / "logs"
KEEP = 40                      # скільки останніх файлів журналу тримати

_lock = threading.Lock()
_file = None
path = None


class _Tee:
    """Дублює stdout/stderr у журнал."""
    def __init__(self, orig):
        self.orig = orig

    def write(self, s):
        try:
            if self.orig:
                self.orig.write(s)
        except Exception:
            pass
        _write_raw(s)

    def flush(self):
        try:
            if self.orig:
                self.orig.flush()
        except Exception:
            pass

    def isatty(self):
        return False


def _write_raw(s):
    if _file is None or not s:
        return
    with _lock:
        try:
            _file.write(s)
            _file.flush()
        except Exception:
            pass


def _prune():
    try:
        files = sorted(LOG_DIR.glob("*"), key=lambda p: p.stat().st_mtime)
        for p in files[:-KEEP]:
            p.unlink()
    except Exception:
        pass


def setup(version="?"):
    global _file, path
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _prune()
    path = LOG_DIR / ("ui_%s.log" % time.strftime("%Y%m%d_%H%M%S"))
    _file = open(str(path), "a", encoding="utf-8")
    sys.stdout = _Tee(sys.__stdout__)
    sys.stderr = _Tee(sys.__stderr__)

    def hook(et, ev, tb):
        log("НЕОБРОБЛЕНА ПОМИЛКА:\n" + "".join(traceback.format_exception(et, ev, tb)))
        try:
            sys.__excepthook__(et, ev, tb)
        except Exception:
            pass
    sys.excepthook = hook
    if hasattr(threading, "excepthook"):
        threading.excepthook = lambda a: hook(a.exc_type, a.exc_value, a.exc_traceback)
    log("Svit Editor %s · macOS %s · %s · Python %s" % (version, platform.mac_ver()[0] or platform.platform(),
                                                         platform.machine(), sys.version.split()[0]))
    return path


def log(msg):
    _write_raw("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))


def _tail(p, n=400):
    try:
        lines = Path(p).read_text(encoding="utf-8", errors="ignore").splitlines()
        return "\n".join(lines[-n:])
    except Exception as e:
        return "(не вдалося прочитати: %s)" % e


def latest(prefix):
    try:
        files = sorted(LOG_DIR.glob(prefix + "_*.log"), key=lambda p: p.stat().st_mtime)
        return files[-1] if files else None
    except Exception:
        return None


def report(title, error="", details="", extra=None, open_it=True):
    """Збирає звіт про збій у текстовий файл і відкриває його. Повертає шлях."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    rp = LOG_DIR / ("Svit Editor звіт %s.txt" % time.strftime("%Y-%m-%d %H-%M-%S"))
    parts = ["SVIT EDITOR — ЗВІТ ПРО ЗБІЙ",
             "Скопіюй увесь цей текст і надішли в чат з Claude.",
             "",
             "Що сталося: %s" % title,
             "Повідомлення: %s" % (error or "—"),
             "Час: %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
             "macOS %s · %s · Python %s" % (platform.mac_ver()[0] or platform.platform(), platform.machine(),
                                            sys.version.split()[0])]
    ver = HOME / "VERSION"
    if ver.exists():
        parts.append("Версія: " + ver.read_text().strip())
    if extra:
        parts += ["", "--- КОНТЕКСТ ---"]
        for k, v in extra.items():
            parts.append("%s: %s" % (k, v))
    if details:
        parts += ["", "--- ДЕТАЛІ ---", str(details).strip()]
    if path:
        parts += ["", "--- ЖУРНАЛ ВІКНА (%s) ---" % path.name, _tail(path)]
    dv = latest("davinci")
    if dv:
        parts += ["", "--- ЖУРНАЛ DAVINCI (%s) ---" % dv.name, _tail(dv, 250)]
    try:
        rp.write_text("\n".join(parts) + "\n", encoding="utf-8")
    except Exception:
        return None
    log("Звіт про збій: %s" % rp)
    if open_it:
        open_file(rp)
    return rp


def open_file(p):
    try:
        subprocess.Popen(["open", "-e", str(p)])      # TextEdit
    except Exception:
        try:
            subprocess.Popen(["open", str(p)])
        except Exception:
            pass


def open_folder():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.Popen(["open", str(LOG_DIR)])
    except Exception:
        pass


def ssl_fix():
    """Python з python.org не бачить сертифікатів macOS → SSL: CERTIFICATE_VERIFY_FAILED.
    Підставляємо набір сертифікатів certifi для всього процесу."""
    try:
        import certifi
        ca = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", ca)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca)
        import ssl
        ssl._create_default_https_context = lambda *a, **k: ssl.create_default_context(cafile=k.get("cafile") or ca)
        return ca
    except Exception as e:
        log("certifi недоступний: %s" % e)
        return None
