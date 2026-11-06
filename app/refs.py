"""
Svit Editor — референси: відео, якими автор надихається.
Посилання (TikTok, Reels, Shorts, YouTube) завантажуються в мінімальній якості лише для аналізу
і видаляються після монтажу. З кожного референсу беремо темп склейок і кілька кадрів.
"""
import io
import re
import shutil
from pathlib import Path

import numpy as np

URL_RE = re.compile(r"https?://\S+", re.I)
PLATFORMS = [("tiktok.com", "TikTok"), ("instagram.com", "Instagram"), ("youtube.com/shorts", "Shorts"),
             ("youtu.be", "YouTube"), ("youtube.com", "YouTube"), ("vimeo.com", "Vimeo")]
MAX_SECONDS = 180          # аналізуємо максимум 3 хвилини референсу
THUMB = 384


def platform(url):
    u = url.lower()
    for key, name in PLATFORMS:
        if key in u:
            return name
    return "Відео"


def _impersonate():
    try:
        import curl_cffi  # noqa: F401
        from yt_dlp.networking.impersonate import ImpersonateTarget
        return ImpersonateTarget.from_str("chrome")
    except Exception:
        return None


def fetch(url, out_dir, log=print):
    """Завантажує референс за посиланням (найменша якість з картинкою). Повертає (шлях, назва) або кидає помилку.
    Спроби: звичайна → без перевірки сертифіката (якщо SSL-помилка: VPN, антивірус, старі сертифікати)
    → з маскуванням під Chrome (TikTok часто блокує «роботів»)."""
    import yt_dlp
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        import certifi
        import os
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    except Exception:
        pass
    base = {
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "format": "best[height<=480][vcodec!=none][acodec!=none]/best[height<=720][vcodec!=none]/worst[vcodec!=none]/best",
        "quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True,
        "socket_timeout": 20, "retries": 2,
        "match_filter": lambda info, *a, **k: "Задовге відео (понад 15 хв)" if (info.get("duration") or 0) > 900 else None,
    }
    imp = _impersonate()
    # перевірку сертифіката НЕ вимикаємо (захист від підміни відео в мережі)
    tries = [("звичайно", {})]
    if imp is not None:
        tries.append(("як Chrome", {"impersonate": imp}))
    last = None
    for i, (name, extra) in enumerate(tries):
        try:
            with yt_dlp.YoutubeDL(dict(base, **extra)) as ydl:
                info = ydl.extract_info(url, download=True)
                path = ydl.prepare_filename(info)
            if not Path(path).exists():
                cands = sorted(out_dir.glob(f"{info.get('id', '*')}.*"))
                if not cands:
                    raise RuntimeError("не вдалося завантажити")
                path = str(cands[0])
            log(f"Референс {url} завантажено ({name})")
            return path, (info.get("title") or "")[:80]
        except Exception as e:
            last = e
            log(f"Референс {url}: спроба «{name}» не вдалася: {e}")
    raise last


def analyze(path, label, max_frames=10, check=lambda: None):
    """Темп склейок (детекція змін плану) + ключові кадри з різних планів."""
    import av
    c = av.open(str(path))
    try:
        vs = c.streams.video[0]
        vs.thread_type = "AUTO"
        prev, diffs, times = None, [], []
        thumbs, next_thumb = [], 0.0
        for frame in c.decode(video=0):
            t = float(frame.time or 0)
            if t > MAX_SECONDS:
                break
            g = frame.reformat(width=64, height=36, format="gray").to_ndarray().astype(np.float32) / 255.0
            if prev is not None:
                diffs.append(float(np.abs(g - prev).mean()))
                times.append(t)
            prev = g
            if t >= next_thumb:
                img = frame.to_image()
                img.thumbnail((THUMB, THUMB))
                buf = io.BytesIO()
                img.convert("RGB").save(buf, "JPEG", quality=70)
                thumbs.append((t, buf.getvalue()))
                next_thumb = t + 0.5
            if len(times) % 300 == 0:
                check()
        duration = times[-1] if times else 0.0
    finally:
        c.close()
    d = np.array(diffs) if diffs else np.zeros(1)
    thr = max(0.09, float(np.median(d) + 4 * (np.median(np.abs(d - np.median(d))) + 1e-6)))
    cuts, last = [], -1.0
    for t, v in zip(times, diffs):
        if v > thr and t - last > 0.25:
            cuts.append(round(t, 2))
            last = t
    bounds = [0.0] + cuts + [duration]
    shots = [b - a for a, b in zip(bounds[:-1], bounds[1:]) if b - a > 0.05]
    # кадри з середини планів, рівномірно по всьому референсу
    mids = [(a + b) / 2 for a, b in zip(bounds[:-1], bounds[1:])]
    if len(mids) > max_frames:
        idx = np.linspace(0, len(mids) - 1, max_frames).round().astype(int)
        mids = [mids[i] for i in idx]
    picked = []
    for m in mids:
        if thumbs:
            t, jpg = min(thumbs, key=lambda x: abs(x[0] - m))
            if not picked or picked[-1][0] != t:
                picked.append((t, jpg))
    return {"label": label, "duration": round(duration, 1), "cuts": cuts,
            "shots": len(shots), "avg": round(float(np.mean(shots)), 2) if shots else round(duration, 2),
            "min": round(float(np.min(shots)), 2) if shots else 0, "max": round(float(np.max(shots)), 2) if shots else 0,
            "frames": picked}


def ref_text(i, r):
    head = (f"РЕФЕРЕНС №{i}: {r['label']} — {r['duration']:.0f} с, планів: {r['shots']}, "
            f"середній план {r['avg']:.1f} с (від {r['min']:.1f} до {r['max']:.1f} с).")
    if r["cuts"]:
        head += "\nСклейки на секундах: " + ", ".join(f"{c:.1f}" for c in r["cuts"][:60])
    return head


def cleanup(dirpath):
    shutil.rmtree(str(dirpath), ignore_errors=True)
