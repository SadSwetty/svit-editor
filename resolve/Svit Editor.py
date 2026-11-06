"""
Svit Editor — запуск з DaVinci Resolve (Workspace → Scripts → Svit Editor).

Цей скрипт працює всередині DaVinci (Python 3.6+). Він відкриває вікно Svit Editor
і виконує його команди: показує, які кліпи вибрані, і збирає готовий таймлайн.
"""
import json
import os
import shutil
import subprocess
import time
import traceback
from pathlib import Path

HOME = Path.home() / ".svit-editor"
PY = HOME / "venv" / "bin" / "python3"
UI = HOME / "app" / "ui.py"
EXPORT_DIR = Path.home() / "Movies" / "Svit Editor"
LOG_DIR = HOME / "logs"
try:
    BRIDGE_VERSION = (HOME / "VERSION").read_text().strip()
except Exception:
    BRIDGE_VERSION = "?"
BRIDGE_REV = 27      # версія протоколу DaVinci-частини; вікно перевіряє, чи вона свіжа
SCRIPT_PATH = (Path.home() / "Library" / "Application Support" / "Blackmagic Design" / "DaVinci Resolve" /
               "Fusion" / "Scripts" / "Utility" / "Svit Editor.py")
LOG_PATH = LOG_DIR / ("davinci_%s.log" % time.strftime("%Y%m%d_%H%M%S"))
SIZES = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080), "4:3": (1440, 1080),
         "16:9": (1920, 1080),
         "src": None}


def L(msg):
    """Журнал DaVinci-частини: ~/.svit-editor/logs/davinci_<час>.log (+ консоль DaVinci)."""
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    try:
        print(line)
    except Exception:
        pass
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(str(LOG_PATH), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def crash_report(title, details):
    """Текстовий звіт про збій + відкрити його в TextEdit."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        rp = LOG_DIR / ("Svit Editor звіт %s.txt" % time.strftime("%Y-%m-%d %H-%M-%S"))
        parts = ["SVIT EDITOR — ЗВІТ ПРО ЗБІЙ", "Скопіюй увесь цей текст і надішли в чат з Claude.", "",
                 "Що сталося: " + title, "Час: " + time.strftime("%Y-%m-%d %H:%M:%S")]
        v = HOME / "VERSION"
        if v.exists():
            parts.append("Версія: " + v.read_text().strip())
        parts += ["", "--- ДЕТАЛІ ---", str(details)]
        for prefix in ("ui", "davinci"):
            files = sorted(LOG_DIR.glob(prefix + "_*.log"), key=lambda p: p.stat().st_mtime)
            if files:
                tail = files[-1].read_text(encoding="utf-8", errors="ignore").splitlines()[-300:]
                parts += ["", "--- ЖУРНАЛ %s (%s) ---" % (prefix.upper(), files[-1].name)] + tail
        rp.write_text("\n".join(parts) + "\n", encoding="utf-8")
        subprocess.Popen(["open", "-e", str(rp)])
        return rp
    except Exception as e:
        print("Не вдалося записати звіт: %s" % e)


def osa(script):
    return subprocess.run(["osascript", "-e", script], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True)


def alert(text, title="Svit Editor"):
    t = text.replace('"', "'")
    osa('display alert "{}" message "{}"'.format(title, t))


def get_resolve():
    r = globals().get("resolve")
    if r:
        return r
    try:
        return bmd.scriptapp("Resolve")  # noqa: F821
    except Exception:
        pass
    try:
        import DaVinciResolveScript as dvr
        return dvr.scriptapp("Resolve")
    except Exception:
        return None


# ------------------------------------------------------------------ кліпи

def tc_to_sec(tc, fps):
    try:
        h, m, s, f = [int(x) for x in str(tc).replace(";", ":").split(":")]
        return h * 3600 + m * 60 + s + f / max(fps, 1)
    except Exception:
        return 0.0


def clip_info(item):
    try:
        path = item.GetClipProperty("File Path")
    except Exception:
        return None
    if not path:
        return None
    ctype = str(item.GetClipProperty("Type") or "")
    if ctype and "Video" not in ctype:
        return None
    try:
        fps = float(str(item.GetClipProperty("FPS")).split()[0])
    except Exception:
        fps = 25.0
    return {"uid": item.GetUniqueId(), "name": item.GetName(), "path": path, "fps": fps,
            "duration": tc_to_sec(item.GetClipProperty("Duration"), fps),
            "resolution": str(item.GetClipProperty("Resolution") or "")}


class Session:
    def __init__(self, resolve):
        self.resolve = resolve
        self.items = {}
        self.dropped = []   # кліпи, перетягнуті у вікно Svit Editor
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.dir = HOME / "session" / stamp
        (self.dir / "cmd").mkdir(parents=True, exist_ok=True)
        (self.dir / "resp").mkdir(parents=True, exist_ok=True)

    @property
    def project(self):
        return self.resolve.GetProjectManager().GetCurrentProject()

    def collect(self, mode):
        project = self.project
        mp = project.GetMediaPool()
        items = []
        if mode == "selected":
            try:
                sel = mp.GetSelectedClips() or []
                items = list(sel.values()) if isinstance(sel, dict) else list(sel)
            except Exception:
                items = []
        elif mode == "folder":
            folder = mp.GetCurrentFolder()
            items = (folder.GetClipList() or []) if folder else []
        elif mode == "dropped":
            items = list(self.dropped)
        else:
            tl = project.GetCurrentTimeline()
            seen = set()
            if tl:
                for idx in range(1, (tl.GetTrackCount("video") or 1) + 1):
                    for ti in tl.GetItemListInTrack("video", idx) or []:
                        mpi = ti.GetMediaPoolItem()
                        if mpi and mpi.GetUniqueId() not in seen:
                            seen.add(mpi.GetUniqueId())
                            items.append(mpi)
        out = []
        for it in items:
            info = clip_info(it)
            if info:
                self.items[info["uid"]] = it
                out.append(info)
        return out

    def resolve_paths(self, paths, append=True):
        """Знаходить перетягнуті файли в Media Pool; яких немає — імпортує в поточну папку."""
        mp = self.project.GetMediaPool()
        want = []
        for p in paths:
            rp = os.path.realpath(p)
            if rp not in want:
                want.append(rp)
        found = {}

        def walk(folder):
            for c in folder.GetClipList() or []:
                try:
                    fp = c.GetClipProperty("File Path")
                except Exception:
                    fp = None
                if fp and os.path.realpath(fp) in want and os.path.realpath(fp) not in found:
                    found[os.path.realpath(fp)] = c
            for sub in folder.GetSubFolderList() or []:
                walk(sub)
        walk(mp.GetRootFolder())
        missing = [p for p in want if p not in found]
        if missing:
            for c in mp.ImportMedia(missing) or []:
                try:
                    found[os.path.realpath(c.GetClipProperty("File Path"))] = c
                except Exception:
                    pass
        items = [found[p] for p in want if p in found]
        if append:
            have = set(i.GetUniqueId() for i in self.dropped)
            self.dropped += [i for i in items if i.GetUniqueId() not in have]
        else:
            self.dropped = items
        return self.collect("dropped")

    def write_sources(self):
        data = {m: self.collect(m) for m in ("selected", "folder", "timeline", "dropped")}
        (self.dir / "sources.json").write_text(json.dumps(data, ensure_ascii=False),
                                               encoding="utf-8")

    def status(self, pct, msg):
        tmp = self.dir / ".status.tmp"
        tmp.write_text(json.dumps({"pct": pct, "msg": msg}, ensure_ascii=False), encoding="utf-8")
        tmp.rename(self.dir / "status.json")

    def respond(self, cid, data):
        tmp = self.dir / "resp" / (".%s.tmp" % cid)
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.rename(self.dir / "resp" / ("%s.json" % cid))


# ------------------------------------------------------------------ монтаж

def frame_math(resolution, out_w, out_h, zoom, pan_x, pan_y):
    try:
        sw, sh = [int(x) for x in resolution.lower().split("x")]
    except Exception:
        return zoom, 0.0, 0.0
    fit = min(out_w / sw, out_h / sh)
    fill = max(out_w / sw, out_h / sh)
    total = fill / fit * zoom
    shown_w, shown_h = sw * fit * total, sh * fit * total
    max_x, max_y = max(0.0, (shown_w - out_w) / 2), max(0.0, (shown_h - out_h) / 2)
    return round(total, 3), round(-pan_x * max_x, 1), round(pan_y * max_y, 1)


def setup_timeline(tl, size, fps=None):
    if not size and not fps:
        return
    tl.SetSetting("useCustomSettings", "1")
    if fps:
        for k in ("timelineFrameRate", "timelinePlaybackFrameRate"):
            try:
                tl.SetSetting(k, str(fps))
            except Exception:
                pass
    if size:
        for k in ("timelineResolutionWidth", "timelineOutputResolutionWidth"):
            tl.SetSetting(k, str(size[0]))
        for k in ("timelineResolutionHeight", "timelineOutputResolutionHeight"):
            tl.SetSetting(k, str(size[1]))


_POS = [0]


def _next_pos():
    """Координати нового вузла: рядок над MediaIn/MediaOut, кожен наступний правіше."""
    _POS[0] += 1
    return 110 * _POS[0], -66


def _tool(comp, kind):
    x, y = _next_pos()
    t = comp.AddTool(kind, x, y)
    if not t:
        raise RuntimeError("Fusion не створив вузол %s" % kind)
    return t


# ------------------------------------------------------------------ вінтажні фактури
# Параметри: sat — насиченість (1 = як є), tint — множники R,G,B, lift — підняті чорні, con — контраст,
# vig — віньєтка, scan — рядки розгортки, shift — розшарування кольорів (пікселі), flick — мерехтіння,
# band — смуга трекінгу VHS, blur — розмиття (hblur — тільки по горизонталі), glow, grain, weave — хитання кадру.
LOOKS = {
    "vhs":       dict(sat=0.80, tint=(1.04, 0.98, 1.03), lift=0.02, con=1.14, vig=0.30, shift=2.0, flick=0.012,
                      hblur=0.8, grain=True),
    "camcorder": dict(sat=0.88, tint=(1.03, 1.0, 0.95), lift=0.015, con=1.10, vig=0.15, flick=0.006, grain=True),
    "film8":     dict(sat=0.80, tint=(1.10, 1.0, 0.85), lift=0.03, con=1.18, vig=0.50, flick=0.04, grain=True),
    "film16":    dict(sat=0.90, tint=(1.04, 1.0, 0.93), lift=0.02, con=1.12, vig=0.30, flick=0.015, grain=True),
    "crt":       dict(sat=0.90, tint=(0.96, 1.03, 1.06), lift=0.01, con=1.18, vig=0.55, flick=0.025, glow=0.4),
    "lostwave":  dict(sat=0.60, tint=(1.0, 1.02, 1.05), lift=0.05, con=1.02, vig=0.45, flick=0.015, blur=1.0,
                      glow=0.5, grain=True),
    "bwfilm":    dict(sat=0.0, tint=(1.0, 1.0, 1.0), lift=0.02, con=1.28, vig=0.55, flick=0.05, grain=True),
    "dream":     dict(sat=1.10, tint=(1.08, 0.94, 1.10), lift=0.03, con=1.05, vig=0.30, blur=0.6, glow=0.9),
}


def _scale(v, neutral, m):
    return neutral + (v - neutral) * m


def look_expr(p, m):
    """Вирази для Custom Tool: колір, розшарування, віньєтка, розгортка, мерехтіння, смуга трекінгу."""
    sat = 0.0 if p.get("sat", 1.0) == 0 else max(0.0, _scale(p.get("sat", 1.0), 1.0, m))
    tr, tg, tb = [_scale(t, 1.0, m) for t in p.get("tint", (1, 1, 1))]
    lift = max(0.0, p.get("lift", 0.0) * m)
    con = max(0.3, _scale(p.get("con", 1.0), 1.0, m))
    vig = p.get("vig", 0.0) * m
    scan = min(0.8, p.get("scan", 0.0) * m)
    sh = p.get("shift", 0.0) * m
    fl = p.get("flick", 0.0) * m
    band = p.get("band", 0.0) * m
    R = "getr1b(x + %.5f/w, y)" % sh if sh else "r1"
    B = "getb1b(x - %.5f/w, y)" % sh if sh else "b1"
    G = "g1"
    L = "(%s*0.299 + %s*0.587 + %s*0.114)" % (R, G, B)
    fac = "(1 - %.4f*pow(((x-0.5)*(x-0.5) + (y-0.5)*(y-0.5))*2, 1.5))" % vig
    if scan:
        fac += "*(1 - %.4f*0.5*(1 + sin(y*h*3.14159/1.5)))" % scan
    if fl:
        fac += "*(1 + %.4f*sin(time*12.9898)*sin(time*4.1414 + 1.3))" % fl
    add = " + %.4f*pow(max(0, sin(y*6.2832 - time*0.21)), 60)" % band if band else ""

    def ch(C, t):
        v = "(%s*(1-%.4f) + %s*%.4f)*%.4f" % (L, sat, C, sat, t)
        v = "((%s - 0.5)*%.4f + 0.5)" % (v, con)
        v = "(%s*(1-%.4f) + %.4f)" % (v, lift, lift)
        return "%s*%s%s" % (v, fac, add)
    return ch(R, tr), ch(G, tg), ch(B, tb)


# ------------------------------------------------------------------ колір фактури через LUT (сторінка Color)
# DaVinci приймає LUT лише зі своєї папки LUT (або підпапок)
# на Mac головна папка LUT — системна /Library/…; запасна — у папці користувача
LUT_DIRS = [Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/Svit Editor"),
            Path.home() / "Library" / "Application Support" / "Blackmagic Design" / "DaVinci Resolve" / "LUT" /
            "Svit Editor"]
LUT_DIR = LUT_DIRS[0]


def lut_dir():
    for d in LUT_DIRS:
        try:
            d.mkdir(parents=True, exist_ok=True)
            t = d / ".w"
            t.write_text("1")
            t.unlink()
            return d
        except Exception:
            continue
    return LUT_DIRS[-1]


def look_color(p, m, r, g, b):
    sat = 0.0 if p.get("sat", 1.0) == 0 else max(0.0, _scale(p.get("sat", 1.0), 1.0, m))
    tint = [_scale(t, 1.0, m) for t in p.get("tint", (1, 1, 1))]
    lift = max(0.0, p.get("lift", 0.0) * m)
    con = max(0.3, _scale(p.get("con", 1.0), 1.0, m))
    lum = r * 0.299 + g * 0.587 + b * 0.114
    out = []
    for c, t in zip((r, g, b), tint):
        v = (lum * (1 - sat) + c * sat) * t
        v = (v - 0.5) * con + 0.5
        v = v * (1 - lift) + lift
        out.append(min(1.0, max(0.0, v)))
    return out


def make_lut(name, m, size=17):
    d = lut_dir()
    path = d / ("svit_%s_%02d.cube" % (name, int(round(m * 10))))
    if path.exists():
        return path
    p = LOOKS[name]
    lines = ['TITLE "Svit %s"' % name, "LUT_3D_SIZE %d" % size, "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1"]
    n = float(size - 1)
    for bi in range(size):          # у .cube найшвидше змінюється червоний
        for gi in range(size):
            for ri in range(size):
                lines.append("%.6f %.6f %.6f" % tuple(look_color(p, m, ri / n, gi / n, bi / n)))
    path.write_text("\n".join(lines) + "\n")
    return path


def apply_look_lut(sess, items, look, strength, stats=None):
    """Колір вінтажу на першу ноду сторінки Color — працює навіть без Fusion."""
    if look not in LOOKS:
        return False
    try:
        m = 0.4 + 0.9 * max(0.0, min(1.0, float(strength)))
        path = make_lut(look, m)
        try:
            sess.project.RefreshLUTList()
        except Exception:
            pass
        ok = 0
        rel = "Svit Editor/" + path.name
        how = {}
        for ti in items:
            done = False
            for name, fn in (("item-rel", lambda: ti.SetLUT(1, rel)),
                             ("item-abs", lambda: ti.SetLUT(1, str(path))),
                             ("graph-rel", lambda: ti.GetNodeGraph().SetLUT(1, rel)),
                             ("graph-abs", lambda: ti.GetNodeGraph().SetLUT(1, str(path)))):
                try:
                    if fn():
                        done = True
                        how[name] = how.get(name, 0) + 1
                        break
                except Exception as e:
                    how["err:" + name] = str(e)[:80]
            ok += 1 if done else 0
        L("  LUT спроби: %s · файл %s" % (how or "усі 4 способи повернули False", path))
        L("  LUT %s: застосовано на %d з %d шматків (%s)" % (look, ok, len(items), path.name))
        if stats is not None:
            stats["lut"] = stats.get("lut", 0) + ok
        return ok == len(items) and ok > 0
    except Exception as e:
        L("  LUT не вдався: %s" % e)
        return False


# ------------------------------------------------------------------ стокові ефекти DaVinci (Resolve FX) у Fusion
_OFX = {"ids": None}
OFX_WANT = {"analog": "analogdamage", "filmdamage": "filmdamage", "shake": "camerashake", "glow": "resolvefx.glow",
            "grain": "filmgrain", "scanlines": "scanlines", "vignette": "vignett", "aberration": "chromaticaberration",
            "flare": "lensflare", "prism": "prismblur", "halation": "halation"}


def ofx_ids(comp=None):
    """Шукає в реєстрі Fusion стокові Resolve FX. Результат кешується на сесію і пишеться в журнал."""
    if _OFX["ids"] is not None:
        return _OFX["ids"]
    found = {}
    ids = set()
    try:
        fu = get_resolve().Fusion()
        for n in range(0, 40):
            try:
                lst = fu.GetRegList(n)
            except Exception:
                continue
            vals = lst.values() if isinstance(lst, dict) else (lst or [])
            for r in vals:
                try:
                    i = (r.GetAttrs() or {}).get("REGS_ID")
                    if i and str(i).lower().startswith("ofx."):
                        ids.add(str(i))
                except Exception:
                    pass
            if len(ids) > 30:
                break
    except Exception as e:
        L("Реєстр Fusion недоступний: %s" % e)
    for key, sub in OFX_WANT.items():
        for i in sorted(ids):
            if sub in i.lower().replace(" ", ""):
                found[key] = i
                break
    # якщо реєстр не прочитався — пробуємо типові назви
    if not found and comp is not None:
        for key, guess in (("analog", "ofx.com.blackmagicdesign.resolvefx.AnalogDamage"),
                           ("filmdamage", "ofx.com.blackmagicdesign.resolvefx.FilmDamage"),
                           ("shake", "ofx.com.blackmagicdesign.resolvefx.CameraShake"),
                           ("glow", "ofx.com.blackmagicdesign.resolvefx.Glow"),
                           ("grain", "ofx.com.blackmagicdesign.resolvefx.FilmGrain"),
                           ("scanlines", "ofx.com.blackmagicdesign.resolvefx.Scanlines")):
            try:
                t = comp.AddTool(guess, -32768, -32768)
                if t:
                    found[key] = guess
                    t.Delete()
            except Exception:
                pass
    L("Стокові Resolve FX: у реєстрі ofx-інструментів %d; знайдено: %s" % (len(ids), found or "нічого"))
    _OFX["ids"] = found
    return found


_OFX_LOGGED = set()


OFX_PARAMS = {
    # тряска без обертання й зуму, лише легке зміщення
    "shake": {"RAmpl": 0.0, "ZAmpl": 0.0},
}


def ofx_node(comp, chain, cur, key, blend, params=None):
    """Додає стоковий ефект DaVinci; blend — сила (0…1). Повертає True, якщо вийшло."""
    ids = ofx_ids(comp)
    if key not in ids:
        return False
    try:
        x, y = _next_pos()
        t = comp.AddTool(ids[key], x, y)
        if not t:
            return False
        linked = False
        for inp in ("Source", "Input", "Background"):
            try:
                r = t.ConnectInput(inp, cur[0])
                try:
                    out = getattr(t, inp).GetConnectedOutput()
                except Exception:
                    out = None
                if r or out:
                    linked = True
                    break
            except Exception:
                pass
        if not linked:
            L("  стоковий %s: не знайшов вхід для картинки" % key)
            try:
                t.Delete()
            except Exception:
                pass
            return False
        try:
            t.SetInput("Blend", max(0.05, min(1.0, float(blend))))
        except Exception:
            pass
        for pk, pv in dict(OFX_PARAMS.get(key, {}), **(params or {})).items():
            try:
                t.SetInput(pk, pv)
            except Exception:
                pass
        if key not in _OFX_LOGGED:
            _OFX_LOGGED.add(key)
            try:
                names = [(i.GetAttrs() or {}).get("INPS_ID") for i in (t.GetInputList() or {}).values()]
                L("  входи %s: %s" % (ids[key], ", ".join(str(x) for x in names[:60])))
            except Exception:
                pass
        cur[0] = t
        return True
    except Exception as e:
        L("  стоковий %s не додався: %s" % (key, e))
        return False


def flicker_keys(a, b, depth, base=1.0, step=2.0):
    """Мерехтіння ключовими кадрами (без виразів): значення стрибають кожні step кадрів."""
    keys, f, i = [], a, 0
    pattern = (0.0, 0.7, -0.4, 1.0, -0.8, 0.3, -0.2, 0.9, -0.6, 0.5)
    while f <= b:
        keys.append((f, base + depth * pattern[i % len(pattern)]))
        f += step
        i += 1
    return keys


# глобальні множники вигляду (повзунки «Вигляд» після монтажу): фантоми і зерно
# ghost — множник фантомів; grain — кількість зерна 0…1 (None = як задумано фактурою); live — живе налаштування
STYLE = {"ghost": 1.0, "grain": None, "live": False}
SVIT_COMP = "Svit"            # композиція з монтажу Svit
LOOK_COMP = "Svit Look"       # композиція з вікна «Мій таймлайн»


def _nm(t, name):
    """Фіксована назва вузла, щоб потім знайти його і підкрутити значення без перебудови."""
    try:
        t.SetAttrs({"TOOLS_Name": name})
    except Exception:
        pass
    return t


def _pass(t, off):
    try:
        t.SetAttrs({"TOOLB_PassThrough": bool(off)})
    except Exception:
        pass


def look_mult(look_strength):
    return 0.4 + 0.9 * max(0.0, min(1.0, float(look_strength)))


def look_grain(look, m):
    return min(1.0, 0.35 + 0.5 * m) if look in LOOKS and LOOKS[look].get("grain") else 0.0


def ghost_blend(look, m):
    return min(1.0, (0.25 + 0.1 * LOOKS.get(look, {}).get("shift", 1.5) * m) * STYLE["ghost"])


def set_dreamy(bl, mg, d):
    # м'яке сяйво без «туману»: невеликий радіус, слабке накладання
    bl.SetInput("XBlurSize", round(3 + 9 * max(d, 0.01), 1))
    mg.SetInput("Blend", round(0.08 + 0.32 * d, 3) if d > 0 else 0.0)
    _pass(bl, d <= 0)
    _pass(mg, d <= 0)


def set_halation(t, h):
    rid = ""
    try:
        rid = (t.GetAttrs() or {}).get("TOOLS_RegID", "")
    except Exception:
        pass
    if "SoftGlow" in rid:
        # halation як на плівці: світяться лише найсвітліші місця, вузько, тепло-помаранчевим, а не весь кадр
        for inp, v in (("Threshold", 0.86 - 0.12 * h), ("Gain", 0.3 + 0.9 * h), ("XGlowSize", 2.5 + 7 * h),
                       ("RedScale", 1.0), ("GreenScale", 0.55), ("BlueScale", 0.3)):
            try:
                t.SetInput(inp, v)
            except Exception:
                pass
    else:
        try:
            t.SetInput("Blend", min(1.0, 0.12 + 0.5 * h))
        except Exception:
            pass
    _pass(t, h <= 0)


def set_tone(bc, tone):
    tone = tone or {}
    for inp, v in (("Contrast", tone.get("contrast", 0)), ("Lift", tone.get("lift", 0)),
                   ("Gamma", tone.get("gamma", 1.0))):
        try:
            bc.SetInput(inp, float(v))
        except Exception:
            pass
    _pass(bc, not tone)


def set_grain(t, amt):
    try:
        t.SetInput("Blend", max(0.0, min(1.0, float(amt))))
    except Exception:
        pass
    _pass(t, amt <= 0.02)


def add_overlay(comp, chain, cur, ov):
    """Ефекти «на весь ролик» (як Adjustment Clip): дрімі і halation. Вузли будуються завжди
    (на нулі — вимкнені), щоб потім їх можна було підкручувати повзунками без перебудови."""
    how = []
    blur = float(ov.get("blur") or 0)
    hal = float(ov.get("halation") or 0)
    # дрімі (Orton): розмита копія накладається на різкий кадр режимом Screen — м'яке сяйво, а не просто мило
    orig = cur[0]
    bl = _nm(_tool(comp, "Blur"), "SvDreamyBlur")
    bl.ConnectInput("Input", orig)
    mg = _nm(_tool(comp, "Merge"), "SvDreamy")
    mg.ConnectInput("Background", orig)
    mg.ConnectInput("Foreground", bl)
    try:
        mg.SetInput("ApplyMode", "Screen")
    except Exception:
        pass
    set_dreamy(bl, mg, blur)
    cur[0] = mg
    if blur > 0:
        how.append("dreamy %.0f%%" % (blur * 100))
    # halation: стоковий ефект або червоно-помаранчеве світіння SoftGlow навколо світлих місць
    if ofx_node(comp, chain, cur, "halation", min(1.0, 0.12 + 0.5 * hal)):
        g = _nm(cur[0], "SvHal")
    else:
        g = _nm(chain(_tool(comp, "SoftGlow")), "SvHal")
        cur[0] = g
    set_halation(g, hal)
    if hal > 0:
        how.append("halation %.0f%%" % (hal * 100))
    return "+".join(how)


def add_look(comp, chain, cur, name, m, lut_ok=False, a=0.0, b=100.0):
    """Ланцюжок вінтажу лише зі стандартних вузлів Fusion і стокових Resolve FX (без виразів і Custom Tool)."""
    p = dict(LOOKS[name])
    how = []
    blend = min(1.0, 0.35 + 0.5 * m)
    # без хитання/кручення кадру і без Prism Blur (він двоїть контур — «силует»)
    stock = {"vhs": ["analog", "prism", "vignette"], "lostwave": ["analog", "prism", "glow", "vignette"],
             "crt": ["scanlines", "glow", "vignette"], "film8": ["filmdamage", "grain", "vignette"],
             "film16": ["grain", "vignette"], "bwfilm": ["filmdamage", "grain", "vignette"],
             "dream": ["glow", "vignette"], "camcorder": ["prism", "vignette"]}.get(name, [])
    used = []
    for key in stock:
        bl = blend
        if key == "shake":
            bl = min(0.6, p["weave"] * 150 * m)          # ледь помітне хитання кадру
        elif key == "prism":
            bl = max(0.03, ghost_blend(name, m))       # фантоми (нерухомі); 0 — вимикаємо вузол
        elif key == "grain":
            continue                                   # зерно — окремим вузлом SvGrain
        elif key == "vignette":
            bl = min(1.0, p.get("vig", 0.3) * 1.3 * m)
        if bl > 0.02 and ofx_node(comp, chain, cur, key, bl):
            used.append(key)
            if key == "prism":
                _nm(cur[0], "SvGhost")
                _pass(cur[0], ghost_blend(name, m) <= 0.02)
    if used:
        how.append("стокові:" + "+".join(used))
    if "analog" in used:
        p.pop("hblur", None)
    if "glow" in used:
        p.pop("glow", None)
    if p.get("hblur") or p.get("blur"):
        bl = chain(_tool(comp, "Blur"))
        if p.get("hblur"):
            bl.SetInput("LockXY", 0)
            bl.SetInput("XBlurSize", p["hblur"] * m)
            bl.SetInput("YBlurSize", 0.0)
        else:
            bl.SetInput("XBlurSize", p["blur"] * m)
        cur[0] = bl
        how.append("blur")
    # колір: LUT на сторінці Color; якщо LUT не став — простими вузлами
    if lut_ok:
        how.append("LUT")
    else:
        bc = chain(_tool(comp, "BrightnessContrast"))
        bc.SetInput("Saturation", 0.0 if p.get("sat", 1.0) == 0 else max(0.0, _scale(p.get("sat", 1.0), 1.0, m)))
        bc.SetInput("Contrast", max(-0.5, (_scale(p.get("con", 1.0), 1.0, m) - 1.0)))
        bc.SetInput("Lift", max(0.0, p.get("lift", 0.0) * m))
        cur[0] = bc
        tr_, tg_, tb_ = [_scale(t, 1.0, m) for t in p.get("tint", (1, 1, 1))]
        if max(abs(tr_ - 1), abs(tg_ - 1), abs(tb_ - 1)) > 0.005:
            cg = chain(_tool(comp, "ColorGain"))
            for inp, v in (("GainRed", tr_), ("GainGreen", tg_), ("GainBlue", tb_)):
                try:
                    cg.SetInput(inp, v)
                except Exception:
                    pass
            cur[0] = cg
        how.append("color")
    if p.get("flick"):
        fl = chain(_tool(comp, "BrightnessContrast"))
        cur[0] = fl
        keyframe(comp, fl, "Gain", flicker_keys(a, b, p["flick"] * m * 1.5), a, b)
        how.append("flicker")
    if p.get("glow"):
        gl = chain(_tool(comp, "SoftGlow"))
        gl.SetInput("Gain", 0.3 + 0.6 * p["glow"] * m)
        cur[0] = gl
        how.append("glow")
    return "+".join(how)


def layout_nodes(comp, mi, mo):
    """Розкладає вузли рядком MediaIn → … → MediaOut, щоб у Fusion їх було видно (а не купою)."""
    try:
        frame = getattr(comp, "CurrentFrame", None)
        flow = frame.FlowView if frame else None
        if not flow:
            return "позиції при створенні"
        x0, y0 = 0.0, 0.0
        try:
            pos = flow.GetPos(mi)
            if pos:
                vals = list(pos.values()) if isinstance(pos, dict) else list(pos)
                x0, y0 = float(vals[0]), float(vals[1])
        except Exception:
            pass
        order, t = [], mo
        for _ in range(60):
            try:
                o = t.Input.GetConnectedOutput() if t is mo else None
            except Exception:
                o = None
            nxt = None
            for inp in ("Input", "Source", "Background"):
                try:
                    o = getattr(t, inp).GetConnectedOutput()
                    if o:
                        nxt = o.GetTool()
                        break
                except Exception:
                    continue
            if nxt is None or nxt.Name == mi.Name:
                break
            order.append(nxt)
            t = nxt
        order.reverse()
        for i, tool in enumerate(order, 1):
            flow.SetPos(tool, x0 + i * 1.2, y0)
        flow.SetPos(mo, x0 + (len(order) + 1) * 1.2, y0)
        return len(order)
    except Exception as e:
        L("  розкладка вузлів не вдалась: %s" % e)
        return -1


def _animated(tool, inp, a, b):
    try:
        va, vb = tool.GetInput(inp, a), tool.GetInput(inp, b)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            return abs(va - vb) > 1e-4
    except Exception:
        pass
    return False


def piecewise(keys):
    """Вираз Fusion: лінійно між ключами, до першого і після останнього — тримає значення."""
    keys = sorted((float(f), float(v)) for f, v in keys)
    expr = "%f" % keys[-1][1]
    for (f0, v0), (f1, v1) in reversed(list(zip(keys[:-1], keys[1:]))):
        seg = "%f + (%f)*(time - %f)/%f" % (v0, v1 - v0, f0, max(1.0, f1 - f0))
        expr = "iif(time < %f, %s, %s)" % (f1, seg, expr)
    return "iif(time < %f, %f, %s)" % (keys[0][0], keys[0][1], expr)


def clamp_t(t0, n):
    return "max(0, min(1, (time - %f)/%f))" % (t0, max(1.0, n))


def add_transition(comp, chain, cur, kind, side, a, b, n, k):
    """Перехід на початку (side='in') або в кінці (side='out') шматка. Пара out+in на сусідніх шматках
    дає склейку-перехід: наїзд, свайп, затемнення, спалах, глітч, розмиття."""
    t0 = a if side == "in" else b - n
    if kind == "zoom":
        tr = chain(_tool(comp, "Transform"))
        cur[0] = tr
        peak = 1.35 + 0.35 * k
        keys = [(a, peak), (a + n, 1.0)] if side == "in" else [(b - n, 1.0), (b, peak)]
        how = keyframe(comp, tr, "Size", keys, a, b)
        bl = chain(_tool(comp, "Blur"))
        cur[0] = bl
        bk = [(a, 10 + 15 * k), (a + n, 0.0)] if side == "in" else [(b - n, 0.0), (b, 10 + 15 * k)]
        keyframe(comp, bl, "XBlurSize", bk, a, b)
        return how
    if kind == "whip":
        tr = chain(_tool(comp, "Transform"))
        cur[0] = tr
        keys = [(a, 1.25), (a + n, 1.0)] if side == "in" else [(b - n, 1.0), (b, 1.25)]
        keyframe(comp, tr, "Size", keys, a, b)
        bl = chain(_tool(comp, "Blur"))
        bl.SetInput("LockXY", 0)
        bl.SetInput("YBlurSize", 0.0)
        bk = [(a, 50 + 50 * k), (a + n, 0.0)] if side == "in" else [(b - n, 0.0), (b, 50 + 50 * k)]
        cur[0] = bl
        return keyframe(comp, bl, "XBlurSize", bk, a, b)
    if kind in ("dip", "white"):
        bc = chain(_tool(comp, "BrightnessContrast"))
        cur[0] = bc
        if kind == "dip":
            keys = [(a, 0.0), (a + n, 1.0)] if side == "in" else [(b - n, 1.0), (b, 0.0)]
            return keyframe(comp, bc, "Gain", keys, a, b)
        nw = max(1.0, min(n, round(n / 3.0)))   # спалах-перехід коротший за інші
        keys = [(a, 0.9), (a + nw, 0.0)] if side == "in" else [(b - nw, 0.0), (b, 0.9)]
        return keyframe(comp, bc, "Brightness", keys, a, b)
    if kind == "glitch":
        keys = [(a, 1.0), (a + n, 0.0)] if side == "in" else [(b - n, 0.0), (b, 1.0)]
        if ofx_node(comp, chain, cur, "prism", 1.0):
            keyframe(comp, cur[0], "Blend", keys, a, b)
        sh = chain(_tool(comp, "Transform"))
        cur[0] = sh
        t0 = a if side == "in" else b - n
        jit = [(t0 + i, (0.03 if i % 2 else -0.02) * (1 + k)) for i in range(int(n) + 1)]
        jit = [(f, 1.0 + v) for f, v in jit] + ([(a + n + 1, 1.0)] if side == "in" else [])
        if side == "out":
            jit = [(b - n - 1, 1.0)] + jit
        return keyframe(comp, sh, "Size", sorted(jit), a, b)
    if kind == "blur":
        bl = chain(_tool(comp, "Blur"))
        cur[0] = bl
        bk = [(a, 20 + 20 * k), (a + n, 0.0)] if side == "in" else [(b - n, 0.0), (b, 20 + 20 * k)]
        return keyframe(comp, bl, "XBlurSize", bk, a, b)
    raise RuntimeError("невідомий перехід %s" % kind)


TRANSITIONS = ("zoom", "whip", "dip", "white", "glitch", "blur")


def keyframe(comp, tool, inp, keys, a, b):
    """Ключові кадри на вході Fusion-вузла. keys — [(кадр, значення)].
    Пробує кілька способів API і перевіряє, що анімація справді є. Повертає назву способу."""
    errs = []
    # 1) BezierSpline-модифікатор + SetInput з часом
    try:
        tool.AddModifier(inp, "BezierSpline")
        for f, v in keys:
            tool.SetInput(inp, float(v), f)
        if _animated(tool, inp, keys[0][0], keys[-1][0]):
            return "keyframes"
    except Exception as e:
        errs.append("1: %s" % e)
    # 2) окремий сплайн + SetKeyFrames
    try:
        spl = comp.AddTool("BezierSpline", -32768, -32768)
        if spl:
            spl.SetKeyFrames(dict((float(f), {1: float(v)}) for f, v in keys), True)
            getattr(tool, inp).ConnectTo(spl)
            if _animated(tool, inp, keys[0][0], keys[-1][0]):
                return "spline"
    except Exception as e:
        errs.append("2: %s" % e)
    # 3) вираз: кусково-лінійна функція часу (працює завжди, але це не ключові кадри)
    try:
        try:
            getattr(tool, inp).ConnectTo(None)
        except Exception:
            pass
        getattr(tool, inp).SetExpression(piecewise(keys))
        return "expression" if _animated(tool, inp, keys[0][0], keys[-1][0]) else "expression?"
    except Exception as e:
        errs.append("3: %s" % e)
    raise RuntimeError("анімація %s не створилась (%s)" % (inp, "; ".join(errs) or "без помилок, але значення не змінюється"))


COMP_TMP = HOME / "comps"


def commit_comp(ti, comp, label, verbose=False, comp_name=SVIT_COMP):
    """DaVinci показує на сторінці Edit лише «збережені» композиції. Зібрану скриптом композицію
    експортуємо у файл і імпортуємо назад штатною функцією — як при ручному Import Fusion Composition —
    робимо її активною, а чернетку видаляємо."""
    try:
        COMP_TMP.mkdir(parents=True, exist_ok=True)
        before = list(ti.GetFusionCompNameList() or [])
        path = COMP_TMP / ("c_%d.comp" % int(time.time() * 1000))
        ok_exp = ti.ExportFusionComp(str(path), len(before) or 1)
        if not ok_exp or not path.exists():
            return "export=%s" % ok_exp
        new = ti.ImportFusionComp(str(path))
        after = list(ti.GetFusionCompNameList() or [])
        added = [n for n in after if n not in before]
        res = "export ok, import=%s, нові=%s" % (bool(new), added)
        if added:
            ti.LoadFusionCompByName(added[-1])
            for old in before:
                try:
                    ti.DeleteFusionCompByName(old)
                except Exception:
                    pass
            try:
                ti.RenameFusionCompByName(added[-1], comp_name)
            except Exception:
                pass
            res += ", активна=%s, лишились=%s" % (added[-1], ti.GetFusionCompNameList())
        elif before:
            # DaVinci 21 інколи не додає імпортовану копію — лишаємо зібрану композицію і даємо їй нашу назву,
            # щоб потім «Вигляд» і «Мій таймлайн» її впізнали
            try:
                ti.LoadFusionCompByName(before[-1])
                ok_rn = ti.RenameFusionCompByName(before[-1], comp_name)
                res += ", перейменовано %s→%s: %s" % (before[-1], comp_name, ok_rn)
            except Exception as e:
                res += ", перейменування: %s" % e
        try:
            path.unlink()
        except Exception:
            pass
        return res
    except Exception as e:
        return "помилка: %s" % e


def apply_fusion(ti, ratio=None, fx=(), strength=0.5, label="", look=None, look_strength=0.6,
                 tin=None, tout=None, lut_ok=False, verbose=False, overlay=None, tone=None, speed=0.6,
                 comp_name=SVIT_COMP):
    """Плавний наїзд і ефекти через Fusion: MediaIn → [сповільнення] → [рух/тряска] → [розмиття] →
    [Ч/Б] → [світіння] → [зерно] → [спалах] → MediaOut. Повертає (зроблено, помилки)."""
    fx = set(fx or ()) - {"slowmo"}          # швидкість відео не змінюємо
    look = look if look in LOOKS else None
    tin = tin if tin in TRANSITIONS else None
    tout = tout if tout in TRANSITIONS else None
    overlay = overlay or {}
    has_ov = any(float(v or 0) > 0 for v in overlay.values())
    if not fx and not ratio and not look and not tin and not tout and not has_ov and not tone and not STYLE["live"]:
        return [], []
    done, errs = [], []
    comp = None
    _POS[0] = 0
    try:
        comp = ti.AddFusionComp()
        if not comp:
            return [], ["AddFusionComp повернув None"]
        # робимо нову композицію активною (саме вона йде в картинку)
        try:
            names = ti.GetFusionCompNameList() or []
            if names:
                ti.LoadFusionCompByName(names[-1])
        except Exception:
            pass
        mi = list((comp.GetToolList(False, "MediaIn") or {}).values())
        mo = list((comp.GetToolList(False, "MediaOut") or {}).values())
        if not mi or not mo:
            return [], ["у композиції немає MediaIn/MediaOut"]
        comp.Lock()
        attrs = comp.GetAttrs() or {}
        a = attrs.get("COMPN_RenderStart")
        b = attrs.get("COMPN_RenderEnd")
        if a is None or b is None or b <= a:
            a, b = 0, max(1, int(ti.GetDuration() or 2) - 1)
        a, b = float(a), float(b)
        k = max(0.1, min(1.0, float(strength)))
        cur = [mi[0]]

        def chain(tool):
            tool.ConnectInput("Input", cur[0])
            return tool

        def step(name, fn):
            try:
                how = fn()
                done.append(name + ("(" + how + ")" if how else ""))
            except Exception as e:
                errs.append("%s: %s" % (name, e))

        def f():
            bc = _nm(chain(_tool(comp, "BrightnessContrast")), "SvTone")
            set_tone(bc, tone)
            cur[0] = bc
            return ("c%+.2f g%.2f" % (tone.get("contrast", 0), tone.get("gamma", 1))) if tone else "вимк."
        step("автоконтраст", f)
        fl_n = max(1.0, round(1 + (1 - float(speed)) * 5))      # спалах: 1…6 кадрів
        stock_shake = False
        if "shake" in fx and ofx_node(comp, chain, cur, "shake", 0.25 + 0.35 * k):
            stock_shake = True
            done.append("shake(стоковий)")
        if ratio or ("shake" in fx and not stock_shake):
            def f():
                tr = chain(_tool(comp, "Transform"))
                cur[0] = tr
                how = ""
                if ratio:
                    how = keyframe(comp, tr, "Size", [(a, 1.0), (b, float(ratio))], a, b)
                if "shake" in fx and not stock_shake:
                    sh = chain(_tool(comp, "Transform"))
                    cur[0] = sh
                    pk = 1.04 + 0.04 * k     # удар-«поштовх» замість кручення
                    keyframe(comp, sh, "Size", [(a, pk), (a + 2, 1.0), (a + 4, 1.0 + (pk - 1) / 2), (a + 7, 1.0)], a, b)
                return how
            step("zoom" if ratio else "shake", f)
        if look:
            def f():
                return add_look(comp, chain, cur, look, 0.4 + 0.9 * max(0.0, min(1.0, float(look_strength))), lut_ok,
                                a, b)
            step("look:" + look, f)
        step("на весь ролик", lambda: add_overlay(comp, chain, cur, overlay))
        # зерно: одним вузлом SvGrain (кількість з повзунка або як задумано фактурою)
        gr = STYLE["grain"]
        if gr is None:
            gr = look_grain(look, look_mult(look_strength))
            if "grain" in fx:
                gr = max(gr, min(1.0, 0.4 + 0.6 * k))
        fx = fx - {"grain"}

        def f():
            if ofx_node(comp, chain, cur, "grain", max(0.05, gr)):
                g = _nm(cur[0], "SvGrain")
            else:
                g = _nm(chain(_tool(comp, "FilmGrain")), "SvGrain")
                cur[0] = g
            set_grain(g, gr)
            return "%.0f%%" % (gr * 100) if gr > 0.02 else "вимк."
        step("зерно", f)
        if "blur_in" in fx:
            def f():
                bl = chain(_tool(comp, "Blur"))
                cur[0] = bl
                return keyframe(comp, bl, "XBlurSize", [(a, 6.0 + 14.0 * k), (min(b, a + 8), 0.0)], a, b)
            step("blur_in", f)
        if "bw" in fx:
            def f():
                bc = chain(_tool(comp, "BrightnessContrast"))
                bc.SetInput("Saturation", 0.0)
                bc.SetInput("Contrast", 0.08 + 0.12 * k)
                cur[0] = bc
            step("bw", f)
        if "glow" in fx and ofx_node(comp, chain, cur, "glow", 0.3 + 0.6 * k):
            done.append("glow(стоковий)")
        elif "glow" in fx:
            def f():
                g = chain(_tool(comp, "SoftGlow"))
                g.SetInput("Gain", 0.4 + 0.8 * k)
                cur[0] = g
            step("glow", f)
        if "rgb" in fx:
            def f():
                if ofx_node(comp, chain, cur, "prism", 1.0):
                    return keyframe(comp, cur[0], "Blend", [(a, 0.6 + 0.4 * k), (min(b, a + 6), 0.0)], a, b)
                bl = chain(_tool(comp, "Blur"))
                bl.SetInput("LockXY", 0)
                bl.SetInput("YBlurSize", 0.0)
                cur[0] = bl
                return keyframe(comp, bl, "XBlurSize", [(a, 15 + 20 * k), (min(b, a + 6), 0.0)], a, b)
            step("rgb", f)
        if "fade_in" in fx:
            def f():
                fd = chain(_tool(comp, "BrightnessContrast"))
                cur[0] = fd
                return keyframe(comp, fd, "Gain", [(a, 0.0), (min(b, a + 10 + 8 * k), 1.0)], a, b)
            step("fade_in", f)
        if "flash" in fx:
            def f():
                fl = chain(_tool(comp, "BrightnessContrast"))
                cur[0] = fl
                return keyframe(comp, fl, "Brightness", [(a, 0.5 + 0.45 * k), (min(b, a + fl_n), 0.0)], a, b)
            step("flash", f)
        # тривалість переходу: швидко = 2 кадри, повільно = 12 (але не більше третини шматка)
        n_tr = max(2.0, min(round(2 + (1 - float(speed)) * 10), (b - a) / 3.0))
        if tin:
            step("in:" + tin, lambda: add_transition(comp, chain, cur, tin, "in", a, b, n_tr, k))
        if tout:
            step("out:" + tout, lambda: add_transition(comp, chain, cur, tout, "out", a, b, n_tr, k))
        mo[0].ConnectInput("Input", cur[0])
        n_nodes = layout_nodes(comp, mi[0], mo[0])
        if verbose:
            L("  вузлів у ланцюжку: %s" % n_nodes)
            diag = {}
            try:
                diag["range"] = (a, b, attrs.get("COMPN_GlobalStart"), attrs.get("COMPN_GlobalEnd"))
            except Exception:
                pass
            try:
                diag["comps"] = ti.GetFusionCompNameList()
            except Exception:
                pass
            try:
                diag["tools"] = [t.Name for t in (comp.GetToolList(False) or {}).values()]
            except Exception:
                pass
            try:
                diag["mediaout<-"] = mo[0].Input.GetConnectedOutput().GetTool().Name
            except Exception as e:
                diag["mediaout<-"] = "? (%s)" % e
            L("  ДІАГНОСТИКА %s: %s" % (label, diag))
    except Exception as e:
        errs.append("fusion: %s" % e)
    finally:
        if comp is not None:
            try:
                comp.Unlock()
            except Exception:
                pass
    if comp is not None and done:
        cr = commit_comp(ti, comp, label, verbose, comp_name)
        if verbose or not cr.startswith("export ok"):
            L("  commit %s: %s" % (label, cr))
    L("  Fusion %s: %s%s" % (label, ", ".join(done) or "—", ("; ПОМИЛКИ: " + " | ".join(errs)) if errs else ""))
    return done, errs


def is_video(ti):
    try:
        return ti.GetTrackTypeAndIndex()[0] == "video"
    except Exception:
        return True


def find_or_import(sess, path):
    """Аудіофайл треку: шукаємо в Media Pool за шляхом, якщо немає — імпортуємо."""
    mp = sess.project.GetMediaPool()
    want = os.path.realpath(path)
    found = []

    def walk(folder):
        for c in folder.GetClipList() or []:
            try:
                fp = c.GetClipProperty("File Path")
            except Exception:
                fp = None
            if fp and os.path.realpath(fp) == want:
                found.append(c)
                return
        for sub in folder.GetSubFolderList() or []:
            if not found:
                walk(sub)
    walk(mp.GetRootFolder())
    if found:
        return found[0]
    imported = mp.ImportMedia([path]) or []
    return imported[0] if imported else None


def timeline_fps(tl):
    try:
        return float(tl.GetSetting("timelineFrameRate") or 25)
    except Exception:
        return 25.0


def place_song(sess, mp, tl, mus, start):
    song = find_or_import(sess, mus["path"])
    if song is None:
        L("Трек не знайдено: %s" % mus["path"])
        return
    try:
        sfps = float(str(song.GetClipProperty("FPS") or "").split()[0])
    except Exception:
        sfps = timeline_fps(tl)
    mp.AppendToTimeline([{"mediaPoolItem": song, "mediaType": 2, "trackIndex": 1,
                          "startFrame": int(round(mus["start"] * sfps)),
                          "endFrame": int(round(mus["end"] * sfps)),
                          "recordFrame": start}])


def append_video(mp, tl, video, by_id, size, sess=None, at=None, fx_strength=0.5, stats=None, look_strength=0.6,
                 defer_song=None, overlay=None, tone=None, speed=0.6):
    """Кладе шматки ролика встик: перший — у задану позицію, решта — один за одним у кінець таймлайну.
    Так немає мікропроміжків від округлення, коли частота кадрів джерела і таймлайну різна."""
    tfps = timeline_fps(tl)
    start = int(at) if at is not None else int(tl.GetEndFrame())
    mus = video.get("music")
    infos, metas = [], []
    for sg in video["segments"]:
        src = by_id[sg["source"]]
        sf = int(round(sg["start"] * src["fps"]))
        ef = max(sf + 1, int(round(sg["end"] * src["fps"])))
        info = {"mediaPoolItem": src["item"], "startFrame": sf, "endFrame": ef, "trackIndex": 1}
        if mus:
            info["mediaType"] = 1   # тільки картинка — звучить трек
        infos.append(info)
        metas.append((src, sg))
    if not infos:
        return start, start
    first = dict(infos[0], recordFrame=start)
    items = list(mp.AppendToTimeline([first]) or [])
    if len(infos) > 1:
        items += list(mp.AppendToTimeline(infos[1:]) or [])
    vi = [ti for ti in items if is_video(ti)]
    try:
        end_frame = int(max(ti.GetEnd() for ti in vi)) if vi else start
        gaps = sum(1 for x, y in zip(vi, vi[1:]) if int(y.GetStart()) != int(x.GetEnd()))
    except Exception:
        end_frame, gaps = start + int(round(sum(sg["end"] - sg["start"] for _, sg in metas) * tfps)), -1
    L("Ролик «%s»: шматків %d, на таймлайн лягло %d (відео %d), кадри %d–%d, проміжків між шматками: %s" %
      (video.get("title", ""), len(infos), len(items), len(vi), start, end_frame, gaps))
    if len(vi) < len(infos):
        L("  УВАГА: DaVinci додав менше шматків, ніж у плані")
    for ti, (src, sg) in zip(vi, metas):
        if not size:
            if sg["zoom"] != 1.0:
                ti.SetProperty("ZoomX", sg["zoom"])
                ti.SetProperty("ZoomY", sg["zoom"])
            continue
        z, px, py = frame_math(src["resolution"], size[0], size[1], sg["zoom"],
                               sg["pan_x"], sg["pan_y"])
        ti.SetProperty("ZoomX", z)
        ti.SetProperty("ZoomY", z)
        if px:
            ti.SetProperty("Pan", px)
        if py:
            ti.SetProperty("Tilt", py)
    look = video.get("look")
    lut_ok = False
    if look:
        lut_ok = apply_look_lut(sess, vi, look, look_strength, stats)
    segs_all = [m[1] for m in metas]
    for n, (ti, (src, sg)) in enumerate(zip(vi, metas), 1):
        ze = sg.get("zoom_end")
        ratio = ze / max(sg["zoom"], 0.01) if ze and abs(ze - sg["zoom"]) > 0.005 else None
        tin = sg.get("tr") if n > 1 else None
        tout = segs_all[n].get("tr") if n < len(segs_all) else None
        if stats is not None:
            stats["total"] = stats.get("total", 0) + 1
        tn = (tone or {}).get(str(sg["source"]))
        if ratio or sg.get("fx") or look or tin or tout or overlay or tn:
            done, errs = apply_fusion(ti, ratio, sg.get("fx") or (), fx_strength,
                                      "#%d %s %.1f–%.1f" % (n, src.get("name", ""), sg["start"], sg["end"]),
                                      look, look_strength, tin, tout, lut_ok=lut_ok, overlay=overlay, tone=tn, speed=speed,
                                      verbose=(stats is not None and stats.get("total", 0) <= 2))
            if stats is not None:
                try:
                    stats["comps"] = stats.get("comps", 0) + (1 if (ti.GetFusionCompCount() or 0) > 0 else 0)
                except Exception:
                    pass
                stats["ok"] += 1 if (done and not errs) else 0
                stats["fail"] += 1 if errs else 0
                for e in errs:
                    if len(stats["errors"]) < 5:
                        stats["errors"].append(e)
    if mus and sess is not None:
        if defer_song is not None:
            defer_song.append((mus, start))
        else:
            place_song(sess, mp, tl, mus, start)
    return start, end_frame


def add_subs(mp, srt, tl=None):
    if not srt:
        return
    try:
        subs = mp.ImportMedia([srt]) or []
        if subs:
            # субтитри від самого початку таймлайну (час у файлі — від нуля)
            done = None
            if tl is not None:
                try:
                    done = mp.AppendToTimeline([{"mediaPoolItem": subs[0], "recordFrame": tl.GetStartFrame()}])
                except Exception:
                    done = None
            if not done:
                done = mp.AppendToTimeline([{"mediaPoolItem": subs[0]}])
            L("Субтитри %s: %s" % (os.path.basename(srt), "додано" if done else "не додались"))
    except Exception as e:
        L("Субтитри не додались автоматично: %s" % e)


TEXT_COMP = "Svit Text"


def anim_chain(comp, cur, anim, a, b):
    """Вузли анімації рядка: поява/зникнення прозорістю + підйом, поп або розмиття. Повертає (вузол, опис)."""
    kind = (anim or {}).get("anim", "fade")
    if kind == "none":
        return cur, "без анімації"
    k = max(0.0, min(1.0, float((anim or {}).get("anim_strength", 50)) / 100.0))
    sm = max(0.0, min(1.0, float((anim or {}).get("anim_smooth", 50)) / 100.0))
    how = []
    din = max(2.0, min(round(3 + 20 * sm), (b - a) / 2.5))        # тривалість появи
    dout = max(2.0, min(round(din * 0.6), (b - a) / 3.0))
    if kind in ("rise", "pop"):
        tr = _nm(_tool(comp, "Transform"), "SvTextMove")
        tr.ConnectInput("Input", cur)
        cur = tr
        if kind == "pop":
            s0 = 1.0 - (0.08 + 0.32 * k)
            how.append("pop:" + keyframe(comp, tr, "Size", [(a, s0), (a + din, 1.0)], a, b))
        else:
            dy = 0.01 + 0.07 * k
            ok = None
            try:
                tr.AddModifier("Center", "XYPath")
                tr.SetInput("Center", {1: 0.5, 2: 0.5 - dy}, a)
                tr.SetInput("Center", {1: 0.5, 2: 0.5}, a + din)
                ok = "path"
            except Exception:
                ok = None
            if not ok:
                try:
                    tr.Center.SetExpression("Point(0.5, 0.5 - %.4f*max(0, 1 - (time - %.1f)/%.1f))" % (dy, a, din))
                    ok = "expr"
                except Exception as e:
                    ok = "не вдалось (%s)" % e
            how.append("rise:" + ok)
    if kind == "blur":
        bl = _tool(comp, "Blur")
        bl.ConnectInput("Input", cur)
        cur = bl
        how.append("blur:" + keyframe(comp, bl, "XBlurSize", [(a, 4 + 26 * k), (a + din, 0.0)], a, b))
    fd = _nm(_tool(comp, "BrightnessContrast"), "SvTextFade")
    fd.ConnectInput("Input", cur)
    try:
        fd.SetInput("Alpha", 1)                 # прозорість теж, а не лише колір
    except Exception:
        pass
    how.append("fade:" + keyframe(comp, fd, "Gain", [(a, 0.0), (a + din, 1.0), (b - dout, 1.0), (b, 0.0)], a, b))
    return fd, ", ".join(how)


_FONTS = {"list": None}


def fusion_fonts():
    """Шрифти, які бачить Fusion: {родина: [стилі]}."""
    if _FONTS["list"] is None:
        fl = {}
        try:
            fu = get_resolve().Fusion()
            raw = fu.FontManager.GetFontList() or {}
            for fam, styles in raw.items():
                fl[str(fam)] = [str(x) for x in (styles.values() if isinstance(styles, dict) else styles or [])]
        except Exception as e:
            L("Шрифти Fusion: не вдалося отримати список (%s)" % e)
        _FONTS["list"] = fl
        if fl:
            L("Шрифти Fusion: %d родин" % len(fl))
    return _FONTS["list"]


def pick_font(fam, style):
    """Шрифт для Text+: такий самий, якщо Fusion його знає, інакше найближчий / Arial Bold."""
    fl = fusion_fonts()
    fam = (fam or "").lstrip(".").strip()
    if not fl:
        return fam or "Arial", style or "Bold", "без перевірки"
    low = {k.lower(): k for k in fl}

    def best_style(f, want):
        sts = fl.get(f) or []
        for cand in (want, "Bold", "Black", "Heavy", "Semibold", "Regular"):
            for s_ in sts:
                if cand and s_.lower() == str(cand).lower():
                    return s_
        return sts[0] if sts else (want or "Regular")
    if fam.lower() in low:
        f = low[fam.lower()]
        return f, best_style(f, style), "є"
    for k in low:                       # «SF Compact» → «SF Compact Display» тощо
        if fam and (k.startswith(fam.lower()) or fam.lower().startswith(k)):
            return low[k], best_style(low[k], style), "схожий"
    for f in ("Arial", "Helvetica Neue", "Helvetica", "Open Sans"):
        if f.lower() in low:
            return low[f.lower()], best_style(low[f.lower()], "Bold"), "замінено"
    f = sorted(fl)[0]
    return f, best_style(f, "Bold"), "замінено"


def _set(t, inp, *vals):
    for v in vals:
        try:
            if t.SetInput(inp, v) is not False:
                return True
        except Exception:
            continue
    return False


def build_text_comp(ti, anim, n, label, tp=None):
    """Fusion-композиція рядка. tp — редагований текст: Text+ (слова, шрифт, колір правляться у Fusion),
    навколо нього тінь, світіння й halation; без tp — анімуємо готову картинку рядка."""
    if not tp and (anim or {}).get("anim") == "none":
        return "картинка без анімації"
    _POS[0] = 0
    comp = ti.AddFusionComp()
    if not comp:
        return "AddFusionComp → None"
    how = []
    try:
        names = ti.GetFusionCompNameList() or []
        if names:
            ti.LoadFusionCompByName(names[-1])
        mi = list((comp.GetToolList(False, "MediaIn") or {}).values())
        mo = list((comp.GetToolList(False, "MediaOut") or {}).values())
        if not mi or not mo:
            return "немає MediaIn/MediaOut"
        comp.Lock()
        attrs = comp.GetAttrs() or {}
        a = float(attrs.get("COMPN_RenderStart") or 0)
        b = float(attrs.get("COMPN_RenderEnd") or (n - 1))
        if b <= a:
            a, b = 0.0, float(max(1, n - 1))
        cur = mi[0]
        if tp:
            tx = _nm(_tool(comp, "TextPlus"), "SvText")
            _set(tx, "StyledText", tp["text"])
            fam, sty, how_f = pick_font(tp["font"], tp["style"])
            _set(tx, "Font", fam)
            _set(tx, "Style", sty)
            _set(tx, "Size", float(tp["size"]))
            _set(tx, "Center", {1: float(tp["cx"]), 2: float(tp["cy"])}, [float(tp["cx"]), float(tp["cy"])])
            for i, c in enumerate(("Red1", "Green1", "Blue1")):
                _set(tx, c, float(tp["rgb"][i]))
            if tp.get("outline", 0) > 0.01:
                dark = sum(tp["rgb"]) > 1.5
                _set(tx, "Enabled2", 1)
                _set(tx, "Thickness2", 0.02 + 0.08 * tp["outline"])
                for c in ("Red2", "Green2", "Blue2"):
                    _set(tx, c, 0.0 if dark else 1.0)
            got = {}
            for k in ("StyledText", "Font", "Style", "Size", "Center"):
                try:
                    got[k] = tx.GetInput(k)
                except Exception as e:
                    got[k] = "? %s" % e
            how.append("Text+ шрифт %s %s (%s; хотіли %s %s) → у вузлі %s" % (fam, sty, how_f, tp["font"], tp["style"], got))
            txt = tx
            if tp.get("glow", 0) > 0.01:
                g = _nm(_tool(comp, "SoftGlow"), "SvTextGlow")
                g.ConnectInput("Input", txt)
                _set(g, "Threshold", 0.0)
                _set(g, "Gain", 0.4 + 2.2 * tp["glow"])
                _set(g, "XGlowSize", 4 + 30 * tp["glow"])
                txt = g
            if tp.get("halation", 0) > 0.01:
                h = _nm(_tool(comp, "SoftGlow"), "SvTextHal")
                h.ConnectInput("Input", txt)
                for inp, v in (("Threshold", 0.0), ("Gain", 0.5 + 2.0 * tp["halation"]),
                               ("XGlowSize", 2 + 10 * tp["halation"]), ("RedScale", 1.0), ("GreenScale", 0.36),
                               ("BlueScale", 0.16)):
                    _set(h, inp, v)
                txt = h
            base = mi[0]
            if tp.get("shadow", 0) > 0.01:
                sh = _nm(_tool(comp, "BrightnessContrast"), "SvTextShadowColor")
                sh.ConnectInput("Input", tx)
                _set(sh, "Gain", 0.0)
                sb = _nm(_tool(comp, "Blur"), "SvTextShadow")
                sb.ConnectInput("Input", sh)
                _set(sb, "XBlurSize", 2 + 14 * tp["shadow"])
                _set(sb, "Blend", min(1.0, 0.5 + 0.6 * tp["shadow"]))
                ms = _tool(comp, "Merge")
                ms.ConnectInput("Background", base)
                ms.ConnectInput("Foreground", sb)
                base = ms
            mg = _nm(_tool(comp, "Merge"), "SvTextOver")
            mg.ConnectInput("Background", base)
            mg.ConnectInput("Foreground", txt)
            cur = mg
        cur, h2 = anim_chain(comp, cur, anim, a, b)
        how.append(h2)
        mo[0].ConnectInput("Input", cur)
        layout_nodes(comp, mi[0], mo[0])
    except Exception as e:
        how.append("помилка: %s" % e)
    finally:
        try:
            comp.Unlock()
        except Exception:
            pass
    commit_comp(ti, comp, label, False, TEXT_COMP)
    return ", ".join(how)


def place_text(sess, mp, tl, items, anim):
    """Svit-текст: PNG-рядки на нову верхню відеодоріжку, кожен у свій час, з анімацією."""
    if not items:
        return
    paths = sorted({it["png"] for it in items if Path(it["png"]).exists()})
    if not paths:
        L("Текст: картинок не знайдено")
        return
    root = mp.GetRootFolder()
    folder = None
    try:
        folder = mp.AddSubFolder(root, "Svit Text %s" % time.strftime("%H%M%S"))
        if folder:
            mp.SetCurrentFolder(folder)
    except Exception:
        folder = None
    imported = []
    for pth in paths:            # по одному файлу — щоб DaVinci не склеїв картинки в секвенцію
        try:
            imported += mp.ImportMedia([pth]) or []
        except Exception as e:
            L("  імпорт %s: %s" % (os.path.basename(pth), e))
    by_path, by_name = {}, {}
    for c in imported:
        try:
            by_path[os.path.realpath(c.GetClipProperty("File Path"))] = c
        except Exception:
            pass
        try:
            by_name[c.GetName()] = c
        except Exception:
            pass
    L("Текст: імпортовано %d з %d картинок" % (len(imported), len(paths)))
    if folder:
        try:
            mp.SetCurrentFolder(root)
        except Exception:
            pass
    tl.AddTrack("video")
    track = tl.GetTrackCount("video")
    try:
        tl.SetTrackName("video", track, "Svit Text")
    except Exception:
        pass
    fps = timeline_fps(tl)
    t0 = tl.GetStartFrame()
    ok, prev_end = 0, -1
    for i, it in enumerate(items):
        mpi = by_path.get(os.path.realpath(it["png"])) or by_name.get(os.path.basename(it["png"]))
        if not mpi:
            if i < 3:
                L("  текст #%d: картинку не знайдено в Media Pool (%s)" % (i + 1, os.path.basename(it["png"])))
            continue
        rec = t0 + int(round(it["start"] * fps))
        rec = max(rec, prev_end)
        n = int(round(it["end"] * fps)) + t0 - rec
        if i + 1 < len(items):
            n = min(n, t0 + int(round(items[i + 1]["start"] * fps)) - rec)
        if n < 2:
            continue
        res = mp.AppendToTimeline([{"mediaPoolItem": mpi, "startFrame": 0, "endFrame": n - 1,
                                    "trackIndex": track, "recordFrame": rec}]) or []
        if not res:
            L("  текст #%d не став на таймлайн" % (i + 1))
            continue
        prev_end = rec + n
        ok += 1
        try:
            got = int(res[0].GetDuration() or n)
            if got < n - 1:
                L("  текст #%d коротший, ніж треба: %d з %d кадрів (стандартна тривалість кадру в DaVinci?)" % (i + 1, got, n))
        except Exception:
            pass
        try:
            how = build_text_comp(res[0], anim, n, "txt#%d" % (i + 1), it.get("tp"))
            if i < 2:
                L("  текст #%d: %s" % (i + 1, how))
        except Exception as e:
            L("  текст #%d анімація: %s" % (i + 1, e))
    L("Svit-текст: рядків %d з %d на доріжці V%d%s" % (ok, len(items), track,
                                                      " (редагований Text+ — правиться у Fusion)" if items[0].get("tp") else ""))


def style_params(data, plan):
    """Параметри вигляду з налаштувань (спільні для монтажу, «Вигляду» після монтажу і «Мого таймлайну»)."""
    fxs = float(data.get("fx_strength", 0.5))
    lks = float(data.get("look_strength", 0.6))
    ov = {k: float(v) for k, v in (data.get("overlay") or {}).items() if float(v or 0) > 0}
    spd = float(data.get("tr_speed", 0.6))
    ts = float(data.get("tone_strength", 0))
    STYLE["ghost"] = float(data.get("ghost", 1.0))
    g = data.get("grain")
    STYLE["grain"] = None if g is None else float(g)
    tone = {}
    if ts > 0:
        for sid, t in (plan.get("tone") or {}).items():
            tone[sid] = {"contrast": t.get("contrast", 0) * ts, "lift": t.get("lift", 0) * ts,
                         "gamma": 1 + (t.get("gamma", 1) - 1) * ts}
    return fxs, lks, ov, spd, ts, tone


def manual_tone(ts):
    """Контраст для власного таймлайну (без аналізу кадрів): помірна S-подібна добавка."""
    return {"contrast": 0.18 * ts, "lift": 0.0, "gamma": 1.0 - 0.06 * ts} if ts > 0 else {}


def current_frame(tl):
    try:
        fps = int(round(timeline_fps(tl)))
        return int(round(tc_to_sec(tl.GetCurrentTimecode(), fps) * fps))
    except Exception:
        return None


def playhead_first(tl, entries):
    """Спершу шматок під курсором, далі — ті, що ближче до нього (щоб зміни було видно одразу)."""
    f = current_frame(tl)
    if f is None:
        return entries

    def dist(e):
        try:
            a, b = e[0].GetStart(), e[0].GetEnd()
        except Exception:
            return 10 ** 9
        return 0 if a <= f < b else min(abs(a - f), abs(b - 1 - f))
    return sorted(entries, key=dist)


def has_sv(comp):
    try:
        return bool(comp and (comp.FindTool("SvTone") or comp.FindTool("SvHal")))
    except Exception:
        return False


def comp_of(ti, name):
    """Наша композиція: за назвою, а якщо DaVinci назву не дав — за нашими вузлами Sv*."""
    try:
        names = list(ti.GetFusionCompNameList() or [])
    except Exception:
        return None
    if name in names:
        try:
            return ti.GetFusionCompByName(name)
        except Exception:
            return None
    for nm in names:
        if nm in (SVIT_COMP, LOOK_COMP, TEXT_COMP):
            continue
        try:
            c = ti.GetFusionCompByName(nm)
        except Exception:
            c = None
        if has_sv(c):
            return c
    return None


def foreign_comp(ti, mine):
    """Чи має шматок свою (не нашу) Fusion-композицію з вузлами — таку не чіпаємо."""
    try:
        names = list(ti.GetFusionCompNameList() or [])
    except Exception:
        return False
    for nm in names:
        if nm == mine:
            continue
        if nm in (SVIT_COMP, LOOK_COMP):
            return True
        try:
            c = ti.GetFusionCompByName(nm)
            if has_sv(c):
                continue                                       # наша, просто без назви
            if c and len(c.GetToolList(False) or {}) > 2:     # не лише MediaIn → MediaOut
                return True
        except Exception:
            return True
    return False


ADJ_NAMES = ("adjustment", "коригувальн", "корректирующ", "einstellungsclip", "clip de ajuste", "clip d'ajustement")


def is_adjustment(ti):
    try:
        if ti.GetMediaPoolItem():
            return False
    except Exception:
        pass
    try:
        n = (ti.GetName() or "").lower()
    except Exception:
        return False
    return any(k in n for k in ADJ_NAMES)


def adjustment_items(tl):
    out = []
    for idx in range(1, (tl.GetTrackCount("video") or 1) + 1):
        for ti in tl.GetItemListInTrack("video", idx) or []:
            if is_adjustment(ti):
                out.append(ti)
    return out


def style_targets(sess, data):
    """[(таймлайн, [(шматок, info), …]), …] і кількість пропущених шматків."""
    project = sess.project
    cur_tl = project.GetCurrentTimeline()
    skipped = 0
    if data.get("manual"):
        if not cur_tl:
            raise RuntimeError("У DaVinci не відкритий жоден таймлайн.")
        ents = []
        adj = adjustment_items(cur_tl)
        if adj:
            # є Adjustment Clip — ефекти кладемо лише на нього, кліпи під ним не чіпаємо
            for ti in adj:
                if foreign_comp(ti, LOOK_COMP):
                    skipped += 1
                    continue
                ents.append((ti, {"look": data.get("look_override") or None, "src": None,
                                  "label": "adj#%d" % (len(ents) + 1)}))
            L("  Adjustment Clip на таймлайні: %d — ефекти на них" % len(adj))
            return [(cur_tl, ents)], skipped
        for idx in range(1, (cur_tl.GetTrackCount("video") or 1) + 1):
            try:
                if cur_tl.GetTrackName("video", idx) == "Svit Text":
                    continue                      # доріжку з текстом ефектами не чіпаємо
            except Exception:
                pass
            for ti in cur_tl.GetItemListInTrack("video", idx) or []:
                try:
                    mpi = ti.GetMediaPoolItem()
                except Exception:
                    mpi = None
                if not mpi:
                    continue                      # титри, генератори, adjustment clips
                names = []
                try:
                    names = list(ti.GetFusionCompNameList() or [])
                except Exception:
                    pass
                if TEXT_COMP in names:
                    continue
                unnamed_ours = LOOK_COMP not in names and SVIT_COMP not in names and comp_of(ti, SVIT_COMP) is not None
                if SVIT_COMP in names or unnamed_ours:
                    # шматок з монтажу Svit (план не знайдено) — можна лише підкрутити значення, не перебудувати
                    ents.append((ti, {"look": data.get("look_override") or None, "src": None, "svit_only": True,
                                      "label": "#%d" % (len(ents) + 1)}))
                    continue
                if foreign_comp(ti, LOOK_COMP):
                    skipped += 1
                    continue
                ents.append((ti, {"look": data.get("look_override") or None, "src": None,
                                  "label": "#%d" % (len(ents) + 1)}))
        return [(cur_tl, ents)], skipped
    plan = data["plan"]
    videos = plan.get("videos") or []
    if data.get("look_override") is not None:
        for v in videos:
            v["look"] = data["look_override"] or None
    names = list(data.get("timelines") or [])
    by_name = {}
    for i in range(1, (project.GetTimelineCount() or 0) + 1):
        t = project.GetTimelineByIndex(i)
        if t:
            by_name[t.GetName()] = t
    if data.get("layout") == "one":
        groups = [(by_name.get(names[0]), videos)] if names else []
    else:
        groups = [(by_name.get(n), [v]) for n, v in zip(names, videos)]
    groups = [g for g in groups if g[0] is not None]
    if data.get("only_timeline"):
        groups = [g for g in groups if g[0].GetName() == data["only_timeline"]]
    if not groups:
        raise RuntimeError("Не знайшов таймлайни цього монтажу в проекті DaVinci (можливо, їх перейменували або видалили).")
    out = []
    for tl, vids in groups:
        items = sorted(tl.GetItemListInTrack("video", 1) or [], key=lambda t: t.GetStart())
        flat = [(v, k, sg) for v in vids for k, sg in enumerate(v["segments"])]
        if len(items) != len(flat):
            L("  «%s»: на таймлайні %d шматків, у плані %d — оновлюю по порядку" % (tl.GetName(), len(items), len(flat)))
        ents = []
        for ti, (v, k, sg) in zip(items, flat):
            segs = v["segments"]
            ze = sg.get("zoom_end")
            ents.append((ti, {"look": v.get("look"), "src": str(sg["source"]), "label": "#%d" % (k + 1),
                              "ratio": ze / max(sg.get("zoom", 1.0), 0.01)
                              if ze and abs(ze - sg.get("zoom", 1.0)) > 0.005 else None,
                              "fx": sg.get("fx") or (), "tin": sg.get("tr") if k > 0 else None,
                              "tout": segs[k + 1].get("tr") if k + 1 < len(segs) else None}))
        out.append((tl, ents))
    # спершу таймлайн, відкритий зараз
    if cur_tl is not None:
        cn = cur_tl.GetName()
        out.sort(key=lambda g: 0 if g[0].GetName() == cn else 1)
    return out, skipped


def tune_item(ti, info, P, comp_name):
    """Підкручує значення в уже зібраній композиції. False — потрібна перебудова."""
    comp = comp_of(ti, comp_name)
    if not comp:
        return False
    find = lambda n: comp.FindTool(n)
    bl, mg, hal, tn, gr = (find("SvDreamyBlur"), find("SvDreamy"), find("SvHal"), find("SvTone"), find("SvGrain"))
    if not (bl and mg and hal and tn and gr):
        return False
    m = look_mult(P["lks"])
    look = info.get("look")
    try:
        comp.Lock()
    except Exception:
        pass
    try:
        set_dreamy(bl, mg, P["ov"].get("blur", 0))
        set_halation(hal, P["ov"].get("halation", 0))
        set_tone(tn, P["tone"](info))
        g = STYLE["grain"]
        if g is None:
            g = look_grain(look, m)
            if "grain" in (info.get("fx") or ()):
                g = max(g, min(1.0, 0.4 + 0.6 * P["fxs"]))
        set_grain(gr, g)
        gh = find("SvGhost")
        if gh:
            b = ghost_blend(look, m)
            try:
                gh.SetInput("Blend", max(0.0, b))
            except Exception:
                pass
            _pass(gh, b <= 0.02)
    finally:
        try:
            comp.Unlock()
        except Exception:
            pass
    return True


def restyle(sess, data):
    """«Вигляд»: змінює ефекти на готових таймлайнах без нового монтажу.
    mode: tune — лише підкрутити значення у вузлах (миттєво); rebuild — перебудувати композиції
    (нова фактура, сила вінтажу, ефектів, швидкість переходів); clear — прибрати ефекти «Мого таймлайну».
    Якщо поки йде оновлення прийшла нова зміна (style_gen), поточне перериваємо — далі піде новіше."""
    mode = data.get("mode", "rebuild")
    manual = bool(data.get("manual"))
    comp_name = LOOK_COMP if manual else SVIT_COMP
    gen = str(data.get("gen", ""))
    gen_file = sess.dir / "style_gen"
    fxs, lks, ov, spd, ts, tone = style_params(data, data.get("plan") or {})
    STYLE["live"] = True
    P = {"ov": ov, "lks": lks, "fxs": fxs,
         "tone": (lambda info: manual_tone(ts)) if manual else (lambda info: tone.get(info.get("src")))}
    groups, skipped = style_targets(sess, data)
    total = sum(len(e) for _, e in groups) or 1
    if manual and not sum(len(e) for _, e in groups):
        raise RuntimeError("На відкритому таймлайні немає відеокліпів, які можна змінити."
                           + (" Пропущено шматків зі своїми Fusion-композиціями: %d." % skipped if skipped else ""))
    L("=== Вигляд (%s%s): шматків %d, вінтаж %.0f%%, ефекти %.0f%%, halation %s, дрімі %s, фантоми %.0f%%, "
      "зерно %s, контраст %.0f%%" % (mode, ", мій таймлайн" if manual else "", total, lks * 100, fxs * 100,
                                     ov.get("halation", 0), ov.get("blur", 0), STYLE["ghost"] * 100,
                                     "авто" if STYLE["grain"] is None else "%.0f%%" % (STYLE["grain"] * 100), ts * 100))
    project = sess.project
    orig_tl = project.GetCurrentTimeline()
    stats = {"ok": 0, "fail": 0, "tuned": 0, "rebuilt": 0}
    n = 0
    t0 = time.time()
    aborted = False
    try:
        for tl, ents in groups:
            switched = False
            if orig_tl is None or tl.GetName() != orig_tl.GetName():
                if mode != "tune":
                    project.SetCurrentTimeline(tl)
                    switched = True
            for ti, info in playhead_first(tl, ents):
                if gen and gen_file.exists() and gen_file.read_text().strip() != gen:
                    aborted = True
                    break
                errs = []
                if mode == "clear":
                    try:
                        for nm in (ti.GetFusionCompNameList() or []):
                            if nm == LOOK_COMP:
                                ti.DeleteFusionCompByName(nm)
                    except Exception as e:
                        errs.append(str(e))
                elif info.get("svit_only"):
                    if mode != "clear" and tune_item(ti, info, P, SVIT_COMP):
                        stats["tuned"] += 1
                        if mode == "rebuild":          # фактуру без плану монтажу не перебудувати
                            stats["old"] = stats.get("old", 0) + 1
                    else:
                        stats["old"] = stats.get("old", 0) + 1
                elif mode == "tune" and tune_item(ti, info, P, comp_name):
                    stats["tuned"] += 1
                else:
                    try:
                        # чужі композиції вже відсіяні — стару нашу (і порожні) прибираємо
                        for nm in (ti.GetFusionCompNameList() or []):
                            ti.DeleteFusionCompByName(nm)
                    except Exception:
                        pass
                    _, errs = apply_fusion(ti, info.get("ratio"), info.get("fx") or (), fxs, info["label"],
                                           info.get("look"), lks, info.get("tin"), info.get("tout"),
                                           overlay=ov, tone=P["tone"](info), speed=spd, comp_name=comp_name)
                    stats["rebuilt"] += 1
                stats["fail" if errs else "ok"] += 1
                n += 1
                if n == 1 or n % 3 == 0 or n == total:
                    sess.status(n / float(total), "Оновлюю вигляд · %d з %d" % (n, total))
            if switched and orig_tl is not None:
                project.SetCurrentTimeline(orig_tl)
            if aborted:
                break
    finally:
        STYLE["live"] = False
    L("=== Вигляд %s за %.1f с: підкручено %d, перебудовано %d, з помилками %d, пропущено %d"
      % ("перервано новішою зміною" if aborted else "готово", time.time() - t0, stats["tuned"], stats["rebuilt"],
         stats["fail"], skipped))
    tl_name = groups[0][0].GetName() if groups else ""
    return {"ok": True, "count": n, "fail": stats["fail"], "aborted": aborted, "skipped": skipped,
            "old": stats.get("old", 0),
            "tuned": stats["tuned"], "rebuilt": stats["rebuilt"], "timeline": tl_name}


def timeline_info(sess):
    tl = sess.project.GetCurrentTimeline()
    if not tl:
        return {"ok": True, "timeline": "", "clips": 0, "adjust": 0}
    n = 0
    for idx in range(1, (tl.GetTrackCount("video") or 1) + 1):
        for ti in tl.GetItemListInTrack("video", idx) or []:
            try:
                if ti.GetMediaPoolItem():
                    n += 1
            except Exception:
                pass
    return {"ok": True, "timeline": tl.GetName(), "clips": n, "adjust": len(adjustment_items(tl))}


def build(sess, data):
    project = sess.project
    mp = project.GetMediaPool()
    plan, stamp = data["plan"], data["stamp"]
    size = SIZES.get(data.get("format"), (1080, 1920))
    fxs, lks, ov, spd, ts, tone = style_params(data, plan)
    L("Автоконтраст (сила %.0f%%): %s; швидкість переходів %.0f%%" % (ts * 100, tone, spd * 100))
    stats = {"ok": 0, "fail": 0, "errors": []}
    L("=== Збірка (DaVinci-частина %s): відео %d, формат %s, fps %s, розкладка %s, версія %s" %
      (BRIDGE_VERSION, len(data["plan"].get("videos", [])), data.get("format"), data.get("fps"), data.get("layout"), data.get("version")))
    fps = data.get("fps")
    fps = None if fps in (None, "", "src") else fps
    by_id = {}
    for s in data["sources"]:
        item = sess.items.get(s["uid"])
        if item is None:
            raise RuntimeError("Кліп «%s» більше не знайдено в Media Pool." % s["name"])
        by_id[s["id"]] = dict(s, item=item)

    version = int(data.get("version") or 1)
    vtag = "" if version == 1 else " v%d" % version
    sess.status(0.1, "Створюю таймлайн" + (" (правка %d)" % version if version > 1 else ""))
    fname = "Svit Editor %s" % stamp
    folder = None
    for f in (mp.GetRootFolder().GetSubFolderList() or []):
        if f.GetName() == fname:
            folder = f
            break
    if folder is None:
        folder = mp.AddSubFolder(mp.GetRootFolder(), fname)
    if folder:
        mp.SetCurrentFolder(folder)

    videos = plan["videos"]
    ranges = []
    if data.get("layout") == "one":
        tl = mp.CreateEmptyTimeline("Svit монтаж %s%s" % (stamp, vtag))
        if not tl:
            raise RuntimeError("DaVinci не зміг створити таймлайн.")
        project.SetCurrentTimeline(tl)
        setup_timeline(tl, size, fps)
        gap = int(round(float(data.get("gap", 3.5)) * timeline_fps(tl)))
        pos = tl.GetStartFrame()
        songs = []
        for i, v in enumerate(videos, 1):
            sess.status(0.1 + 0.8 * (i - 1) / len(videos), "Монтую ролик %d з %d" % (i, len(videos)))
            a, b = append_video(mp, tl, v, by_id, size, sess, at=pos, fx_strength=fxs, stats=stats, look_strength=lks,
                                defer_song=songs, overlay=ov, tone=tone, speed=spd)
            pos = b + gap
            name = ("%02d %s" % (i, v["title"]))[:60]
            try:
                tl.AddMarker(a - tl.GetStartFrame(), "Blue", name, v.get("why", ""), 1)
            except Exception:
                pass
            ranges.append((name, tl, a, b - 1))
        for mus, st in songs:          # треки — після всіх відео, щоб не зсували кінець таймлайну
            place_song(sess, mp, tl, mus, st)
        add_subs(mp, plan.get("srt_all"), tl)
        place_text(sess, mp, tl, plan.get("text_all"), plan.get("text_anim"))
    else:
        for i, v in enumerate(videos, 1):
            sess.status(0.1 + 0.8 * (i - 1) / len(videos), "Монтую ролик %d з %d" % (i, len(videos)))
            name = ("%02d %s" % (i, v["title"]))[:56] + vtag
            tl = mp.CreateEmptyTimeline(name)
            if not tl:
                continue
            project.SetCurrentTimeline(tl)
            setup_timeline(tl, size, fps)
            a, b = append_video(mp, tl, v, by_id, size, sess, at=tl.GetStartFrame(), fx_strength=fxs, stats=stats,
                                look_strength=lks, overlay=ov, tone=tone, speed=spd)
            try:
                tl.AddMarker(0, "Blue", "Чому це спрацює", v.get("why", ""), 1)
            except Exception:
                pass
            add_subs(mp, v.get("srt"), tl)
            place_text(sess, mp, tl, v.get("text"), plan.get("text_anim"))
            ranges.append((name, tl, a, b - 1))

    if data.get("auto_render") and ranges:
        sess.status(0.92, "Ставлю ролики на експорт")
        if not EXPORT_DIR.exists():
            EXPORT_DIR.mkdir(parents=True)
        try:
            project.SetCurrentRenderFormatAndCodec("mp4", "H264")
        except Exception:
            pass
        for name, tl, a, b in ranges:
            project.SetCurrentTimeline(tl)
            settings = {"TargetDir": str(EXPORT_DIR), "CustomName": name, "MarkIn": a, "MarkOut": b}
            if size:
                settings.update({"FormatWidth": size[0], "FormatHeight": size[1]})
            project.SetRenderSettings(settings)
            project.AddRenderJob()
        project.StartRendering()
    if ranges:
        project.SetCurrentTimeline(ranges[0][1])
    sess.status(1.0, "Готово")
    L("=== Готово: таймлайнів %d, шматків %d, з Fusion-композицією %d, Fusion успішно %d, з помилками %d, LUT %d" %
      (len(ranges), stats.get("total", 0), stats.get("comps", 0), stats["ok"], stats["fail"], stats.get("lut", 0)))
    tl_names = []
    for r in ranges:
        try:
            n = r[1].GetName()
        except Exception:
            n = r[0]
        if n not in tl_names:
            tl_names.append(n)
    return {"ok": True, "folder": fname, "count": len(ranges), "version": version, "fusion": stats, "timelines": tl_names,
            "log": str(LOG_PATH)}


# ------------------------------------------------------------------ головний цикл

def main():
    if not PY.exists() or not UI.exists():
        alert("Svit Editor не встановлений повністю. Запусти Svit Editor Installer ще раз.")
        return
    resolve = get_resolve()
    if not resolve or not resolve.GetProjectManager().GetCurrentProject():
        alert("Відкрий проект у DaVinci і запусти Svit Editor ще раз.")
        return

    sess = Session(resolve)
    L("Старт. DaVinci %s, проект «%s»" % (resolve.GetVersionString() if hasattr(resolve, "GetVersionString") else "?",
                                         sess.project.GetName()))
    sess.write_sources()
    try:
        (sess.dir / "bridge.json").write_text(json.dumps({"version": BRIDGE_VERSION, "rev": BRIDGE_REV}),
                                              encoding="utf-8")
    except Exception:
        pass

    env = dict(os.environ)
    for k in ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE", "__PYVENV_LAUNCHER__"):
        env.pop(k, None)
    log = open(str(sess.dir / "ui.log"), "w")

    def launch():
        return subprocess.Popen([str(PY), str(UI), "--session", str(sess.dir)],
                                stdout=log, stderr=subprocess.STDOUT, env=env)
    proc = launch()

    try:
        while True:
            if proc.poll() is not None:
                if proc.returncode == 75:   # оновлення: перезапускаємо і саму DaVinci-частину з нового файлу
                    L("Оновлення — перезавантажую DaVinci-частину")
                    return "reload"
                break
            for f in sorted((sess.dir / "cmd").glob("*.json")):
                try:
                    msg = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                f.unlink()
                cid, cmd, data = msg["id"], msg["cmd"], msg.get("data") or {}
                if cmd == "quit":
                    return
                try:
                    if cmd == "refresh":
                        sess.respond(cid, {"sources": sess.collect(data.get("mode", "selected"))})
                    elif cmd == "add_paths":
                        sess.respond(cid, {"sources": sess.resolve_paths(data.get("paths", []))})
                    elif cmd == "clear_dropped":
                        sess.dropped = []
                        sess.respond(cid, {"sources": []})
                    elif cmd == "build":
                        sess.respond(cid, build(sess, data))
                    elif cmd == "restyle":
                        sess.respond(cid, restyle(sess, data))
                    elif cmd == "timeline_info":
                        sess.respond(cid, timeline_info(sess))
                except Exception as e:
                    tb = traceback.format_exc()
                    L("ПОМИЛКА в команді %s:\n%s" % (cmd, tb))
                    sess.respond(cid, {"ok": False, "error": str(e), "details": tb, "log": str(LOG_PATH)})
            time.sleep(0.25)
        if proc.returncode not in (0, None):
            log.close()
            tail = (sess.dir / "ui.log").read_text(encoding="utf-8", errors="ignore")[-4000:]
            L("Вікно закрилось з кодом %s:\n%s" % (proc.returncode, tail))
            crash_report("Вікно Svit Editor закрилось з помилкою (код %s)" % proc.returncode, tail)
    finally:
        # вікно мало закритись саме; якщо зависло — прибираємо через 2 с, щоб не тримати DaVinci
        try:
            for _ in range(20):
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
            if proc.poll() is None:
                L("Вікно не закрилось саме — завершую")
                proc.terminate()
        except Exception:
            pass
        try:
            log.close()
        except Exception:
            pass
        try:
            shutil.rmtree(str(sess.dir / "cmd"), ignore_errors=True)
        except Exception:
            pass


try:
    if main() == "reload" and SCRIPT_PATH.exists():
        g = {"__name__": "__main__", "resolve": get_resolve()}
        if "bmd" in globals():
            g["bmd"] = globals()["bmd"]
        exec(compile(SCRIPT_PATH.read_text(encoding="utf-8"), str(SCRIPT_PATH), "exec"), g)
except Exception as e:
    tb = traceback.format_exc()
    L("Не зміг запуститись:\n" + tb)
    crash_report("Svit Editor не зміг запуститись: %s" % e, tb)
    alert("Svit Editor не зміг запуститись: %s. Звіт відкрито в TextEdit — надішли його Claude." % e)
