"""
Svit Editor — рушій монтажу.

Аналізує матеріал (слова, енергія звуку, кадри), рахує ціну, просить Claude скласти
план монтажу і повертає готовий план для DaVinci. Прогрес і скасування — через callback.
"""
import base64
import io
import json
import math
import re
import time
from pathlib import Path

try:
    import svlog
    _log = svlog.log
except Exception:   # pragma: no cover
    _log = print

HOME = Path.home() / ".svit-editor"
CONFIG = HOME / "config.json"

MAX_FRAMES = 400             # кадрів на весь матеріал (йдуть листами по 4)
FRAME_STEP_SEC = 2.0        # мінімальний крок між кадрами
FRAME_SIZE = 384
MAX_REF_SIZE = 1568
CONTEXT_LIMIT = 180_000   # з запасом від вікна моделі

# Внутрішня валюта Svit Editor: скільки токенів показуємо за $1 реальних витрат на Claude.
# Продаж 1000 токенів за $5 = націнка ×5. Щоб змінити курс — поміняй це число.
TOKENS_PER_USD = 1000

# ціна за 1 млн токенів, USD: (вхід, вихід); для Haiku — дві ціни залежно від довжини запиту
PRICES = {
    "claude-sonnet-5-5": {"in": 2.0, "out": 10.0},
    "claude-opus-5-5": {"in": 4.0, "out": 20.0},
    "claude-haiku-5-5": {"in": 0.10, "out": 0.50, "in_long": 0.50, "out_long": 2.50,
                         "long_from": 100_000},
}

# швидкість розпізнавання слів: секунд роботи на 1 секунду відео (CPU Mac, приблизно)
WHISPER_SPEED = {"small": 0.10, "medium": 0.22, "large-v3": 0.50}


PACE_TEXT = {
    "fast": "ШВИДКА (TikTok/Reels): шматки здебільшого 1–2.5 с, склейки на біт і акценти, мінімум пауз; "
            "для мовлення став tighten: true.",
    "normal": "НОРМАЛЬНА: шматки 3–6 с, ритм тримається; паузи довші за секунду прибирай (tighten: true для мовлення).",
    "slow": "ПОВІЛЬНА (YouTube/влог): довгі плани 6–20 с, зберігай природні паузи й дихання розмови; "
            "tighten лише для дуже довгих пауз; без хаотичних склейок.",
}
SEG_LEN = {"fast": 1.8, "normal": 4.5, "slow": 12.0}


def motion_max(strength):
    """Наскільки сильним буде плавний рух при динамічному зумі (0.02…0.15 = 2…15%)."""
    return 0.02 + max(0, min(100, float(strength))) / 100.0 * 0.13


def zoom_text(s):
    crop = s.get("zoom_crop", True)
    dyn = s.get("zoom_dynamic", True)
    out = []
    if crop:
        out.append("КАДРУВАННЯ увімкнене: для кожного шматка можна задати статичний zoom (1.0–1.6) і pan_x/pan_y, "
                   "щоб тримати в кадрі головне (людину, сцену). Це просто кадр, не ефект.")
    else:
        out.append("КАДРУВАННЯ вимкнене: zoom 1.0, pan_x і pan_y 0.")
    if dyn:
        d = motion_max(s.get("zoom_strength", 35))
        out.append(f"ДИНАМІЧНИЙ ЗУМ увімкнений: на КОЖНОМУ шматку задай ЛЕГКИЙ плавний рух — "
                   f"zoom_end відрізняється від zoom на 0.02–{d:.2f} (повільний наїзд або від'їзд), щоб картинка жила. "
                   f"Рух має бути ледь помітним. НЕ ріж один план на шматки заради зуму.")
    else:
        out.append("ДИНАМІЧНИЙ ЗУМ вимкнений: zoom_end не використовуй.")
    return " ".join(out)


VIDEO_GAP = 3.5   # пауза між роликами на спільному таймлайні, с

FX_INFO = {
    "shake": "легкий поштовх кадру (без обертання) — на ударах, дропах, криках залу",
    "flash": "спалах (різке висвітлення, що згасає) на початку шматка — сильні долі, різкі зміни, кульмінації",
    "fade_in": "проявлення з темряви — початок ролика, нова частина, тиша перед дропом",
    "blur_in": "вхід з розмиття — початок ролика або нової частини, мрійливі моменти",
    "rgb": "RGB-розшарування (глітч) на початку шматка — різкі склейки, біт, тривога, цифрова естетика",
    "glow": "світіння — сцена, світло, прожектори, вечірні кадри",
    "bw": "чорно-біле — драматичні, ностальгічні, контрастні моменти",
    "grain": "плівкове зерно — атмосфера, документальність",
}

TRANS_INFO = {
    "zoom": "наїзд-перехід: кінець плану різко наближається з розмиттям, новий виїжджає з наближення — енергійно, на біт",
    "whip": "свайп (whip pan): кадр різко «змахується» вбік з розмиттям руху — динаміка, зміна місця",
    "dip": "затемнення: через чорне — зміна частини, пауза, lost wave, драма",
    "white": "через біле (спалах-перехід) — кульмінація, дроп, яскраві зміни",
    "glitch": "глітч: кольори розшаровуються і смикаються — цифрова естетика, агресивний біт",
    "blur": "через розмиття — м'яко, мрійливо, спогад",
}


def tr_text(s):
    allowed = [f for f in (s.get("tr_allowed") or []) if f in TRANS_INFO]
    if not s.get("tr_on") or not allowed:
        return "ВИМКНЕНІ: поле tr не використовуй (усі склейки прямі)."
    lines = "; ".join(f"{f} — {TRANS_INFO[f]}" for f in allowed)
    return (f"УВІМКНЕНІ. Дозволені: {lines}. Поле tr у шматку — перехід З ПОПЕРЕДНЬОГО шматка в цей. "
            f"Більшість склейок — прямі (без tr); перехід став приблизно на кожну 3–5-ту склейку: на сильних "
            f"долях, зміні частини пісні, зміні місця чи настрою. Не став tr на першому шматку відео.")


LOOKS = {
    "vhs": ("Касета VHS", "розмиті кольори, що «з'їжджають», смуга трекінгу, тремтіння, шум; монтаж як домашній архів або кліп 90-х"),
    "camcorder": ("Камкордер 90-х", "Hi8/MiniDV: трохи м'яко, теплі кольори, легке розшарування; аматорська зйомка, бекстейдж, тусовка"),
    "film8": ("Плівка 8 мм", "сімейна хроніка: тепло, сильне зерно, віньєтка, мерехтіння і хитання кадру"),
    "film16": ("Плівка 16 мм", "інді-кіно, документалістика: м'яке зерно, теплі кольори, легке мерехтіння"),
    "crt": ("Старий телевізор", "рядки розгортки, сильна віньєтка, світіння екрана, холодний відтінок"),
    "lostwave": ("Lost wave", "вицвілі, розмиті, «знайдені» кадри: підняті чорні, м'який фокус, світіння, тривожна ностальгія"),
    "bwfilm": ("Старе ч/б кіно", "чорно-біле, контрастно, сильне мерехтіння і зерно, віньєтка"),
    "dream": ("Vaporwave / мрія", "рожево-бузковий відтінок, сильне світіння, м'якість; dreamcore, vaporwave"),
}


def look_text(s):
    lk = s.get("look") or "none"
    opts = "; ".join(f"{k} — {v[0]}: {v[1]}" for k, v in LOOKS.items())
    if lk in LOOKS:
        return (f"ЗАДАНИЙ АВТОРОМ: {lk} ({LOOKS[lk][0]}) — накладається на весь ролик автоматично. "
                f"Монтуй у дусі цієї фактури: {LOOKS[lk][1]}. Поле look не потрібне.")
    if lk == "auto":
        return (f"ОБИРАЄШ ТИ: для кожного відео постав поле look — одне з: {opts}; або \"none\", якщо вінтаж "
                f"не пасує. Орієнтуйся на запит, референси й настрій матеріалу.")
    return (f"ВИМКНЕНО. Став поле look у відео ТІЛЬКИ якщо автор прямо просить таку фактуру в запиті "
            f"(можливі: {opts}).")


def fx_text(s):
    allowed = [f for f in (s.get("fx_allowed") or []) if f in FX_INFO]
    if not s.get("fx_on") or not allowed:
        return "ВИМКНЕНІ: поле fx не використовуй."
    lines = "; ".join(f"{f} — {FX_INFO[f]}" for f in allowed)
    return (f"УВІМКНЕНІ. Дозволені: {lines}. Додавай їх полем fx (список, максимум 2 на шматок) там, де вони "
            f"підсилюють момент і ритм; не на кожному шматку — приблизно на кожному 3–4-му. "
            f"Якщо є референси — повторюй їхню манеру.")


def cinematic_text(s):
    if not s.get("cinematic"):
        return "вимкнено."
    c = max(0, min(100, int(_f(s.get("cinematic_level", 60), 60))))
    lvl = ("легкий" if c <= 35 else "виразний" if c <= 70 else "повний — як у кіно")
    return (f"УВІМКНЕНО ({c}/100, {lvl}). Монтуй як кліп / кіно, а не як TikTok-нарізку: "
            "довші мотивовані плани, що «дихають»; повільні плавні наїзди замість різких зумів; композиція "
            "(правило третин, повітря в кадрі); загальний → середній → крупний на емоції; склейки на дії, на "
            "фразах і рядках пісні, а не на кожному ударі; найкращі крупні плани — на ключові рядки й приспів; "
            "B-roll і деталі (руки, світло, силует) між куплетами; переходи — рідко, м'які (dip, blur); жодних "
            "різких трясок. Якщо матеріал — кілька дублів однієї пісні (кліп, лірик-відео), обирай для кожного "
            "рядка найкращий дубль і найкращий ракурс, чергуй дублі, щоб кожна склейка давала новий кадр.")


def abstract_text(a):
    a = max(0, min(100, int(_f(a, 25))))
    if a <= 15:
        lvl = ("КЛАСИКА: чиста, логічна розповідь; хронологія і зрозумілість; жодних експериментів, "
               "правила монтажу — суворо.")
    elif a <= 40:
        lvl = ("ТРОХИ ТВОРЧОСТІ: основа класична, але додавай 1–2 знахідки на ролик — склейку за формою "
               "(match cut), контраст «тиша → вибух», несподіваний перший кадр.")
    elif a <= 65:
        lvl = ("ТВОРЧО: асоціативний монтаж — поєднуй кадри за формою, кольором, рухом, змістом; можна "
               "нелінійно (фінал на початку, флешбеки); контрапункт між звуком і картинкою; варіюй ритм "
               "сміливо (довгий план → серія мікрошматків). Кожен ролик має мати ідею, яку можна назвати.")
    elif a <= 85:
        lvl = ("ЕКСПЕРИМЕНТ: кліпове й артхаусне мислення — монтаж атракціонів (Ейзенштейн), ефект Кулешова, "
               "свідомі jump cut'и, ритмічні «заїкання» склейок на біт, різкі контрасти масштабу, "
               "розірвана хронологія, візуальні рими. Правила монтажу можна ламати, але кожне порушення — "
               "навмисне і з ідеєю.")
    else:
        lvl = ("АБСТРАКЦІЯ: максимальна свобода — монтаж як сон, пам'ять або знайдена плівка; lost wave, "
               "dreamcore, глітч, ліричні «порожні» кадри (деталі, світло, руки, натовп у розфокусі), "
               "тягучі плани поруч із кадрами на 1 удар, повторювані мотиви (різні моменти з однаковою формою). "
               "Сенс — у настрої та ритмі, не в сюжеті. Але все одно без повторів тих самих моментів.")
    return f"{a}/100 — {lvl}"


class Cancelled(Exception):
    pass


def price_of(model, tin, tout):
    p = PRICES.get(model, PRICES["claude-sonnet-5-5"])
    if "long_from" in p and tin > p["long_from"]:
        return tin / 1e6 * p["in_long"] + tout / 1e6 * p["out_long"]
    return tin / 1e6 * p["in"] + tout / 1e6 * p["out"]


def load_cfg():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cfg(cfg):
    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        CONFIG.chmod(0o600)
    except Exception:
        pass


def add_spend(usd):
    cfg = load_cfg()
    month = time.strftime("%Y-%m")
    spend = cfg.get("spend", {})
    spend[month] = round(spend.get(month, 0.0) + usd, 4)
    cfg["spend"] = spend
    save_cfg(cfg)
    return spend[month]


def hms(t):
    t = int(t)
    return f"{t // 3600:01}:{t % 3600 // 60:02}:{t % 60:02}"


# ======================================================================= аналіз

class Transcriber:
    def __init__(self, model_name, language):
        self.model_name, self.language, self.model = model_name, language, None

    def load(self):
        if self.model is None:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(self.model_name, device="cpu", compute_type="int8")

    def run(self, path, on_pct, check):
        self.load()
        audio = decode_audio_16k(path, check)
        if audio is None or len(audio) < 1600:
            return [], []
        segments, info = self.model.transcribe(audio, language=self.language or None,
                                               word_timestamps=True, vad_filter=True)
        segs, words = [], []
        for s in segments:
            check()
            on_pct(min(1.0, s.end / max(info.duration, 1)))
            segs.append({"start": round(s.start, 2), "end": round(s.end, 2),
                         "text": s.text.strip()})
            for w in s.words or []:
                if w.word.strip():
                    words.append({"start": float(w.start), "end": float(w.end),
                                  "word": w.word.strip()})
        return segs, words


def decode_audio_16k(path, check=lambda: None):
    """Звук файлу як моно 16 кГц float32 — читаємо самі, щоб не залежати від версії PyAV у faster-whisper."""
    import av
    import numpy as np
    try:
        c = av.open(str(path))
    except Exception:
        return None
    try:
        if not c.streams.audio:
            return None
        res = av.AudioResampler(format="s16", layout="mono", rate=16000)
        chunks, n = [], 0
        for frame in c.decode(c.streams.audio[0]):
            for f in res.resample(frame):
                chunks.append(f.to_ndarray().ravel())
            n += 1
            if n % 500 == 0:
                check()
        try:
            for f in res.resample(None):
                chunks.append(f.to_ndarray().ravel())
        except Exception:
            pass
        if not chunks:
            return None
        return np.concatenate(chunks).astype(np.float32) / 32768.0
    finally:
        c.close()


def src_off(src):
    """Звідки в файлі починається використана частина (обрізаний на таймлайні кліп або In/Out у Media Pool)."""
    try:
        return max(0.0, float(src.get("offset") or 0))
    except (TypeError, ValueError):
        return 0.0


def window_words(segs, words, src):
    """Слова й фрази лише з використаної частини файлу, час — від її початку."""
    w0 = src_off(src)
    if not w0 and not src.get("trimmed"):
        return segs, words
    w1 = w0 + float(src["duration"])
    sh = lambda x: dict(x, start=round(x["start"] - w0, 3), end=round(x["end"] - w0, 3))
    return ([sh(x) for x in segs if x["end"] > w0 and x["start"] < w1],
            [sh(x) for x in words if x["start"] >= w0 - 0.05 and x["end"] <= w1 + 0.05])


def window_frames(path, times, on_pct, check, src):
    """grab_frames у межах використаної частини: час на вході й виході — від її початку."""
    w0 = src_off(src)
    got = grab_frames(path, [t + w0 for t in times], on_pct, check)
    return [(round(max(0.0, t - w0), 3), j) for t, j in got] if w0 else got


def audio_energy(path, on_pct, check, duration):
    """Гучність по секундах, 0–9."""
    import av
    import numpy as np
    try:
        c = av.open(str(path))
    except Exception:
        return []
    if not c.streams.audio:
        c.close()
        return []
    rate = 8000
    res = av.AudioResampler(format="s16", layout="mono", rate=rate)
    levels, acc, n = [], np.zeros(0, dtype=np.float32), 0
    try:
        for frame in c.decode(c.streams.audio[0]):
            for f in res.resample(frame):
                a = f.to_ndarray().astype(np.float32).ravel() / 32768.0
                acc = np.concatenate([acc, a])
                while len(acc) >= rate:
                    chunk, acc = acc[:rate], acc[rate:]
                    rms = float(np.sqrt(np.mean(chunk ** 2)))
                    levels.append(20 * math.log10(rms + 1e-9))
            n += 1
            if n % 200 == 0:
                check()
                on_pct(min(1.0, len(levels) / max(duration, 1)))
    except Cancelled:
        raise
    except Exception:
        pass
    finally:
        c.close()
    if not levels:
        return []
    lo = float(np.percentile(levels, 10))
    hi = float(np.percentile(levels, 98))
    span = max(hi - lo, 1e-6)
    return [int(max(0, min(9, round(9 * (v - lo) / span)))) for v in levels]


def energy_text(levels):
    return "\n".join(f"[{hms(i)}] " + "".join(str(x) for x in levels[i:i + 60])
                     for i in range(0, len(levels), 60))


def grab_frames(path, times, on_pct, check):
    import av
    out = []
    try:
        c = av.open(str(path))
    except Exception:
        return out
    if not c.streams.video:
        c.close()
        return out
    c.streams.video[0].thread_type = "AUTO"
    tag_rot = 0
    try:
        tag_rot = int(float((c.streams.video[0].metadata or {}).get("rotate", 0)))
    except Exception:
        pass
    for i, t in enumerate(times):
        check()
        try:
            c.seek(int(t * 1_000_000))
            fr = next(c.decode(video=0))
            img = fr.to_image()
            # телефонне відео зберігається «лежачи» з позначкою повороту — повертаємо, як показує DaVinci,
            # інакше Claude бачить вертикальні кліпи на боці
            ang = 0
            try:
                ang = int(round(float(getattr(fr, "rotation", 0) or 0)))
            except Exception:
                ang = 0
            if not ang and tag_rot:
                ang = -tag_rot
            ang = ((ang + 180) % 360) - 180
            if ang in (90, -90, 180, -180):
                img = img.rotate(ang, expand=True)
            img.thumbnail((FRAME_SIZE, FRAME_SIZE))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, "JPEG", quality=70)
            out.append((float(fr.time) if fr.time is not None else t, buf.getvalue()))
        except Exception:
            pass
        on_pct((i + 1) / max(len(times), 1))
    c.close()
    return out


def _dhash(jpg):
    from PIL import Image
    im = Image.open(io.BytesIO(jpg)).convert("L").resize((9, 8))
    px = list(im.getdata())
    bits = 0
    for r in range(8):
        for c in range(8):
            bits = (bits << 1) | (1 if px[r * 9 + c] > px[r * 9 + c + 1] else 0)
    return bits


def visual_groups(sources, frames, thr=11):
    """Групи джерел, що знімають те саме (схожі кадри за перцептивним хешем). {id: № групи}."""
    hs = {}
    for src in sources:
        fr = frames.get(src["id"]) or []
        if fr:
            hs[src["id"]] = [_dhash(j) for _, j in fr]
    ids = list(hs)
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            ha, hb = hs[a], hs[b]
            close = sum(1 for x in ha if min(bin(x ^ y).count("1") for y in hb) <= thr)
            if close >= max(1, 0.5 * min(len(ha), len(hb))):
                parent[find(a)] = find(b)
    groups = {}
    for i in ids:
        groups.setdefault(find(i), []).append(i)
    out, g = {}, 0
    for members in groups.values():
        if len(members) > 1:
            g += 1
            for m in members:
                out[str(m)] = g
    return out


def visual_groups_text(job):
    vg = job.get("vgroups") or {}
    by = {}
    for sid, g in vg.items():
        by.setdefault(g, []).append(int(sid))
    return "; ".join("група %d: №%s" % (g, ", №".join(str(x) for x in sorted(m))) for g, m in sorted(by.items()))


def contact_sheet(items):
    """До 4 кадрів в одному зображенні 2×2 з підписом часу — більше кадрів для Claude без перевищення лімітів."""
    from PIL import Image, ImageDraw
    ims = [Image.open(io.BytesIO(j)).convert("RGB") for _, j in items]
    w = max(i.size[0] for i in ims)
    h = max(i.size[1] for i in ims)
    cols = 2 if len(ims) > 1 else 1
    rows = (len(ims) + 1) // 2 if len(ims) > 1 else 1
    sheet = Image.new("RGB", (cols * w + (cols - 1) * 6, rows * h + (rows - 1) * 6), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for k, (im, (t, _)) in enumerate(zip(ims, items)):
        x, y = (k % cols) * (w + 6), (k // cols) * (h + 6)
        sheet.paste(im, (x, y))
        lab = "%d) %.1fs" % (k + 1, t)
        d.rectangle([x, y, x + 8 + 9 * len(lab), y + 22], fill=(0, 0, 0))
        d.text((x + 5, y + 5), lab, fill=(255, 255, 80))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=72)
    return buf.getvalue()


def tone_of(jpegs):
    """Автоконтраст: яскравість кадрів джерела → поправки контрасту, чорного і гами.
    Пласке (лог) відео отримує більше контрасту, темне — трохи світліше, підняті чорні опускаються."""
    from PIL import Image
    import numpy as np
    lums = []
    for jpg in jpegs[:24]:
        try:
            im = Image.open(io.BytesIO(jpg)).convert("L")
            im.thumbnail((160, 160))
            lums.append(np.asarray(im, dtype=np.float32).ravel() / 255.0)
        except Exception:
            continue
    if not lums:
        return None
    y = np.concatenate(lums)
    lo, hi, mean = float(np.percentile(y, 1)), float(np.percentile(y, 99)), float(y.mean())
    spread = max(0.05, hi - lo)
    contrast = max(0.0, min(0.45, (0.88 - spread) * 0.9))
    lift = max(-0.15, min(0.0, -(lo - 0.02) * 0.7)) if lo > 0.02 else 0.0
    gamma = math.log(max(mean, 0.02)) / math.log(0.34)
    gamma = max(0.85, min(1.25, gamma))
    return {"lo": round(lo, 3), "hi": round(hi, 3), "mean": round(mean, 3),
            "contrast": round(contrast, 3), "lift": round(lift, 3), "gamma": round(gamma, 3)}


def match_tones(tone):
    """Вирівнювання між відео: кожне джерело підтягуємо до спільної середини (медіана всіх) —
    яскравість через гаму, розмах через контраст, підняте чорне опускаємо. Темне світлішає,
    пересвічене темнішає, пласке отримує контраст, надто контрастне — м'якшає."""
    vals = [t for t in tone.values() if t and "mean" in t]
    if not vals:
        return tone
    med = lambda xs: sorted(xs)[len(xs) // 2]
    t_mean = max(0.38, min(0.5, med([t["mean"] for t in vals])))
    t_spread = max(0.7, min(0.92, med([t["hi"] - t["lo"] for t in vals])))
    out = {}
    for sid, t in tone.items():
        if not t or "mean" not in t:
            out[sid] = t
            continue
        spread = max(0.05, t["hi"] - t["lo"])
        contrast = max(-0.2, min(0.45, (t_spread - spread) * 0.9))
        gamma = math.log(max(t["mean"], 0.02)) / math.log(t_mean)
        gamma = max(0.8, min(1.3, gamma))
        lift = max(-0.15, min(0.0, -(t["lo"] - 0.02) * 0.7)) if t["lo"] > 0.02 else 0.0
        out[sid] = dict(t, contrast=round(contrast, 3), gamma=round(gamma, 3), lift=round(lift, 3), matched=True)
    return out


def image_bytes(data, max_side=MAX_REF_SIZE):
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=85)
    return buf.getvalue()


def b64img(data):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(data).decode()}}


# ======================================================================= оцінка

def estimate(sources_total_sec, n_sources, settings, n_shots, n_refs=0):
    """Приблизні токени, ціна й час ще до старту. Повертає dict."""
    minutes = sources_total_sec / 60.0
    tin = 2000
    if settings.get("transcribe", True):
        tin += minutes * 300
    tin += minutes * 35
    frames = 0
    if settings.get("frames", True):
        frames = min(MAX_FRAMES, int(sources_total_sec / FRAME_STEP_SEC) + n_sources * 2) if sources_total_sec else 0
        tin += frames * 200
    tin += n_shots * 1600 + n_refs * 1700
    tin = min(tin, CONTEXT_LIMIT)
    nv = settings.get("num_videos_n") or 5
    vid_len = {"fast": 30, "normal": 45, "slow": 120}.get(settings.get("pace", "normal"), 45)
    segs = vid_len / SEG_LEN.get(settings.get("pace", "normal"), 4.5)
    tout = 800 + nv * int(250 + segs * 60)
    model = settings.get("model", "claude-sonnet-5-5")
    cost = price_of(model, tin, tout)
    secs = 20 + sources_total_sec * 0.02 + frames * 0.15
    if settings.get("transcribe", True):
        secs += sources_total_sec * WHISPER_SPEED.get(settings.get("whisper_model", "medium"), 0.22)
    secs += 15 + tout / 60 + n_refs * 25
    return {"tokens_in": int(tin), "tokens_out": int(tout), "cost": cost,
            "cost_low": cost * 0.6, "cost_high": cost * 1.5, "seconds": int(secs)}


# ======================================================================= Claude

SYSTEM_PROMPT = """Ти — досвідчений монтажер відео для соцмереж (TikTok, Reels, Shorts, YouTube).
Тобі дають матеріал (одне або багато відео) і запит автора. Головне — зробити саме те,
що просить автор. Його запит важливіший за будь-які загальні правила.

Про матеріал ти знаєш:
- текст з таймкодами (що кажуть або співають), якщо він є;
- карту енергії звуку: рядки по хвилині, кожна цифра 0–9 — гучність однієї секунди
  (9 — найгучніше: дроп, крик залу, кульмінація; 0 — тиша);
- кадри з відео з підписами «джерело N, час»;
- скріни-приклади від автора, якщо він їх додав (як має виглядати результат);
- РЕФЕРЕНСИ — відео, які подобаються автору (темп склейок, кадри з різних планів).
  Перейми з них темп (довжину планів і частоту склейок), кадрування, рух і настрій монтажу.
  Не копіюй їхній зміст. Якщо темп референсу відрізняється від налаштувань динаміки — орієнтуйся на референс,
  якщо автор не просить іншого.

Що ти можеш робити з кожним шматком (segment):
- брати будь-який відрізок будь-якого джерела: source, start, end (секунди від початку файлу);
- zoom: 1.0 — кадр заповнює формат; 1.3 — наближення на 30% (кадрування);
- pan_x: від -1 (показати ліву частину кадру) до 1 (праву), 0 — центр;
  pan_y: від -1 (верх) до 1 (низ). Використовуй кадри, щоб тримати в кадрі головне;
- zoom_end: якщо задано — плавний рух від zoom до zoom_end протягом шматка
  (ТІЛЬКИ коли увімкнений динамічний зум);
- tighten: true — автоматично вирізати паузи між словами всередині шматка;
- fx: список ефектів для шматка (лише дозволені в налаштуваннях), напр. ["shake"] або ["flash", "glow"];
- tr: перехід з попереднього шматка в цей (лише дозволені в налаштуваннях), напр. "zoom"; без tr — пряма склейка;
- shot: крупність плану, ОБОВ'ЯЗКОВО — "wide" (загальний: вся сцена/місце), "medium" (середній: людина по пояс,
  група), "close" (крупний: обличчя, інструмент), "detail" (деталь: руки, струни, мікрофон, світло),
  "crowd" (публіка/реакція), "pov" (від першої особи/з рук). Визначай за кадрами; якщо кадрів немає — за назвою
  файлу й текстом, і тоді чергуй джерела частіше.
Для кожного відео є поле look — вінтажна фактура (див. налаштування).
Швидкість відео НІКОЛИ не змінюється (без сповільнень і прискорень). Переходи — лише через поле tr.
Кольорокорекції немає (крім фактури look).
Темп нарізки і правила зумів задані в НАЛАШТУВАННЯХ — дотримуйся їх.
Якщо автор просить те, чого немає, зроби найближче можливе і поясни в "notes".

ГРАМАТИКА МОНТАЖУ (як у професійного монтажера, а не випадкові шматки):
- Зміна плану на кожній склейці: чергуй крупність (загальний → середній → крупний → деталь → реакція).
  Не став підряд два шматки однакової крупності з одного джерела — це jump cut (лише навмисно, при високій
  абстрактності). Сусідні плани мають відрізнятися масштабом або ракурсом (правило 30°).
- Ролик має структуру: зачіпка (найсильніший або найзагадковіший кадр) → орієнтація (загальний, де ми) →
  розвиток (середні й крупні, деталі) → кульмінація (найкращий момент на найвищій енергії/дропі) → фінал
  (емоційний крупний план, реакція залу або тихий загальний).
- Склейка на дії: ріж у момент руху (удар по струні, змах руки, стрибок, поворот голови) — рух ховає склейку.
- Дія → реакція: після яскравого моменту на сцені — публіка або обличчя.
- Мотивація: кожен новий план дає нову інформацію або емоцію. Немає причини — немає склейки.
- Довжина плану залежить від змісту: загальні й емоційні крупні — довші, деталі — коротші.
  Варіюй довжину, рівний «метроном» склейок нудний (крім навмисного ритму під біт).
- Напрямок руху й погляду між сусідніми планами не має «стрибати» без причини.
- Не обривай жест, фразу чи рух на півдорозі; не починай з порожнього кадру без мети.

СТИЛІ, ЯКІ ТИ ЗНАЄШ (застосовуй, коли автор просить або дозволяє висока абстрактність):
- lost wave / found footage: як знайдена стара плівка — довгі тягучі плани, розфокус, порожні кадри (світло,
  стеля, натовп у русі), обірвані моменти, тривожна ностальгія, фактура VHS/плівки, мало подій — багато настрою;
- dreamcore / weirdcore / liminal: дивні тихі деталі, повтори схожих форм, відчуття сну, м'які входи з темряви;
- vaporwave: повільно, мрійливо, світіння, ретро;
- кліповий монтаж: ритм понад сюжет, візуальні рими, різкі контрасти, склейки строго на біт;
- монтаж атракціонів / асоціативний: поєднання кадрів, що разом дають нове значення (ефект Кулешова);
- документальний / vérité: довші живі плани, реакції, мінімум прикрас;
- глітч / цифровий хаос: мікрошматки, RGB-розшарування, тряска, різкі обриви.

Правила монтажу:
- КОЖНА склейка має міняти картинку: інше джерело або момент того самого джерела мінімум на 3 с далі.
  Ніколи не став підряд два шматки, де другий продовжує перший (той самий план) — це виглядає як збій.
- Жоден момент не повторюється: шматки не перекриваються в часі ні в одному відео, ні між відео.
- РІЗНОМАНІТТЯ: використай якомога більше різних джерел і різних моментів усередині довгих джерел (початок,
  середина, кінець), а не перші секунди. Ніколи не став підряд два шматки з одного джерела або з однієї
  «групи схожих» (той самий об'єкт/локація — список нижче). Якщо об'єкт мусить повторитись — візьми інший момент
  і явно іншу крупність: zoom 1.25–1.5 з pan_x/pan_y, щоб це читалось як новий план, а не повтор.
- Якщо є кілька камер одного концерту, різні камери в той самий момент — це різні кадри, їх можна чергувати.
- Межі шматків не мають різати слово чи фразу посередині, якщо автор не просить інакше.
- Перший шматок кожного відео має чіпляти з першої секунди.
- Не повторюй той самий момент у різних відео, якщо автор не просить.
- Таймкоди мають бути в межах тривалості джерела.

Якщо є МУЗИКА — монтаж іде під трек:
- замість end вказуй beats — скільки ударів триває шматок (1, 2, 4, 8…); start — звідки брати у джерелі;
- шматки йдуть підряд від першого удару фрагмента; сума beats = кількості ударів фрагмента;
- склейки на ударах, особливо на початках тактів (|); на високій енергії — 1–2 удари на шматок,
  на спокійних місцях — 4–8; на дропі — найшвидші склейки;
- звук з відео не звучить (звучить трек), тож tighten не потрібен; обирай рух у кадрі, що пасує до ритму.

Відповідай ТІЛЬКИ валідним JSON без пояснень навколо:
{"notes": "коротко: що ти зробив, яка ідея монтажу і що не вдалося",
 "rotate": {},
 "videos": [
  {"title": "коротка назва", "caption": "підпис для посту", "hashtags": ["#..."],
   "why": "чому це спрацює (1 речення)", "look": "none",
   "segments": [
     [1, 125.4, 131.0, "wide", 1.0, 1.06, 0, 0, ["shake"], "zoom"],
     [2, 40.2, 42.0, "close", 1.2, 1.25, 0.3, -0.2, [], ""]
   ]}
 ]}
КОЖЕН ШМАТОК — КОМПАКТНИЙ МАСИВ (так коротше і дешевше), поля строго в такому порядку:
[source, start, end, shot, zoom, zoom_end, pan_x, pan_y, fx, tr]
- якщо є МУЗИКА — третє поле не end, а beats (ціле число ударів): [1, 125.4, 2, "wide", ...];
- zoom_end = zoom, якщо руху немає; fx = [] і tr = "", якщо їх немає;
- для мовлення, де треба вирізати паузи, додай 11-м полем true (tighten).
- rotate: подивись на кадри кожного джерела — якщо відео знято догори дриґом (небо внизу, люди догори ногами,
  текст перевернутий) — {"№": 180}. Вертикальне чи горизонтальне відео — це НЕ поворот, його не чіпай.
  Програма сама поверне ці кліпи. Якщо все рівно — "rotate": {}.
Пиши JSON компактно, без зайвих пробілів і переносів; notes, why і caption — коротко."""


def compress_segments(segs, window):
    """Склеює фрази у вікна по window секунд, щоб вмістити дуже довгий матеріал."""
    out, cur = [], None
    for s in segs:
        if cur and s["start"] - cur["start"] < window:
            cur["end"] = s["end"]
            cur["text"] += " " + s["text"]
        else:
            if cur:
                out.append(cur)
            cur = dict(s)
    if cur:
        out.append(cur)
    for c in out:
        if len(c["text"]) > 220:
            c["text"] = c["text"][:220] + "…"
    return out


def build_content(job, data, frames, refs, seg_window=0, frame_step=1, ref_videos=None):
    s = job["settings"]
    head = [
        f"ЗАПИТ АВТОРА:\n{job['prompt'].strip() or '(порожній — зроби найкращі короткі відео)'}",
        "",
        "НАЛАШТУВАННЯ:",
        f"- скільки відео зробити: {s['num_videos']}",
        f"- довжина кожного відео: {s['video_length']}",
        f"- формат кадру: {s['format_label']}",
        f"- розміщення: {s['layout_label']}",
        f"- динаміка (темп нарізки): {PACE_TEXT.get(s.get('pace', 'normal'), PACE_TEXT['normal'])}",
        f"- зуми: {zoom_text(s)}",
        f"- абстрактність ідей: {abstract_text(s.get('abstract', 25))}",
        f"- cinematic: {cinematic_text(s)}",
        ("- МОВА ТЕКСТІВ: усі title, caption, hashtags, why і notes пиши АНГЛІЙСЬКОЮ (автор користується англійським інтерфейсом)."
         if s.get("ui_lang") == "en" else "- мова текстів (title, caption, why, notes): українська."),
        f"- ефекти: {fx_text(s)}",
        f"- переходи: {tr_text(s)}",
        f"- вінтаж / фактура (look): {look_text(s)}",
        "",
        "МАТЕРІАЛ:",
    ]
    for src in job["sources"]:
        head.append(f"- джерело {src['id']}: «{src['name']}», {hms(src['duration'])}")
    content = [{"type": "text", "text": "\n".join(head)}]
    for src in job["sources"]:
        d = data[src["id"]]
        parts = [f"\n===== ДЖЕРЕЛО {src['id']}: «{src['name']}» ====="]
        segs = compress_segments(d["segs"], seg_window) if seg_window else d["segs"]
        if segs:
            parts.append("Текст:")
            parts += [f"[{x['start']:.1f}–{x['end']:.1f}] {x['text']}" for x in segs]
        elif s.get("transcribe"):
            parts.append("Текст: слів не знайдено.")
        if d["energy"]:
            parts.append("Енергія звуку (цифра = 1 секунда):")
            parts.append(energy_text(d["energy"]))
        content.append({"type": "text", "text": "\n".join(parts)})
        fr = frames.get(src["id"], [])[::frame_step]
        for i0 in range(0, len(fr), 4):
            chunk = fr[i0:i0 + 4]
            content.append({"type": "text", "text": f"Кадри джерела {src['id']} (зліва направо, згори вниз): "
                            + ", ".join(f"{k + 1}) {t:.1f} с" for k, (t, _) in enumerate(chunk))})
            try:
                content.append(b64img(contact_sheet(chunk) if len(chunk) > 1 else chunk[0][1]))
            except Exception:
                for _, jpg in chunk:
                    content.append(b64img(jpg))
    for i, jpg in enumerate(refs, 1):
        content.append({"type": "text", "text": f"Скрін-приклад від автора №{i}:"})
        content.append(b64img(jpg))
    import refs as _r
    for i, rv in enumerate(ref_videos or [], 1):
        content.append({"type": "text", "text": _r.ref_text(i, rv)})
        for t, jpg in rv["frames"][::frame_step]:
            content.append({"type": "text", "text": f"Кадр референсу №{i}, {t:.1f} с"})
            content.append(b64img(jpg))
    if job.get("vgroups"):
        content.append({"type": "text", "text": "ГРУПИ СХОЖИХ ДЖЕРЕЛ (знімають той самий об'єкт чи локацію — "
                        "не став їх поруч, з кожної групи бери кілька найкращих моментів, а не все підряд): "
                        + visual_groups_text(job)})
    if job.get("music_info"):
        import music as _m
        content.append({"type": "text", "text": _m.music_text(job["music_info"])})
        if job.get("lyrics_timing"):
            ms0 = float(job["music_info"].get("start", 0))
            ll = [f"{max(0, ln['start'] - ms0):.1f}–{ln['end'] - ms0:.1f} с: {ln['text']}"
                  for ln in job["lyrics_timing"] if ln["end"] > ms0][:80]
            if ll:
                content.append({"type": "text", "text": "РЯДКИ ПІСНІ (час від початку ролика; субтитри з ними додасть "
                                "програма — сам їх не пиши). Став склейки на початках рядків і фраз, крупні плани "
                                "на ключових словах:\n" + "\n".join(ll)})
        if job.get("sync"):
            ms = job["music_info"]["start"]
            lines = []
            for sid, sy in sorted(job["sync"].items(), key=lambda x: int(x[0])):
                lines.append(f"№{sid}{' (ЛІПСІНК — автор співає в кадр)' if sy.get('lip') else ''}: секунда джерела t "
                             f"звучить як момент пісні t+{sy['offset']:.2f} с; "
                             f"дубль покриває фрагмент від {max(0, sy['from'] - ms):.1f} до {sy['to'] - ms:.1f} с")
            content.append({"type": "text", "text":
                            "ДУБЛІ, СИНХРОНІЗОВАНІ З ПІСНЕЮ (lip-sync). Для цих джерел start можеш ставити будь-який — "
                            "програма сама вирівняє кожен шматок так, щоб спів і рухи збігались із треком. Твоя задача — "
                            "вибрати, ЯКИЙ дубль/ракурс показати на кожному відрізку (секунди — від початку фрагмента):\n"
                            + "\n".join(lines)
                            + ("\n\nЛІПСІНК: автор позначив відео, де він співає під трек. Чергуй ліпсінк з вайбовими "
                               "кадрами з решти матеріалу: ліпсінк — на ключових рядках, приспіві й сильних долях "
                               "(30–60% часу ролика), вайбові шматки — між ними, на паузах і інструменталі. Шматки "
                               "ліпсінку завжди ставлять у синхроні з піснею."
                               if any(sy.get("lip") for sy in job["sync"].values()) else "")})
    content.append({"type": "text", "text": "Склади план монтажу у форматі JSON."})
    return content


# ======================================================================= нарізка

def tighten(seg, words, max_gap=0.45, pad=0.08):
    s, e = seg["start"], seg["end"]
    inside = [w for w in words if w["start"] >= s - 0.05 and w["end"] <= e + 0.05]
    if not inside:
        return [seg]
    groups, cur = [], [inside[0]["start"], inside[0]["end"]]
    for w in inside[1:]:
        if w["start"] - cur[1] > max_gap:
            groups.append(cur)
            cur = [w["start"], w["end"]]
        else:
            cur[1] = w["end"]
    groups.append(cur)
    out, last_end = [], -1.0
    for a, b in groups:
        a, b = max(s, a - pad), min(e, b + pad)
        if out and a <= last_end:
            out[-1]["end"] = b
        else:
            out.append(dict(seg, start=a, end=b))
        last_end = b
    return out


def trim_overlap(st, en, used):
    """Обрізає відрізок [st, en] так, щоб він не перекривав уже використані. Повертає (st, en) або None."""
    for a, b in sorted(used):
        if en <= a or st >= b:
            continue
        if st >= a and en <= b:
            return None
        if st < a < en <= b:
            en = a
        elif a <= st < b < en:
            st = b
        else:
            en = a
    return (st, en) if en - st >= 0.3 else None


GAP = 1.5   # мінімальна відстань між моментами одного джерела, с


def _f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


SHOTS = ("wide", "medium", "close", "detail", "crowd", "pov")
SHOT_UA = {"wide": "загальний", "medium": "середній", "close": "крупний", "detail": "деталь",
           "crowd": "публіка", "pov": "з рук"}


def seg_from_list(a, music=False):
    """Компактний шматок [source, start, end|beats, shot, zoom, zoom_end, pan_x, pan_y, fx, tr, tighten] → dict."""
    a = list(a) + [None] * 11
    d = {"source": a[0], "start": a[1], "shot": a[3], "zoom": a[4], "pan_x": a[6] or 0, "pan_y": a[7] or 0,
         "fx": a[8] if isinstance(a[8], list) else ([a[8]] if isinstance(a[8], str) and a[8] else []),
         "tr": a[9] or "", "tighten": bool(a[10])}
    if music:
        d["beats"] = a[2]
    else:
        d["end"] = a[2]
    if a[5] is not None and a[4] is not None and abs(_f(a[5]) - _f(a[4], 1.0)) > 0.004:
        d["zoom_end"] = a[5]
    return d


def plan_beats(v):
    """Скільки ударів музики покривають шматки ролика з плану Claude (до чистки)."""
    n = 0
    for x in v.get("segments") or []:
        d = seg_from_list(x, True) if isinstance(x, (list, tuple)) else (x if isinstance(x, dict) else {})
        n += max(1, int(round(_f(d.get("beats"), 2))))
    return n


def grammar_check(segs, title=""):
    """Журнал: скільки jump cut'ів (той самий план підряд) і яка різноманітність крупності."""
    jumps = sum(1 for a, b in zip(segs, segs[1:])
                if a["source"] == b["source"] and a.get("shot") and a.get("shot") == b.get("shot"))
    kinds = sorted(set(x.get("shot", "?") for x in segs))
    _log(f"Граматика «{title}»: шматків {len(segs)}, крупності {kinds}, jump cut'ів {jumps}")
    return jumps


def _vkey(job, sid):
    """Ключ «схожості»: група схожих джерел або саме джерело."""
    g = (job.get("vgroups") or {}).get(str(sid))
    return ("g", g) if g else ("s", sid)


def spread_raw(raw, job):
    """Не ставимо підряд шматки з одного джерела чи групи схожих — переставляємо порядок.
    Синхронізовані з піснею (ліпсінк) можуть іти підряд — це безперервний спів."""
    sync = job.get("sync") or {}
    sid_of = lambda sg: int(_f(sg.get("source", 1), 1))
    pool, out = list(raw), []
    moved = 0
    while pool:
        if out:
            pk = _vkey(job, sid_of(out[-1]))
            c = pool[0]
            both_sync = str(sid_of(c)) in sync and str(sid_of(out[-1])) in sync
            if _vkey(job, sid_of(c)) == pk and not both_sync:
                j = next((k for k in range(1, len(pool)) if _vkey(job, sid_of(pool[k])) != pk), None)
                if j is not None:
                    out.append(pool.pop(j))
                    moved += 1
                    continue
        out.append(pool.pop(0))
    if moved:
        _log(f"Різноманіття: переставлено шматків {moved}, щоб схожі кадри не йшли підряд")
    return out


def free_start(spans, dur, want, sdur):
    """Найближчий до want вільний відрізок довжини dur у джерелі (поза вже взятими моментами)."""
    best, pos = None, 0.0
    gaps = []
    for a, b in sorted(spans):
        if a - GAP - pos >= dur:
            gaps.append((pos, a - GAP - dur))
        pos = max(pos, b + GAP)
    if sdur - pos >= dur:
        gaps.append((pos, sdur - dur))
    for lo, hi in gaps:
        st = min(max(want, lo), hi)
        if best is None or abs(st - want) < abs(best - want):
            best = st
    return best


def clean_segments(raw, job, data, used, beat_from=0, beat_to=None):
    """Чистить шматки одного відео: межі, повтори, склейки «план сам із собою», біти музики, тиша.
    used — {джерело: [(start, end)]} уже зайняті моменти (по всьому плану)."""
    durations = {src["id"]: src["duration"] for src in job["sources"]}
    s = job.get("settings", {})
    crop, dyn = s.get("zoom_crop", True), s.get("zoom_dynamic", True)
    mus = job.get("music_info")
    grid = mus["grid"] if mus else None
    if grid is not None and beat_to is None:
        beat_to = len(grid) - 1
    cursor = beat_from
    segs = []
    _auto_zoom = {}
    raw = [seg_from_list(x, grid is not None) if isinstance(x, (list, tuple)) else x for x in raw]
    raw = spread_raw([x for x in raw if isinstance(x, dict)], job)
    seen_key = {}            # що вже було в цьому ролику: ключ схожості → кадрування
    reframed = [0]

    def reframe(item, reuse=False):
        """Повтор того самого об'єкта — інше кадрування, щоб читалось як новий план."""
        k = _vkey(job, item["source"])
        prev = seen_key.get(k)
        if crop and (prev is not None or reuse):
            pz = prev["zoom"] if prev else item["zoom"]
            if pz < 1.15:
                nz = 1.3
                side = -1 if (prev or {}).get("pan_x", 0) > 0 else 1
                item["zoom"], item["pan_x"], item["pan_y"] = nz, round(0.35 * side, 2), round(-0.15 * side, 2)
            else:
                item["zoom"], item["pan_x"], item["pan_y"] = 1.0, 0.0, 0.0
            if "zoom_end" in item:
                item["zoom_end"] = round(item["zoom"] + (0.06 if item["zoom"] < 1.2 else -0.06), 3)
            reframed[0] += 1
        seen_key[k] = {"zoom": item["zoom"], "pan_x": item.get("pan_x", 0)}
    for sg in raw:
        sid = int(_f(sg.get("source", 1), 1))
        if sid not in durations:
            continue
        sdur = durations[sid]
        st = max(0.0, _f(sg.get("start")))
        z = max(1.0, min(1.6, _f(sg.get("zoom"), 1.0) or 1.0)) if crop else 1.0
        allowed = set(f for f in (s.get("fx_allowed") or []) if f in FX_INFO) if s.get("fx_on") else set()
        fx = [f for f in (sg.get("fx") or []) if isinstance(f, str) and f in allowed][:2]
        item = {"source": sid, "zoom": round(z, 3),
                "pan_x": max(-1.0, min(1.0, _f(sg.get("pan_x")))) if crop else 0.0,
                "pan_y": max(-1.0, min(1.0, _f(sg.get("pan_y")))) if crop else 0.0}
        if fx:
            item["fx"] = fx
        tr_ok = set(f for f in (s.get("tr_allowed") or []) if f in TRANS_INFO) if s.get("tr_on") else set()
        trv = str(sg.get("tr") or "").lower().strip()
        if trv in tr_ok and segs:
            item["tr"] = trv
        shot = str(sg.get("shot") or "").lower().strip()
        if shot in SHOTS:
            item["shot"] = shot
        if dyn and sg.get("zoom_end"):
            ze = max(1.0, min(z + 0.2, _f(sg.get("zoom_end"), z)))
            if abs(ze - z) > 0.005:
                item["zoom_end"] = round(ze, 3)
        if dyn and "zoom_end" not in item:
            # Claude не задав рух — додаємо самі, щоб динамічний зум точно був (наїзд / від'їзд по черзі)
            amp = round(motion_max(s.get("zoom_strength", 35)) * (0.45 if s.get("cinematic") else 0.7), 3)
            _auto_zoom["n"] = _auto_zoom.get("n", 0) + 1
            if _auto_zoom["n"] % 2:
                item["zoom_end"] = round(z + amp, 3)
            else:
                item["zoom"], item["zoom_end"] = round(z + amp, 3), round(z, 3)
        if grid is not None:
            # монтаж під музику: тривалість = ціла кількість ударів
            if cursor >= beat_to:
                break
            nb = max(1, int(round(_f(sg.get("beats"), 2))))
            nxt = min(beat_to, cursor + nb)
            dur = grid[nxt] - grid[cursor]
            sy = (job.get("sync") or {}).get(str(sid))
            synced = False
            if sy:
                # дубль синхронізований з піснею: беремо саме той момент, де звучить ця частина треку
                song_t = mus["start"] + grid[cursor]
                cand = song_t - sy["offset"]
                if cand >= 0 and cand + dur <= sdur:
                    st, synced = cand, True
            cursor = nxt
            reuse = False
            if not synced:
                if st + dur > sdur:
                    st = max(0.0, sdur - dur)
                if any(st < b + GAP and st + dur > a - GAP for a, b in used.get(sid, [])):
                    fs = free_start(used.get(sid, []), dur, st, sdur)
                    if fs is not None:
                        st = fs             # той самий момент уже був — беремо вільний відрізок цього джерела
                    else:
                        reuse = True        # вільного місця немає — хоча б інше кадрування
            else:
                item["sync"] = True
            reframe(item, reuse)
            item.update(start=round(st, 3), end=round(st + dur, 3), beat=cursor)
            used.setdefault(sid, []).append((st, st + dur))
            segs.append(item)
            continue
        en = min(sdur, _f(sg.get("end"), st))
        if en - st < 0.3:
            continue
        # склейка «план сам із собою»: продовження попереднього шматка — зливаємо в один
        if segs and segs[-1]["source"] == sid and abs(segs[-1]["end"] - st) < 0.35:
            prev = segs[-1]
            prev["end"] = round(en, 3)
            if "zoom_end" in item:
                prev["zoom_end"] = item["zoom_end"]
            used[sid][-1] = (used[sid][-1][0], en)
            continue
        padded = [(a - GAP, b + GAP) for a, b in used.get(sid, [])]
        cut = trim_overlap(st, en, padded)
        if not cut:
            continue
        st, en = cut
        reframe(item)
        item.update(start=round(st, 3), end=round(en, 3), tighten=bool(sg.get("tighten")))
        used.setdefault(sid, []).append((st, en))
        segs.append(item)
    if reframed[0]:
        _log(f"Різноманіття: інше кадрування для повторних об'єктів — {reframed[0]} шматків")
    if grid is not None and segs and cursor < beat_to:
        extra = grid[beat_to] - grid[cursor]
        if extra > TAIL_STRETCH:
            # план закінчився раніше за пісню — не розтягуємо один кліп на півхвилини, а добиваємо
            # короткими шматками в темпі решти монтажу (спершу ліпсінк саме на цей момент пісні)
            cursor = autofill_tail(segs, job, used, durations, grid, cursor, beat_to, reframe)
        if cursor < beat_to:
            last = segs[-1]
            extra = grid[beat_to] - grid[cursor]
            last["end"] = round(min(durations[last["source"]], last["end"] + extra), 3)
    out = []
    for it in segs:
        if it.pop("tighten", False) and data[it["source"]]["words"]:
            pieces = [dict(p, start=round(p["start"], 3), end=round(p["end"], 3))
                      for p in tighten(it, data[it["source"]]["words"]) if p["end"] - p["start"] >= 0.2]
            for p in pieces[1:]:
                p.pop("tr", None)
                p.pop("fx", None)
            out += pieces
        else:
            out.append(it)
    rot = job.get("rotate") or {}
    for it in out:
        if str(it["source"]) in rot:
            it["rot"] = rot[str(it["source"])]
    return out


TAIL_STRETCH = 4.0   # хвіст до стількох секунд просто дотягуємо останнім кліпом


def autofill_tail(segs, job, used, durations, grid, cursor, beat_to, reframe):
    """Заповнює удари від cursor до beat_to короткими шматками. Повертає новий cursor."""
    import statistics
    sync = job.get("sync") or {}
    mus = job.get("music_info") or {}
    beats_used = [x.get("beat", 0) for x in segs]
    steps = [b - a for a, b in zip([0] + beats_used, beats_used) if b - a > 0]
    nb = max(1, min(8, int(round(statistics.median(steps))) if steps else 2))
    tmpl = {k: segs[-1].get(k) for k in ("look",) if k in segs[-1]}
    sources = [sid for sid in durations if durations[sid] >= 1.0]
    if not sources:
        return cursor
    added, k = 0, 0
    prev_sid = segs[-1]["source"]
    while cursor < beat_to:
        nxt = min(beat_to, cursor + nb)
        dur = grid[nxt] - grid[cursor]
        song_t = mus.get("start", 0) + grid[cursor]
        pick = None
        # 1) ліпсінк-дубль, де саме зараз звучить ця частина пісні
        sync_items = list(sync.items())
        for j in range(len(sync_items)):
            sid_s, sy = sync_items[(added + j) % len(sync_items)]
            sid = int(sid_s)
            st = song_t - sy["offset"]
            if sid != prev_sid and sid in durations and st >= 0 and st + dur <= durations[sid]:
                pick, synced = (sid, st), True
                break
        # 2) інакше — по колу різні джерела, вільний момент
        if pick is None:
            synced = False
            for _ in range(len(sources)):
                sid = sources[k % len(sources)]
                k += 1
                if sid == prev_sid or dur > durations[sid]:
                    continue
                want = (durations[sid] - dur) * ((k * 0.37) % 1.0)
                st = free_start(used.get(sid, []), dur, want, durations[sid])
                if st is not None:
                    pick = (sid, st)
                    break
        if pick is None:
            break
        sid, st = pick
        item = {"source": sid, "start": round(st, 3), "end": round(st + dur, 3), "beat": nxt,
                "zoom": 1.0, "pan_x": 0, "pan_y": 0, "fx": [], "tr": "", "auto": True}
        item.update(tmpl)
        if synced:
            item["sync"] = True
        reframe(item)
        used.setdefault(sid, []).append((st, st + dur))
        segs.append(item)
        prev_sid, cursor = sid, nxt
        added += 1
    if added:
        _log(f"Автодобивка кінця: {added} шматків по ~{nb} ударів (план Claude закінчився раніше за пісню)")
    return cursor


def pick_look(want, s, prev=None):
    fixed = s.get("look") or "none"
    if fixed in LOOKS:
        return fixed
    want = str(want or "").lower().strip()
    if want in LOOKS:
        return want
    if want == "none":
        return None
    return prev


def plan_rotation(plan, job):
    """Перевернуті джерела від Claude → {id: кут}; зберігається в job для наступних правок."""
    rot = {k: v for k, v in (job.get("rotate") or {}).items() if v == 180}
    raw = plan.get("rotate")
    if isinstance(raw, dict):
        ids = {str(x["id"]) for x in job.get("sources", [])}
        for k, v in raw.items():
            try:
                a = int(round(float(v)))
            except Exception:
                continue
            a = {270: -90, -270: 90, -180: 180}.get(a, a)
            if str(k) in ids:
                if a == 180:            # лише догори дриґом; «на боці» — це звичайне вертикальне відео
                    rot[str(k)] = a
                elif a == 0:
                    rot.pop(str(k), None)
    if rot != (job.get("rotate") or {}):
        names = {str(x["id"]): x.get("name") for x in job.get("sources", [])}
        _log("Поворот джерел: " + ", ".join(f"«{names.get(k, k)}» {v}°" for k, v in rot.items()))
    job["rotate"] = rot
    return rot


def clean_plan(plan, job, data, prev_videos=None):
    videos, used = [], {}
    s = job.get("settings", {})
    rot = plan_rotation(plan, job)
    for n, v in enumerate(plan.get("videos", [])):
        segs = clean_segments(v.get("segments", []), job, data, used)
        for x in segs:
            if str(x["source"]) in rot:
                x["rot"] = rot[str(x["source"])]
        if segs:
            prev = (prev_videos[n].get("look") if prev_videos and n < len(prev_videos) else None)
            title = v.get("title", f"Відео {len(videos) + 1}")
            grammar_check(segs, title)
            videos.append({"title": title,
                           "caption": v.get("caption", ""), "hashtags": v.get("hashtags", []),
                           "why": v.get("why", ""), "segments": segs, "look": pick_look(v.get("look"), s, prev),
                           "duration": round(sum(x["end"] - x["start"] for x in segs), 2)})
    raw_n = len(plan.get("videos", []))
    _log(f"План: Claude дав відео {raw_n}, після чистки {len(videos)}; "
         f"шматків {[len(v['segments']) for v in videos]}; переходів "
         f"{sum(1 for v in videos for x in v['segments'] if x.get('tr'))}; ефектів "
         f"{sum(1 for v in videos for x in v['segments'] if x.get('fx'))}")
    if job.get("music_info"):
        for v in videos:
            v["music"] = {k: job["music_info"][k] for k in ("path", "start", "end")}
    return videos


def s_smooth(job):
    return bool(job.get("settings", {}).get("zoom_dynamic", True))


# ======================================================================= слова пісні → субтитри

def _norm_word(w):
    import re
    w = w.lower().replace("’", "'").replace("ʼ", "'").replace("`", "'")
    return re.sub(r"[^\w]+", "", w)


def lyric_lines(text):
    """Рядки тексту пісні: порожні рядки й позначки на кшталт [Приспів] пропускаємо, довгі рядки ділимо."""
    import re
    out = []
    tag = re.compile(r"^(приспів|куплет|бридж|програш|вступ|кода|аутро|інтро|chorus|verse|bridge|intro|outro|"
                     r"pre-?chorus|hook|приспев|куплет)\s*\d*\s*[:.\-]?\s*(\(?x?\d\)?)?$", re.I)
    for ln in (text or "").splitlines():
        ln = ln.strip()
        # службові позначки: «|» праворуч, «(2)», «x2», «×2»
        ln = re.sub(r"\s*\|+\s*", " ", ln)
        ln = re.sub(r"\s*(\(\s*[x×]?\s*\d+\s*\)|\b[x×]\s*\d+)\s*$", "", ln, flags=re.I).strip()
        if not ln or re.fullmatch(r"[\[(].*[\])]", ln) or tag.match(ln):
            continue
        words = ln.split()
        while len(" ".join(words)) > 42 and len(words) > 3:
            cut = len(words) // 2
            commas = [k + 1 for k, w in enumerate(words[:-1]) if w.endswith((",", ";", "—", "-", ":"))]
            if commas:
                cut = min(commas, key=lambda k: abs(k - len(words) / 2.0))
            out.append(" ".join(words[:cut]))
            words = words[cut:]
        out.append(" ".join(words))
    return out


def align_lyrics(lines, heard, span_start, span_end):
    """Прив'язує рядки тексту до слів, які розпізнав Whisper у треку (час — у секундах треку).
    Збіги слів дають «якорі», решту слів розставляємо між якорями пропорційно довжині.
    Повертає ([{start,end,text}], частка впізнаних слів)."""
    import difflib
    lw = []                                  # (індекс рядка, слово)
    for i, ln in enumerate(lines):
        for w in ln.split():
            lw.append((i, w))
    if not lw:
        return [], 0.0
    a = [_norm_word(w) for _, w in lw]
    b = [_norm_word(h["word"]) for h in heard]
    times = [None] * len(lw)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            if a[blk.a + k]:
                h = heard[blk.b + k]
                times[blk.a + k] = (h["start"], h["end"])
    # нечіткі збіги для одиночних слів між якорями (Whisper часто чує слово трохи інакше)
    j = 0
    for i in range(len(a)):
        if times[i] is None and a[i]:
            lo = max((times[k][1] for k in range(i) if times[k]), default=span_start)
            for jj in range(len(b)):
                if heard[jj]["start"] >= lo - 0.01 and difflib.SequenceMatcher(None, a[i], b[jj]).ratio() >= 0.75:
                    nxt = next((times[k][0] for k in range(i + 1, len(a)) if times[k]), span_end)
                    if heard[jj]["end"] <= nxt + 0.01:
                        times[i] = (heard[jj]["start"], heard[jj]["end"])
                    break
    known = sum(1 for t in times if t)
    ratio = known / float(len(lw))
    if known == 0:
        return [], 0.0
    # інтерполяція між якорями за довжиною слів
    idx = [i for i, t in enumerate(times) if t]
    first, last = idx[0], idx[-1]
    rate = max(0.18, (times[last][1] - times[first][0]) / max(1, sum(len(a[i]) + 2 for i in range(first, last + 1))))
    for i in range(first - 1, -1, -1):
        d = (len(a[i]) + 2) * rate
        times[i] = (max(span_start, times[i + 1][0] - d), times[i + 1][0])
    for i in range(last + 1, len(times)):
        d = (len(a[i]) + 2) * rate
        times[i] = (times[i - 1][1], min(span_end + 30, times[i - 1][1] + d))
    for p, q in zip(idx, idx[1:]):
        if q - p > 1:
            t0, t1 = times[p][1], times[q][0]
            w = [len(a[i]) + 2 for i in range(p + 1, q)]
            tot, acc = float(sum(w)) or 1.0, 0.0
            for k, i in enumerate(range(p + 1, q)):
                s0 = t0 + (t1 - t0) * acc / tot
                acc += w[k]
                times[i] = (s0, t0 + (t1 - t0) * acc / tot)
    res = []
    for li, ln in enumerate(lines):
        ts = [times[k] for k, (i, _) in enumerate(lw) if i == li]
        if ts:
            res.append({"start": ts[0][0], "end": ts[-1][1], "text": ln})
    for k in range(len(res) - 1):            # рядок висить до наступного (але не довше +1.2 с після слів)
        res[k]["end"] = min(max(res[k]["end"], res[k]["start"] + 0.6), res[k + 1]["start"], res[k]["end"] + 1.2) \
            if res[k + 1]["start"] > res[k]["start"] else res[k]["end"]
    if res:
        res[-1]["end"] = max(res[-1]["end"], res[-1]["start"] + 0.8)
    return res, ratio


def transcribe_song(path, start, end, model_name, language, prompt="", check=lambda: None):
    """Розпізнає спів у вибраному шматку треку (час слів — у секундах треку)."""
    audio = decode_audio_16k(path, check)
    if audio is None:
        return []
    a0 = max(0.0, float(start) - 3.0)
    seg = audio[int(a0 * 16000): int((float(end) + 3.0) * 16000)]
    if len(seg) < 1600:
        return []
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(seg, language=language or None, word_timestamps=True, vad_filter=False,
                                   initial_prompt=(prompt or "")[:220] or None, condition_on_previous_text=False)
    words = []
    for sg in segments:
        check()
        for w in sg.words or []:
            if w.word.strip():
                words.append({"start": a0 + float(w.start), "end": a0 + float(w.end), "word": w.word.strip()})
    return words


def lyric_chunks(timing, mus_start, offset, length):
    """Рядки пісні для одного ролика: час треку → час ролика (+offset на спільному таймлайні)."""
    out = []
    for ln in timing or []:
        st, en = ln["start"] - mus_start, ln["end"] - mus_start
        if en <= 0.05 or st >= length - 0.05:
            continue
        out.append([{"start": offset + max(0.0, st), "end": offset + min(length, en), "word": ln["text"]}])
    return out


def strip_marks(chunks):
    """Зірочки (*ключове слово*) потрібні лише Svit-тексту — зі звичайних субтитрів прибираємо."""
    out = []
    for ch in chunks:
        out.append([dict(w, word=w["word"].replace("*", "")) for w in ch])
    return out


def fmt_ts(t):
    ms = int(round(max(0.0, t) * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def caption_chunks(segs, data, offset, n=3):
    mapped, pos = [], offset
    for sg in segs:
        for w in data[sg["source"]]["words"]:
            if w["start"] >= sg["start"] and w["end"] <= sg["end"] + 0.05:
                mapped.append({"start": pos + w["start"] - sg["start"],
                               "end": pos + min(w["end"], sg["end"]) - sg["start"],
                               "word": w["word"]})
        pos += sg["end"] - sg["start"]
    chunks, cur = [], []
    for w in mapped:
        if cur and (len(cur) >= n or w["start"] - cur[-1]["end"] > 0.6):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def write_srt(path, chunk_lists, upper=True):
    chunks = [c for cl in chunk_lists for c in cl]
    lines = []
    for i, ch in enumerate(chunks):
        st = ch[0]["start"]
        en = max(ch[-1]["end"], st + 0.4)
        if i + 1 < len(chunks):
            en = min(en, chunks[i + 1][0]["start"])
        lines.append(f"{i + 1}\n{fmt_ts(st)} --> {fmt_ts(en)}\n"
                     + (lambda t: t.upper() if upper else t)(" ".join(w["word"] for w in ch)) + "\n")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return bool(chunks)


# ======================================================================= запуск

class Job:
    """Один монтаж. progress(stage, overall 0..1, message, extra) викликається з цього потоку."""

    STAGES = ["prepare", "listen", "sound", "look", "refs", "plan", "build", "done"]

    def __init__(self, job, out_dir, progress, cancel_event):
        self.job, self.out = job, Path(out_dir)
        self.progress, self.cancel = progress, cancel_event
        self.s = job["settings"]
        self.cost = 0.0
        self.out.mkdir(parents=True, exist_ok=True)
        total = sum(src["duration"] for src in job["sources"]) or 1.0
        self.total = total
        w_listen = total * WHISPER_SPEED.get(self.s.get("whisper_model", "medium"), 0.22) \
            if self.s.get("transcribe") else 0
        n_frames = min(MAX_FRAMES, int(total / FRAME_STEP_SEC)) if self.s.get("frames") else 0
        n_refs = len(job.get("refs") or [])
        self.weights = {"prepare": 3, "listen": w_listen, "sound": total * 0.02 + 2,
                        "look": n_frames * 0.15, "refs": n_refs * 12, "plan": 25 + 15, "build": 8}
        self.warnings = []
        self.wsum = sum(self.weights.values())

    def check(self):
        if self.cancel.is_set():
            raise Cancelled()

    def report(self, stage, frac, msg, **extra):
        done = 0.0
        for st in self.STAGES:
            if st == stage:
                break
            done += self.weights.get(st, 0)
        overall = (done + self.weights.get(stage, 0) * max(0.0, min(1.0, frac))) / self.wsum
        if msg != getattr(self, "_last_msg", None):
            self._last_msg = msg
            _log(f"[{stage}] {msg}")
        self.progress(stage, min(0.99, overall), msg, extra)

    def _sync_takes(self, _m, song_path):
        """Lip-sync: для кожного джерела шукаємо, яке місце пісні в ньому звучить.
        Якщо автор позначив ліпсінк-відео — слухаємо лише їх і з м'якшим порогом."""
        out = {}
        try:
            env = _m.song_envelope(song_path)
        except Exception as e:
            _log(f"Синхрон дублів: трек не прочитався: {e!r}")
            return out
        marked = set(self.s.get("lipsync") or [])
        auto_lip = bool(self.s.get("lip_auto")) and not marked     # «у відео є ліпсінк» — шукаємо самі
        srcs = self.job["sources"]
        lips = [x for x in srcs if x.get("name") in marked]
        todo = lips or srcs
        mu = self.job.get("music") or {}
        win = (float(mu.get("start", 0)), float(mu.get("end", 30)))
        for k, src in enumerate(todo, 1):
            self.check()
            self.report("sound", (k - 1) / max(1, len(todo)), f"Синхронізую з піснею · {k} з {len(todo)}",
                        file=src.get("name"))
            lip = src.get("name") in marked
            try:
                off, conf = _m.sync_offset(song_path, src["path"], env)
                if off is not None:
                    off = round(off + src_off(src), 3)   # зсув відносно початку використаної частини
            except Cancelled:
                raise
            except Exception as e:
                _log(f"Синхрон «{src['name']}»: {e!r}")
                continue
            ok = off is not None and conf >= (0.7 if lip else 1.0 if auto_lip else 1.2)
            lip = lip or (auto_lip and ok)
            covers = off is not None and (off < win[1] and off + src["duration"] > win[0])
            _log(f"Синхрон «{src['name']}»{' [ліпсінк]' if lip else ''}: зсув {off} с, впевненість {conf} → "
                 f"{'так' if ok else 'ні'}{'' if covers or not ok else ' (але поза вибраним шматком пісні)'}")
            if ok:
                out[str(src["id"])] = {"offset": off, "conf": conf, "from": round(max(0.0, off), 2),
                                       "to": round(off + src["duration"], 2), "lip": lip}
                if lip and not covers:
                    self.warnings.append(f"Ліпсінк «{src['name']}» знято на інший шматок пісні "
                                         f"({off:.0f}–{off + src['duration']:.0f} с треку) — зсунь виділення треку туди.")
        for src in lips:
            if str(src["id"]) not in out:
                self.warnings.append(f"Ліпсінк «{src['name']}»: не вдалося почути в ньому трек — він піде як "
                                     f"звичайні кадри. Перевір, що в цьому відео чути пісню.")
        if auto_lip and not out:
            self.warnings.append("Ліпсінк: у жодному відео не вдалося почути трек. Познач ліпсінк-відео вручну "
                                 "(«Текст» → «Ліпсінк-відео») — для позначених Svit слухає уважніше.")
        elif auto_lip:
            _log(f"Ліпсінк знайдено автоматично: {len(out)} відео")
        if not lips and not auto_lip:
            if out and len(out) < len(srcs):
                self.warnings.append(f"Синхрон: з піснею вирівняно {len(out)} з {len(srcs)} відео "
                                     f"(в інших не чути треку — вони підуть як звичайні кадри).")
        return out

    def run(self):
        job, s = self.job, self.s
        cfg = load_cfg()
        self.report("prepare", 0.5, "Готуюсь до аналізу")
        n = len(job["sources"])

        tr = None
        if s.get("transcribe"):
            tr = Transcriber(s.get("whisper_model", "medium"), s.get("language"))
            self.report("listen", 0, "Завантажую модель розпізнавання мови")
            tr.load()

        data, done_sec = {}, 0.0
        for k, src in enumerate(job["sources"], 1):
            segs, words = [], []
            if tr:
                def lp(f, base=done_sec, dur=src["duration"], k=k, name=src["name"]):
                    self.report("listen", (base + f * dur) / self.total,
                                f"Слухаю слова · відео {k} з {n}", file=name)
                segs, words = window_words(*tr.run(src["path"], lp, self.check), src)
            data[src["id"]] = {"segs": segs, "words": words, "energy": []}
            done_sec += src["duration"]

        done_sec = 0.0
        for k, src in enumerate(job["sources"], 1):
            def sp(f, base=done_sec, dur=src["duration"], k=k, name=src["name"]):
                self.report("sound", (base + f * dur) / self.total,
                            f"Шукаю найгучніші моменти · відео {k} з {n}", file=name)
            lv = audio_energy(src["path"], sp, self.check, src_off(src) + src["duration"])
            w0 = int(src_off(src))
            data[src["id"]]["energy"] = lv[w0:w0 + int(math.ceil(src["duration"]))] if (w0 or src.get("trimmed")) else lv
            done_sec += src["duration"]

        frames = {}
        if s.get("frames"):
            interval = max(FRAME_STEP_SEC, self.total / MAX_FRAMES)
            done_n = 0
            all_times = {}
            for src in job["sources"]:
                d = src["duration"]
                times, t = [], interval / 2
                while t < d:
                    times.append(t)
                    t += interval
                if d >= 2.5 and len(times) < 3:      # навіть короткий кліп — початок, середина, кінець
                    times = [round(d * f, 2) for f in (0.12, 0.5, 0.88)]
                all_times[src["id"]] = times
            total_n = sum(len(v) for v in all_times.values()) or 1
            for k, src in enumerate(job["sources"], 1):
                times = all_times[src["id"]]

                def fp(f, base=done_n, cnt=len(times), k=k, name=src["name"]):
                    self.report("look", (base + f * cnt) / total_n,
                                f"Дивлюсь кадри · відео {k} з {n}", file=name)
                frames[src["id"]] = window_frames(src["path"], times, fp, self.check, src)
                done_n += len(times)

        # автоконтраст: тон кожного джерела (з уже знятих кадрів або з кількох швидких)
        tone = {}
        if s.get("auto_tone", True) or s.get("match_exposure"):
            for src in job["sources"]:
                self.check()
                try:
                    jp = [j for _, j in frames.get(src["id"], [])]
                    if not jp:
                        d = src["duration"]
                        jp = [j for _, j in window_frames(src["path"], [d * f for f in (0.15, 0.35, 0.55, 0.75, 0.9)],
                                                          lambda f: None, self.check, src)]
                    t = tone_of(jp)
                except Cancelled:
                    raise
                except Exception as e:
                    _log(f"Автоконтраст для «{src['name']}» не вдався: {e!r}")
                    t = None
                if t:
                    tone[str(src["id"])] = t
            if s.get("match_exposure") and len(tone) > 1:
                tone = match_tones(tone)
                _log("Вирівнювання експозиції: ціль — спільна середина всіх відео")
            job["tone"] = tone
        if frames:
            try:
                job["vgroups"] = visual_groups(job["sources"], frames)
                if job["vgroups"]:
                    _log("Схожі джерела (той самий об'єкт/локація): %s" % visual_groups_text(job))
            except Exception as e:
                _log(f"Схожість кадрів: {e!r}")
            _log(f"Автоконтраст: {tone}")
            try:
                (Path(self.out) / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

        if job.get("music") and not job.get("music_info"):
            import music as _m
            self.report("sound", 0.95, "Слухаю музику: темп і удари")
            mu = job["music"]
            job["music_info"] = _m.analyze(mu["path"], mu.get("start", 0), mu.get("end", 30))
            lyr = (s.get("lyrics") or "").strip()
            if (s.get("cinematic") and s.get("take_sync", True)) or (lyr and s.get("song_sync", True)) \
                    or s.get("lipsync") or s.get("lip_auto"):
                job["sync"] = self._sync_takes(_m, mu["path"])
            if lyr:
                self.report("sound", 0.96, "Слухаю спів і прив'язую слова пісні")
                try:
                    lines = lyric_lines(lyr)
                    heard = transcribe_song(mu["path"], mu.get("start", 0), mu.get("end", 30),
                                            s.get("whisper_model", "medium"), s.get("language"), " ".join(lines),
                                            self.check)
                    timing, ratio = align_lyrics(lines, heard, float(mu.get("start", 0)), float(mu.get("end", 30)))
                    job["lyrics_timing"] = timing
                    job["lyrics_ratio"] = round(ratio, 2)
                    _log(f"Слова пісні: рядків {len(lines)}, почуто слів {len(heard)}, впізнано {ratio:.0%}")
                except Exception as e:
                    _log(f"Слова пісні: не вдалося прив'язати: {e!r}")
            (self.out / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

        ref_videos = []
        rlist = job.get("refs") or []
        if rlist:
            import refs as _r
            dl = self.out / "refs_dl"
            for k, rf in enumerate(rlist, 1):
                self.check()
                label = rf.get("label") or rf.get("url") or Path(rf.get("path", "")).name
                self.report("refs", (k - 1) / len(rlist), f"Вивчаю референси · {k} з {len(rlist)}", file=label)
                try:
                    path = rf.get("path")
                    if rf.get("url"):
                        self.report("refs", (k - 0.7) / len(rlist), f"Завантажую референс · {k} з {len(rlist)}",
                                    file=label)
                        path, title = _r.fetch(rf["url"], dl, log=_log)
                        label = f"{_r.platform(rf['url'])}: {title}" if title else label
                    ref_videos.append(_r.analyze(path, label, check=self.check))
                except Cancelled:
                    raise
                except Exception as e:
                    _log(f"Референс «{label}» не взято: {e!r}")
                    if rf.get("url"):
                        self.warnings.append(f"Референс «{label}» не вдалося завантажити (сайт не віддав відео) — "
                                             f"скачай його й перетягни файлом у блок референсів. Деталі в журналі.")
                    else:
                        self.warnings.append(f"Референс «{label}» не вдалося прочитати. Деталі в журналі.")
            _r.cleanup(dl)

        refs = []
        for p in job.get("screenshots", []):
            try:
                refs.append(image_bytes(Path(p).read_bytes()))
            except Exception:
                pass

        # ---- план від Claude
        import anthropic
        client = anthropic.Anthropic(api_key=cfg.get("api_key", ""))
        model = s.get("model", "claude-sonnet-5-5")
        self.report("plan", 0.02, "Рахую точну ціну")
        content, seg_window, frame_step = None, 0, 1
        for _ in range(6):
            self.check()
            content = build_content(job, data, frames, refs, seg_window, frame_step, ref_videos)
            try:
                tin = client.messages.count_tokens(
                    model=model, system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": content}]).input_tokens
            except Exception:
                tin = None
                break
            if tin <= CONTEXT_LIMIT:
                break
            seg_window = 20 if not seg_window else seg_window * 2
            frame_step *= 2
        est_out = 800 + 900 * 5 + THINK_EST   # сам план + роздуми моделі
        if tin:
            self.report("plan", 0.05, "Монтую",
                        tokens_in=tin, cost_estimate=price_of(model, tin, est_out))
        messages = [{"role": "user", "content": with_cache(content)}]
        plan, text, usage = ask_plan(client, model, messages, self.check,
                                     lambda f, c, m: self.report("plan", f, m, cost_live=c),
                                     tin or 0, self.out)
        try:
            want = int(str(s.get("num_videos") or "").strip())
        except ValueError:
            want = 0
        have = len(plan.get("videos") or [])
        if want and have < want:
            # Claude зробив менше роликів, ніж просили — допрошуємо решту (матеріал у кеші, тож дешево)
            _log(f"Claude дав {have} відео з {want} — прошу решту")
            more_msgs = messages + [{"role": "assistant", "content": text},
                                    {"role": "user", "content":
                                     f"Потрібно рівно {want} відео, а ти зробив {have}. Зроби ще {want - have} "
                                     f"НОВИХ відео з іншими моментами (не повторюй уже взяті) за тими самими правилами. "
                                     f"Поверни ТІЛЬКИ JSON з новими відео: {{\"notes\": \"...\", \"videos\": [...]}}"}]
            try:
                extra, _t, u2 = ask_plan(client, model, more_msgs, self.check,
                                         lambda f, c, m: self.report("plan", 0.7 + 0.29 * f, f"Монтую ще {want - have} відео"),
                                         tin or 0, self.out, f"Монтую ще {want - have} відео")
                plan["videos"] = (plan.get("videos") or []) + (extra.get("videos") or [])[:want - have]
                usage = Usage(usage, u2)
            except Cancelled:
                raise
            except Exception as e:
                _log(f"Не вдалося дозамовити відео: {e!r}")
                self.warnings.append(f"Claude зробив {have} відео замість {want}.")
        mus_i = job.get("music_info")
        if mus_i and plan.get("videos"):
            total = len(mus_i["grid"]) - 1
            short = [(i, plan_beats(v)) for i, v in enumerate(plan["videos"])]
            short = [(i, got) for i, got in short if got < total * 0.92]
            if short:
                # Claude «втомився» і не дописав ролик до кінця пісні — просимо продовження (матеріал у кеші)
                spb = (mus_i["grid"][-1] - mus_i["grid"][0]) / max(1, total)
                lines = [f"- відео {i + 1} «{plan['videos'][i].get('title', '')}»: є {got} з {total} ударів, "
                         f"бракує {total - got} (≈{(total - got) * spb:.0f} с, від {got * spb:.0f} с пісні до кінця)"
                         for i, got in short]
                _log("План коротший за пісню: " + "; ".join(f"відео {i + 1}: {got}/{total}" for i, got in short))
                cont_msgs = messages + [{"role": "assistant", "content": text},
                                        {"role": "user", "content":
                                         "Ти не дописав ролики до кінця пісні:\n" + "\n".join(lines) +
                                         "\nДопиши ПРОДОВЖЕННЯ кожного з них — тільки нові шматки з того удару, де "
                                         "зупинився, до кінця пісні. Той самий темп і енергія, що й на початку "
                                         "(кінець пісні не менш важливий — фінальні приспіви й кульмінація), "
                                         "ліпсінк-дублі на свої рядки, нові моменти без повторів уже взятих. "
                                         "Сума beats у продовженні = кількості ударів, яких бракує. "
                                         "Поверни ТІЛЬКИ JSON: {\"videos\": [{\"index\": номер відео, "
                                         "\"segments\": [...]}]}"}]
                try:
                    cont, _t, u3 = ask_plan(client, model, cont_msgs, self.check,
                                            lambda f, c, m: self.report("plan", 0.8 + 0.19 * f, "Монтую кінець пісні"),
                                            tin or 0, self.out, "Монтую кінець пісні")
                    usage = Usage(usage, u3)
                    for cv in cont.get("videos") or []:
                        try:
                            idx = int(cv.get("index")) - 1
                        except (TypeError, ValueError):
                            continue
                        if 0 <= idx < len(plan["videos"]) and cv.get("segments"):
                            plan["videos"][idx]["segments"] = list(plan["videos"][idx].get("segments") or []) \
                                + list(cv["segments"])
                    _log("Після продовження: " + "; ".join(
                        f"відео {i + 1}: {plan_beats(v)}/{total}" for i, v in enumerate(plan["videos"])))
                    text = json.dumps(plan, ensure_ascii=False)
                except Cancelled:
                    raise
                except Exception as e:
                    _log(f"Не вдалося дописати кінець: {e!r} — добиваю автоматично")
        self.cost = usage_cost(model, usage)
        month_total = add_spend(self.cost)

        save_state(self.out, data, [{"role": "user", "content": content},
                                    {"role": "assistant", "content": text}])
        result = finalize(job, data, text, self.out, 1, plan)
        if self.warnings:
            result["notes"] = (" ".join(self.warnings) + " " + (result.get("notes") or "")).strip()
        result.update({"cost": round(self.cost, 4), "month_total": month_total,
                       "tokens_in": usage.input_tokens, "tokens_out": usage.output_tokens})
        (self.out / "plan.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
        return result

# ======================================================================= спільне: запит, кеш, результат

EDIT_PROMPT = """ПРАВКИ ВІД АВТОРА:
{edit}

ПОТОЧНИЙ ПЛАН (час на таймлайні ролика → що взято з джерела):
{plan}

Внеси правки. Усе, про що автор не просив, залиш як було (включно з полем look кожного відео).
Поверни ПОВНИЙ оновлений план у тому самому JSON-форматі (усі відео й шматки)."""

RANGE_PROMPT = """ПРАВКА ДІЛЯНКИ ВІД АВТОРА:
{edit}

Відео №{vnum} «{title}». Автор виділив ділянку {t0:.1f}–{t1:.1f} с на таймлайні ролика
({span:.1f} с{beats_note}). Поточні шматки цього відео:
{plan}

Заміни ТІЛЬКИ цю ділянку новими шматками. Решта ролика не змінюється.
Не бери моменти, які вже є в ролику. Поверни ТІЛЬКИ JSON:
{{"segments": [[1, 0.0, {len_field}, "close", 1.0, 1.04, 0, 0, [], ""]], "notes": "що змінив"}}
(шматки — компактні масиви [source, start, {len_name}, shot, zoom, zoom_end, pan_x, pan_y, fx, tr])
Дотримуйся граматики монтажу: нова ділянка має стикуватися з сусідніми планами (інша крупність на стиках)."""


def plan_text(videos, only=None):
    lines = []
    for i, v in enumerate(videos):
        if only is not None and i != only:
            continue
        lines.append(f"Відео №{i + 1} «{v['title']}»" + (f" (look: {v['look']})" if v.get("look") else "") + ":")
        pos = 0.0
        for k, sg in enumerate(v["segments"], 1):
            d = sg["end"] - sg["start"]
            z = (f"перехід {sg['tr']}, " if sg.get("tr") else "") + (f"{sg['shot']}, " if sg.get("shot") else "") + f"zoom {sg.get('zoom', 1.0):.2f}" + (f"→{sg['zoom_end']:.2f}" if sg.get("zoom_end") else "") + \
                (f", fx {'+'.join(sg['fx'])}" if sg.get("fx") else "")
            lines.append(f"  #{k} [{pos:.1f}–{pos + d:.1f}] джерело {sg['source']}, {sg['start']:.1f}–{sg['end']:.1f} с, {z}")
            pos += d
    return "\n".join(lines)


def splice(video, t0, t1, new):
    """Вставляє нові шматки замість ділянки [t0, t1] таймлайну ролика."""
    out, pos, done = [], 0.0, False
    for sg in video["segments"]:
        d = sg["end"] - sg["start"]
        a, b = pos, pos + d
        if b <= t0 + 1e-6:
            out.append(sg)
        elif a >= t1 - 1e-6:
            if not done:
                out += new
                done = True
            out.append(sg)
        else:
            if a < t0:
                out.append(dict(sg, end=round(sg["start"] + (t0 - a), 3)))
            if not done:
                out += new
                done = True
            if b > t1:
                out.append(dict(sg, start=round(sg["start"] + (t1 - a), 3)))
        pos = b
    if not done:
        out += new
    out = [x for x in out if x["end"] - x["start"] >= 0.2]
    return dict(video, segments=out, duration=round(sum(x["end"] - x["start"] for x in out), 2))


def with_cache(content):
    """Позначаємо матеріал для кешу Claude: повторні запити (правки) коштують ~10% ціни."""
    out = [dict(b) for b in content]
    if out:
        out[-1] = dict(out[-1], cache_control={"type": "ephemeral"})
    return out


def usage_cost(model, u):
    p = PRICES.get(model, PRICES["claude-sonnet-5-5"])
    tin = getattr(u, "input_tokens", 0) or 0
    cw = getattr(u, "cache_creation_input_tokens", 0) or 0
    cr = getattr(u, "cache_read_input_tokens", 0) or 0
    tout = getattr(u, "output_tokens", 0) or 0
    total_in = tin + cw + cr
    if "long_from" in p and total_in > p["long_from"]:
        pin, pout = p["in_long"], p["out_long"]
    else:
        pin, pout = p["in"], p["out"]
    return (tin * pin + cw * pin * 1.25 + cr * pin * 0.1 + tout * pout) / 1e6


# Ліміт відповіді Claude (токени). Моделі 5.5 спершу «думають», і ці роздуми теж рахуються
# в ліміт — тому запас великий, а глибину роздумів тримаємо помірною через effort.
MAX_OUT = 64000
PLAN_EFFORT = "medium"   # перша спроба: розумно, але без роздумів на всі 64K
RETRY_EFFORT = "low"     # повтор: майже без роздумів, одразу план
THINK_EST = 12000        # орієнтовні роздуми на effort=medium — для оцінки ціни
PLAN_PHASES = ["переглядаю матеріал", "обираю найкращі моменти", "вибудовую ритм і структуру",
               "розставляю склейки"]


class Usage:
    """Сума витрат кількох запитів (основний + повторний)."""
    def __init__(self, *us):
        for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            setattr(self, k, sum((getattr(u, k, 0) or 0) for u in us if u is not None))


def ask_claude(client, model, messages, check, on_progress, tin_hint=0, label="Монтую", effort=PLAN_EFFORT):
    """Потокова відповідь Claude. Прогрес рухається і за часом (поки Claude «думає» над великим
    матеріалом і ще нічого не пише), і за кількістю написаного. Повертає (текст, usage, stop_reason)."""
    import threading
    state = {"text": "", "t0": time.time(), "done": False}
    # скільки чекати першого слова: залежить від розміру матеріалу
    wait = 6 + (tin_hint or 20000) / 9000.0

    def frac_now():
        el = time.time() - state["t0"]
        out_tokens = len(state["text"]) // 3
        f_time = 0.55 * (1 - math.exp(-el / max(8.0, wait * 1.6)))
        f_tok = 0.12 + 0.83 * (1 - math.exp(-out_tokens / 3500.0)) if out_tokens else 0
        return min(0.97, max(f_time, f_tok)), out_tokens

    def msg_now():
        n = len(re.findall(r'\[\s*\d+\s*,\s*-?[\d.]+\s*,', state["text"])) or state["text"].count('"source"')
        if n:
            return f"{label} · склейок: {n}"
        el = time.time() - state["t0"]
        return f"{label} · {PLAN_PHASES[min(len(PLAN_PHASES) - 1, int(el / max(4.0, wait / 2)))]}"

    def tick():
        while not state["done"]:
            f, ot = frac_now()
            try:
                on_progress(f, price_of(model, tin_hint, ot), msg_now())
            except Exception:
                pass
            time.sleep(0.7)
    th = threading.Thread(target=tick, daemon=True)
    th.start()
    try:
        # extra_body — щоб працювало з будь-якою версією бібліотеки anthropic
        with client.messages.stream(model=model, max_tokens=MAX_OUT, system=SYSTEM_PROMPT,
                                    messages=messages,
                                    extra_body={"output_config": {"effort": effort}}) as stream:
            for chunk in stream.text_stream:
                check()
                state["text"] += chunk
            final = stream.get_final_message()
    finally:
        state["done"] = True
    stop = getattr(final, "stop_reason", None)
    _log(f"Claude відповів (effort={effort}): {len(state['text'])} символів, stop_reason={stop}, "
         f"usage={getattr(final, 'usage', None)}")
    return state["text"], final.usage, stop


def ask_plan(client, model, messages, check, on_progress, tin_hint=0, out_dir=None, label="Монтую",
             need="videos"):
    """ask_claude + надійний розбір JSON: обрізана відповідь лагодиться, порожня — один повторний запит.
    Повертає (dict, текст, usage)."""
    text, usage, stop = ask_claude(client, model, messages, check, on_progress, tin_hint, label)
    _save_raw(out_dir, text, 1)
    obj = try_parse(text, need)
    if obj is not None:
        if stop == "max_tokens":
            obj["notes"] = ("План вийшов задовгим і обрізався — частину останніх шматків прибрано. "
                            + str(obj.get("notes") or "")).strip()
        return obj, text, usage
    _log("JSON не розібрано — прошу Claude повторити тільки JSON, з меншими роздумами")
    hint = ("Поверни ТІЛЬКИ валідний JSON у потрібному форматі, без пояснень. Довго не обмірковуй — "
            "одразу пиши план. Будь лаконічним: короткі notes, why і caption, без зайвих пробілів.")
    if text.strip():
        retry = messages + [{"role": "assistant", "content": text.strip()},
                            {"role": "user", "content": "Твоя відповідь обірвалась або не містить коректного JSON. "
                             + hint}]
    else:
        # порожня відповідь (усе пішло на роздуми) — повторюємо той самий запит з підказкою
        retry = [dict(m) for m in messages]
        last = retry[-1]
        if isinstance(last.get("content"), str):
            last["content"] = last["content"] + "\n\n" + hint
        else:
            last["content"] = list(last["content"]) + [{"type": "text", "text": hint}]
    text2, usage2, stop2 = ask_claude(client, model, retry, check,
                                      lambda f, c, m: on_progress(0.6 + 0.37 * f, c, f"{label} · ще раз"),
                                      tin_hint, label, effort=RETRY_EFFORT)
    _save_raw(out_dir, text2, 2)
    usage = Usage(usage, usage2)
    obj = try_parse(text2, need)
    if obj is None:
        raise RuntimeError("Claude двічі не повернув план (відповідь порожня або обірвана). "
                           "Спробуй ще раз, зменш кількість відео або матеріалу. Деталі в журналі.")
    return obj, text2, usage


def _save_raw(out_dir, text, n):
    if out_dir:
        try:
            (Path(out_dir) / f"claude_raw_{int(time.time())}_{n}.txt").write_text(text, encoding="utf-8")
        except Exception:
            pass


def save_state(out, data, history):
    out = Path(out)
    (out / "data.json").write_text(json.dumps({str(k): v for k, v in data.items()}, ensure_ascii=False),
                                   encoding="utf-8")
    (out / "history.json").write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")


def load_state(out):
    out = Path(out)
    data = {int(k): v for k, v in json.loads((out / "data.json").read_text(encoding="utf-8")).items()}
    history = json.loads((out / "history.json").read_text(encoding="utf-8"))
    return data, history


def _strip_fences(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```\s*$", "", t)
    return t


def repair_json(text):
    """Лагодить обрізаний JSON: відрізає незакінчений хвіст і закриває дужки.
    Пробує точки після кожного закритого об'єкта/масиву, від останньої до першої."""
    i = text.find("{")
    if i < 0:
        return None
    t = text[i:]
    stack, cuts, in_str, esc = [], [], False, False
    for k, ch in enumerate(t):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if not stack:
                break
            stack.pop()
            cuts.append((k + 1, "".join(reversed(stack))))
            if not stack:
                break
    for pos, closers in reversed(cuts[-400:]):
        cand = t[:pos].rstrip().rstrip(",") + closers
        try:
            return json.loads(cand)
        except Exception:
            continue
    return None


def try_parse(text, need="videos"):
    t = _strip_fences(text or "")
    cands = []
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        cands.append(m.group(0))
    for c in cands:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict) and need in obj:
                return obj
        except Exception:
            pass
    obj = repair_json(t)
    if isinstance(obj, dict) and obj.get(need):
        # прибираємо порожні/обрізані відео
        if need == "videos":
            obj["videos"] = [v for v in obj["videos"] if isinstance(v, dict) and v.get("segments")]
            if not obj["videos"]:
                return None
        _log("JSON був обрізаний — відновив частину плану")
        return obj
    return None


def parse_json(text, need="videos"):
    obj = try_parse(text, need)
    if obj is None:
        raise RuntimeError("Claude не повернув план. Спробуй ще раз або уточни запит.")
    return obj


def finalize(job, data, text, out, version, plan=None):
    plan = plan if plan is not None else parse_json(text)
    videos = clean_plan(plan, job, data)
    if not videos:
        raise RuntimeError("Claude не зміг скласти план: " + str(plan.get("notes", "")))
    try:                     # поворот джерел пам'ятаємо для наступних правок
        (Path(out) / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return finalize_videos(job, data, videos, plan.get("notes", ""), out, version)


def finalize_videos(job, data, videos, notes, out, version):
    s = job["settings"]
    out = Path(out)
    tag = "" if version == 1 else f"_v{version}"
    srt_all = None
    text_all = None
    lt = job.get("lyrics_timing")
    up = bool(s.get("lyrics_upper", False))
    # шматки тексту для кожного ролика: слова пісні (з музикою) або розпізнана мова (без музики)
    per_video = None
    if lt and job.get("music_info"):
        ms = float(job["music_info"].get("start", 0))
        per_video = lambda v, off: lyric_chunks(lt, ms, off, v["duration"])
    elif s.get("subtitles") and s.get("transcribe") and not job.get("music_info"):
        per_video = lambda v, off: caption_chunks(v["segments"], data, off)
    if per_video:
        svit_text = s.get("text_mode", "svit") in ("svit", "img")
        style = dict(s.get("text_style") or {})
        style["as_image"] = s.get("text_mode") == "img"
        style["upper"] = up or bool(style.get("upper"))
        res = ""
        try:
            res = next((src.get("resolution", "") for src in job.get("sources", []) if src.get("resolution")), "")
        except Exception:
            pass
        W, H = (0, 0)
        if svit_text:
            import textfx
            W, H = textfx.canvas_size(s.get("format", "9:16"), res)

        def as_lines(chunks):
            return [{"start": c[0]["start"], "end": c[-1]["end"], "text": " ".join(w["word"] for w in c)} for c in chunks]
        if s["layout"] == "one":
            offset, lists = 0.0, []
            for v in videos:
                lists.append(per_video(v, offset))
                offset += v["duration"] + VIDEO_GAP
            if svit_text:
                try:
                    text_all = textfx.render_items([x for cl in lists for x in as_lines(cl)], style, W, H,
                                                   out / f"text{tag}")
                    if text_all and text_all[0].get("tp"):   # запасні субтитри, якщо Text+ у Media Pool немає
                        p = out / f"subtitles_all{tag}.srt"
                        if write_srt(p, [strip_marks(c) for c in lists], style.get("upper", False)):
                            text_all[0]["srt"] = str(p)
                except Exception as e:
                    _log(f"Svit-текст не намалювався: {e!r} — ставлю звичайні субтитри")
                    svit_text = False
            if not svit_text:
                p = out / f"subtitles_all{tag}.srt"
                srt_all = str(p) if write_srt(p, [strip_marks(c) for c in lists], up or not lt) else None
        else:
            for i, v in enumerate(videos, 1):
                chunks = per_video(v, 0.0)
                done = False
                if svit_text:
                    try:
                        v["text"] = textfx.render_items(as_lines(chunks), style, W, H, out / f"text{tag}_{i:02}")
                        if v["text"] and v["text"][0].get("tp"):
                            p = out / f"subtitles_{i:02}{tag}.srt"
                            if write_srt(p, [strip_marks(chunks)], style.get("upper", False)):
                                v["text"][0]["srt"] = str(p)
                        done = True
                    except Exception as e:
                        _log(f"Svit-текст не намалювався: {e!r}")
                if not done:
                    p = out / f"subtitles_{i:02}{tag}.srt"
                    v["srt"] = str(p) if write_srt(p, [strip_marks(chunks)], up or not lt) else None
    posts = [f"=== {i}. {v['title']} ({v['duration']:.0f} с) ===\n{v.get('why', '')}\n\n"
             f"{v.get('caption', '')}\n{' '.join(v.get('hashtags', []))}\n" for i, v in enumerate(videos, 1)]
    if notes:
        posts.insert(0, f"Коментар монтажера: {notes}\n")
    cap = out / f"captions{tag}.txt"
    cap.write_text("\n".join(posts), encoding="utf-8")
    (out / "current_plan.json").write_text(json.dumps({"notes": notes, "videos": videos, "version": version},
                                                      ensure_ascii=False), encoding="utf-8")
    return {"notes": notes, "videos": videos, "srt_all": srt_all, "text_all": text_all,
            "text_anim": {k: (s.get("text_style") or {}).get(k, d) for k, d in
                          (("anim", "fade"), ("anim_strength", 50), ("anim_smooth", 50))},
            "captions": str(cap), "version": version,
            "tone": job.get("tone") or {}}


def estimate_edit(job_dir, span, full):
    """Скільки приблизно коштує правка (з урахуванням кешу матеріалу)."""
    job_dir = Path(job_dir)
    try:
        job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        res = json.loads((job_dir / "plan.json").read_text(encoding="utf-8"))
        cur = json.loads((job_dir / "current_plan.json").read_text(encoding="utf-8"))
    except Exception:
        return {"cost": 0}
    model = job["settings"].get("model", "claude-sonnet-5-5")
    p = PRICES.get(model, PRICES["claude-sonnet-5-5"])
    tin = res.get("tokens_in", 20000)
    nseg = sum(len(v["segments"]) for v in cur["videos"])
    plan_tok = 40 * nseg + 400
    tout = (300 + 70 * nseg) if full else (150 + int(span / SEG_LEN.get(job["settings"].get("pace", "normal"), 4.5) + 1) * 70)
    tout += THINK_EST // 2   # правка — менше роздумів, ніж повний монтаж
    cached = (tin * p["in"] * 0.1 + plan_tok * p["in"] + tout * p["out"]) / 1e6
    fresh = (tin * p["in"] * 1.25 + plan_tok * p["in"] + tout * p["out"]) / 1e6
    return {"cost": cached, "cost_nocache": fresh}


def revise(job_dir, edit_text, progress, cancel_event, rng=None):
    """Правка готового монтажу. Матеріал іде з кешу (~10% ціни). rng = {"video", "start", "end"} — лише ділянка."""
    import anthropic
    job_dir = Path(job_dir)
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    data, history = load_state(job_dir)
    cur = json.loads((job_dir / "current_plan.json").read_text(encoding="utf-8"))
    videos = cur["videos"]
    cfg = load_cfg()
    model = job["settings"].get("model", "claude-sonnet-5-5")
    client = anthropic.Anthropic(api_key=cfg.get("api_key", ""))

    def check():
        if cancel_event.is_set():
            raise Cancelled()
    version = int(cur.get("version", 1)) + 1
    mus = job.get("music_info")

    if rng:
        vi = max(0, min(len(videos) - 1, int(rng.get("video", 0))))
        v = videos[vi]
        t0, t1 = max(0.0, float(rng["start"])), min(v["duration"], float(rng["end"]))
        b0 = b1 = None
        if mus:
            g = mus["grid"]
            b0 = min(range(len(g)), key=lambda i: abs(g[i] - t0))
            b1 = min(range(len(g)), key=lambda i: abs(g[i] - t1))
            b1 = max(b1, b0 + 1)
            t0, t1 = g[b0], g[b1]
        prompt = RANGE_PROMPT.format(
            edit=edit_text.strip() or "Зроби цю ділянку цікавішою: інші моменти, кращий ритм.",
            vnum=vi + 1, title=v["title"], t0=t0, t1=t1, span=t1 - t0,
            beats_note=(f", рівно {b1 - b0} ударів музики — сума beats = {b1 - b0}" if mus else ""),
            plan=plan_text(videos, vi), len_field=('2' if mus else '0.0'), len_name=('beats' if mus else 'end'))
    else:
        prompt = EDIT_PROMPT.format(edit=edit_text.strip(), plan=plan_text(videos))

    progress("plan", 0.1, "Вношу правки", {})
    msgs = [{"role": "user", "content": with_cache(history[0]["content"]) + [{"type": "text", "text": prompt}]}]
    data_obj, text, usage = ask_plan(client, model, msgs, check,
                                     lambda f, c, m: progress("plan", 0.1 + f * 0.75, m, {"cost_live": c}),
                                     0, job_dir, "Вношу правки", need="segments" if rng else "videos")
    cost = usage_cost(model, usage)
    month_total = add_spend(cost)

    if rng:
        used = {}
        for i, other in enumerate(videos):
            pos = 0.0
            for sg in other["segments"]:
                d = sg["end"] - sg["start"]
                if not (i == vi and pos + d > t0 and pos < t1):
                    used.setdefault(sg["source"], []).append((sg["start"], sg["end"]))
                pos += d
        new = clean_segments(data_obj.get("segments", []), job, data, used,
                             beat_from=b0 or 0, beat_to=b1) if mus else \
            clean_segments(data_obj.get("segments", []), job, data, used)
        if not mus and new:
            # підганяємо тривалість під виділену ділянку
            total, span = sum(x["end"] - x["start"] for x in new), t1 - t0
            if total > span:
                over = total - span
                last = new[-1]
                last["end"] = round(max(last["start"] + 0.3, last["end"] - over), 3)
        if not new:
            raise RuntimeError("Claude не запропонував заміну для ділянки. Спробуй сформулювати інакше.")
        videos = [splice(x, t0, t1, new) if i == vi else x for i, x in enumerate(videos)]
        notes = data_obj.get("notes", "")
    else:
        videos = clean_plan(data_obj, job, data, prev_videos=videos)
        notes = data_obj.get("notes", "")
        try:
            (job_dir / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        if not videos:
            raise RuntimeError("Claude не зміг внести правки: " + str(notes))
    if mus:
        for x in videos:
            x["music"] = {k: mus[k] for k in ("path", "start", "end")}
    result = finalize_videos(job, data, videos, notes, job_dir, version)
    result.update({"cost": round(cost, 4), "month_total": month_total,
                   "tokens_in": usage.input_tokens, "tokens_out": usage.output_tokens,
                   "range": rng})
    (job_dir / f"plan_v{version}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                                   encoding="utf-8")
    return result
