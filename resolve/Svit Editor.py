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
BRIDGE_REV = 25      # версія протоколу DaVinci-частини; вікно перевіряє, чи вона свіжа
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
STYLE = {"ghost": 1.0, "grain": 1.0}


def add_overlay(comp, chain, cur, ov):
    """Ефекти «на весь ролик» (як Adjustment Clip): розмиття і halation з однаковою силою на кожному шматку."""
    how = []
    blur = float(ov.get("blur") or 0)
    hal = float(ov.get("halation") or 0)
    if blur > 0:
        # дрімі (Orton): розмита копія накладається на різкий кадр режимом Screen — м'яке сяйво, а не просто мило
        orig = cur[0]
        bl = _tool(comp, "Blur")
        bl.ConnectInput("Input", orig)
        bl.SetInput("XBlurSize", round(8 + 30 * blur, 1))
        mg = _tool(comp, "Merge")
        mg.ConnectInput("Background", orig)
        mg.ConnectInput("Foreground", bl)
        for inp, v in (("ApplyMode", "Screen"),):
            try:
                mg.SetInput(inp, v)
            except Exception:
                pass
        mg.SetInput("Blend", round(0.2 + 0.55 * blur, 3))
        cur[0] = mg
        how.append("dreamy %.0f%%" % (blur * 100))
    if hal > 0:
        if ofx_node(comp, chain, cur, "halation", min(1.0, 0.2 + 0.8 * hal)):
            how.append("halation(стоковий)")
        else:
            g = chain(_tool(comp, "SoftGlow"))
            # halation: червоно-помаранчеве світіння навколо світлих місць
            for inp, v in (("Threshold", 0.55 - 0.25 * hal), ("Gain", 0.4 + 1.6 * hal),
                           ("XGlowSize", 8 + 40 * hal), ("RedScale", 1.0), ("GreenScale", 0.42),
                           ("BlueScale", 0.22)):
                try:
                    g.SetInput(inp, v)
                except Exception:
                    pass
            cur[0] = g
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
            bl = min(1.0, (0.25 + 0.1 * p.get("shift", 1.5) * m) * STYLE["ghost"])    # фантоми (нерухомі)
        elif key == "grain":
            bl = min(1.0, blend * STYLE["grain"])
        elif key == "vignette":
            bl = min(1.0, p.get("vig", 0.3) * 1.3 * m)
        if bl > 0.02 and ofx_node(comp, chain, cur, key, bl):
            used.append(key)
    if used:
        how.append("стокові:" + "+".join(used))
    if "analog" in used:
        p.pop("hblur", None)
    if "glow" in used:
        p.pop("glow", None)
    if "grain" in used:
        p.pop("grain", None)
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
    if p.get("grain") and STYLE["grain"] > 0.02:
        g = chain(_tool(comp, "FilmGrain"))
        try:
            g.SetInput("Blend", min(1.0, STYLE["grain"]))
        except Exception:
            pass
        cur[0] = g
        how.append("grain")
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


def commit_comp(ti, comp, label, verbose=False):
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
                ti.RenameFusionCompByName(added[-1], "Svit")
            except Exception:
                pass
            res += ", активна=%s, лишились=%s" % (added[-1], ti.GetFusionCompNameList())
        try:
            path.unlink()
        except Exception:
            pass
        return res
    except Exception as e:
        return "помилка: %s" % e


def apply_fusion(ti, ratio=None, fx=(), strength=0.5, label="", look=None, look_strength=0.6,
                 tin=None, tout=None, lut_ok=False, verbose=False, overlay=None, tone=None, speed=0.6):
    """Плавний наїзд і ефекти через Fusion: MediaIn → [сповільнення] → [рух/тряска] → [розмиття] →
    [Ч/Б] → [світіння] → [зерно] → [спалах] → MediaOut. Повертає (зроблено, помилки)."""
    fx = set(fx or ()) - {"slowmo"}          # швидкість відео не змінюємо
    look = look if look in LOOKS else None
    tin = tin if tin in TRANSITIONS else None
    tout = tout if tout in TRANSITIONS else None
    overlay = overlay or {}
    has_ov = any(float(v or 0) > 0 for v in overlay.values())
    if not fx and not ratio and not look and not tin and not tout and not has_ov and not tone:
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

        if tone:
            def f():
                bc = chain(_tool(comp, "BrightnessContrast"))
                for inp, v in (("Contrast", tone.get("contrast", 0)), ("Lift", tone.get("lift", 0)),
                               ("Gamma", tone.get("gamma", 1.0))):
                    try:
                        bc.SetInput(inp, float(v))
                    except Exception:
                        pass
                cur[0] = bc
                return "c%+.2f g%.2f" % (tone.get("contrast", 0), tone.get("gamma", 1))
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
        if has_ov:
            step("на весь ролик", lambda: add_overlay(comp, chain, cur, overlay))
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
        if "grain" in fx and look and LOOKS.get(look, {}).get("grain"):
            fx = fx - {"grain"}                 # зерно вже є у фактурі — не накладаємо вдруге
        if STYLE["grain"] <= 0.02:
            fx = fx - {"grain"}
        if "grain" in fx and ofx_node(comp, chain, cur, "grain", min(1.0, (0.4 + 0.6 * k) * STYLE["grain"])):
            done.append("grain(стоковий)")
        elif "grain" in fx:
            def f():
                cur[0] = chain(_tool(comp, "FilmGrain"))
            step("grain", f)
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
        cr = commit_comp(ti, comp, label, verbose)
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


def add_subs(mp, srt):
    if not srt:
        return
    try:
        subs = mp.ImportMedia([srt]) or []
        if subs:
            mp.AppendToTimeline([{"mediaPoolItem": subs[0]}])
    except Exception as e:
        L("Субтитри не додались автоматично: %s" % e)


def style_params(data, plan):
    """Параметри вигляду з налаштувань (спільні для монтажу і для «Вигляд» після монтажу)."""
    fxs = float(data.get("fx_strength", 0.5))
    lks = float(data.get("look_strength", 0.6))
    ov = {k: float(v) for k, v in (data.get("overlay") or {}).items() if float(v or 0) > 0}
    spd = float(data.get("tr_speed", 0.6))
    ts = float(data.get("tone_strength", 0))
    STYLE["ghost"] = float(data.get("ghost", 1.0))
    STYLE["grain"] = float(data.get("grain", 1.0))
    tone = {}
    if ts > 0:
        for sid, t in (plan.get("tone") or {}).items():
            tone[sid] = {"contrast": t.get("contrast", 0) * ts, "lift": t.get("lift", 0) * ts,
                         "gamma": 1 + (t.get("gamma", 1) - 1) * ts}
    return fxs, lks, ov, spd, ts, tone


def restyle(sess, data):
    """«Вигляд» після монтажу: перебудовує Fusion-ефекти на вже готових таймлайнах з новими рівнями.
    Шматки, склейки й монтаж не змінюються, Claude не викликається."""
    project = sess.project
    plan = data["plan"]
    videos = plan.get("videos") or []
    fxs, lks, ov, spd, ts, tone = style_params(data, plan)
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
    only = data.get("only_video")
    if only is not None and data.get("layout") != "one":
        groups = [g for i, g in enumerate(groups) if i == int(only)]
    groups = [g for g in groups if g[0] is not None]
    if not groups:
        raise RuntimeError("Не знайшов таймлайни цього монтажу в проекті DaVinci (можливо, їх перейменували або видалили).")
    total = sum(len(v["segments"]) for _, vs in groups for v in vs) or 1
    done_n, stats = 0, {"ok": 0, "fail": 0, "errors": []}
    L("=== Вигляд: таймлайнів %d, шматків %d, вінтаж %.0f%%, ефекти %.0f%%, halation %s, дрімі %s, фантоми %.0f%%, "
      "зерно %.0f%%, контраст %.0f%%" % (len(groups), total, lks * 100, fxs * 100, ov.get("halation", 0),
                                          ov.get("blur", 0), STYLE["ghost"] * 100, STYLE["grain"] * 100, ts * 100))
    for tl, vids in groups:
        project.SetCurrentTimeline(tl)
        items = sorted(tl.GetItemListInTrack("video", 1) or [], key=lambda t: t.GetStart())
        flat = [(v, k, sg) for v in vids for k, sg in enumerate(v["segments"])]
        if len(items) != len(flat):
            L("  «%s»: на таймлайні %d шматків, у плані %d — оновлюю по порядку" % (tl.GetName(), len(items), len(flat)))
        for ti, (v, k, sg) in zip(items, flat):
            segs = v["segments"]
            ze = sg.get("zoom_end")
            ratio = ze / max(sg.get("zoom", 1.0), 0.01) if ze and abs(ze - sg.get("zoom", 1.0)) > 0.005 else None
            tin = sg.get("tr") if k > 0 else None
            tout = segs[k + 1].get("tr") if k + 1 < len(segs) else None
            tn = tone.get(str(sg["source"]))
            # стара композиція Svit прибирається, нова збирається з новими рівнями
            try:
                for nm in (ti.GetFusionCompNameList() or []):
                    ti.DeleteFusionCompByName(nm)
            except Exception:
                pass
            dn, errs = apply_fusion(ti, ratio, sg.get("fx") or (), fxs, "#%d" % (k + 1), v.get("look"), lks,
                                    tin, tout, overlay=ov, tone=tn, speed=spd)
            stats["ok"] += 1 if not errs else 0
            stats["fail"] += 1 if errs else 0
            done_n += 1
            if done_n % 3 == 0 or done_n == total:
                sess.status(done_n / float(total), "Оновлюю вигляд · %d з %d" % (done_n, total))
    L("=== Вигляд готово: оновлено %d, з помилками %d" % (stats["ok"], stats["fail"]))
    return {"ok": True, "count": done_n, "fail": stats["fail"]}


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
        add_subs(mp, plan.get("srt_all"))
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
            add_subs(mp, v.get("srt"))
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
