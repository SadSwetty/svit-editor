"""
Svit Editor — аналіз музики для монтажу під трек.
Темп (BPM), удари, сильні долі, енергія по ударах, хвиля для повзунка і прев'ю шматка.
Тільки numpy + PyAV, без важких бібліотек.
"""
import base64
import io
import wave

import numpy as np

SR = 22050
HOP = 512
NFFT = 2048
# усе, що читає ffmpeg/PyAV
AUDIO_EXT = {".wav", ".wave", ".bwf", ".mp3", ".mp2", ".aif", ".aiff", ".aifc", ".flac", ".alac", ".m4a", ".m4b",
             ".aac", ".ogg", ".oga", ".opus", ".wma", ".caf", ".ac3", ".eac3", ".dts", ".amr", ".ape", ".wv",
             ".mka", ".tta", ".au", ".snd", ".spx", ".dsf", ".dff"}


def decode_mono(path, sr=SR):
    import av
    c = av.open(str(path))
    try:
        if not c.streams.audio:
            raise RuntimeError("У файлі немає звуку.")
        res = av.AudioResampler(format="s16", layout="mono", rate=sr)
        chunks = []
        for frame in c.decode(c.streams.audio[0]):
            for f in res.resample(frame):
                chunks.append(f.to_ndarray().ravel())
        try:
            for f in res.resample(None):
                chunks.append(f.to_ndarray().ravel())
        except Exception:
            pass
    finally:
        c.close()
    if not chunks:
        raise RuntimeError("Не вдалося прочитати звук.")
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def onset_envelope(y, sr=SR):
    """Спектральний потік: де в музиці «щось починається» (удар, атака)."""
    n = 1 + (len(y) - NFFT) // HOP
    if n < 8:
        return np.zeros(8, dtype=np.float32)
    win = np.hanning(NFFT).astype(np.float32)
    prev, flux = None, np.zeros(n, dtype=np.float32)
    step = 256
    for i0 in range(0, n, step):
        idx = np.arange(NFFT)[None, :] + HOP * np.arange(i0, min(n, i0 + step))[:, None]
        mag = np.log1p(10.0 * np.abs(np.fft.rfft(y[idx] * win, axis=1)))
        if prev is not None:
            mag_full = np.vstack([prev[None, :], mag])
        else:
            mag_full = np.vstack([mag[:1], mag])
        d = np.maximum(0.0, np.diff(mag_full, axis=0)).sum(axis=1)
        flux[i0:i0 + len(d)] = d
        prev = mag[-1]
    flux -= np.convolve(flux, np.ones(16) / 16, mode="same")   # прибираємо повільний фон
    flux = np.maximum(flux, 0)
    sd = flux.std() or 1.0
    return flux / sd


def estimate_bpm(env, fps):
    ac = np.correlate(env - env.mean(), env - env.mean(), mode="full")[len(env) - 1:]
    best, best_bpm = -1e9, 120.0
    for bpm in np.arange(60.0, 190.0, 0.5):
        lag = 60.0 * fps / bpm
        l0 = int(lag)
        if l0 + 1 >= len(ac):
            continue
        v = ac[l0] * (1 - (lag - l0)) + ac[l0 + 1] * (lag - l0)
        w = np.exp(-0.5 * (np.log2(bpm / 120.0) / 0.9) ** 2)
        if v * w > best:
            best, best_bpm = v * w, bpm
    return float(best_bpm)


def track_beats(env, fps, bpm, tightness=120.0):
    """Динамічне програмування (Ellis 2007): удари там, де атаки + рівний темп."""
    period = 60.0 * fps / bpm
    n = len(env)
    score = env.astype(np.float64).copy()
    back = -np.ones(n, dtype=np.int64)
    lo_off, hi_off = int(round(2 * period)), max(1, int(round(period / 2)))
    for t in range(n):
        lo, hi = max(0, t - lo_off), t - hi_off
        if hi <= lo:
            continue
        cand = np.arange(lo, hi)
        cost = -tightness * (np.log((t - cand) / period)) ** 2
        vals = score[cand] + cost
        k = int(np.argmax(vals))
        score[t] = env[t] + vals[k]
        back[t] = cand[k]
    tail = max(1, int(round(period)))
    t = int(np.argmax(score[-tail:])) + n - tail
    beats = []
    while t >= 0:
        beats.append(t)
        t = int(back[t])
    return np.array(beats[::-1], dtype=np.float64) / fps


def analyze(path, start, end):
    """Аналіз фрагмента пісні [start, end] (секунди)."""
    y = decode_mono(path)
    dur = len(y) / SR
    start = max(0.0, min(float(start), dur - 1))
    end = max(start + 1, min(float(end), dur))
    env = onset_envelope(y)
    fps = SR / HOP
    bpm = estimate_bpm(env, fps)
    beats = track_beats(env, fps, bpm)
    inside = beats[(beats >= start - 0.05) & (beats < end - 0.15)]
    if len(inside) < 2:
        step = 60.0 / bpm
        inside = np.arange(start, end - 0.15, step)
    # фрагмент починаємо точно з удару, щоб склейки лягали в ритм
    if inside[0] - start < 0.6:
        start = float(inside[0])
    rel = [round(float(b - start), 3) for b in inside if b >= start - 1e-6]
    if not rel or rel[0] != 0.0:
        rel = [0.0] + rel
    length = round(end - start, 3)
    grid = rel + [length]
    # енергія по ударах
    energies = []
    for a, b in zip(grid[:-1], grid[1:]):
        seg = y[int((start + a) * SR):int((start + b) * SR)]
        energies.append(float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0)
    e = np.array(energies)
    lo, hi = np.percentile(e, 5), np.percentile(e, 98)
    lvl = [int(max(0, min(9, round(9 * (v - lo) / max(hi - lo, 1e-9))))) for v in e]
    # сильні долі: фаза 0..3 з найбільшою сумою атак
    on = [env[min(len(env) - 1, int((start + b) * fps))] for b in rel]
    phase = int(np.argmax([sum(on[p::4]) for p in range(4)])) if len(on) >= 4 else 0
    bars = list(range(phase, len(rel), 4))
    if len(rel) > 3:
        bpm = 60.0 / float(np.median(np.diff(rel)))
    return {"path": str(path), "start": round(start, 3), "end": round(end, 3), "length": length,
            "bpm": round(bpm, 1), "beats": rel, "grid": grid, "energy": lvl, "bars": bars}


def music_text(m):
    """Опис фрагмента для Claude: удари з енергією, | — початок такту."""
    bars = set(m["bars"])
    parts = []
    for i, (b, e) in enumerate(zip(m["beats"], m["energy"])):
        parts.append(("|" if i in bars else "") + f"{b:.2f}:{e}")
    lines = [" ".join(parts[i:i + 16]) for i in range(0, len(parts), 16)]
    return (f"МУЗИКА (монтаж під трек): фрагмент пісні {m['start']:.1f}–{m['end']:.1f} с "
            f"({m['length']:.1f} с), темп {m['bpm']:.0f} BPM, ударів: {len(m['beats'])}.\n"
            f"Удари — секунди від початку фрагмента : енергія 0–9; «|» — початок такту:\n" + "\n".join(lines))


def overview(path, bins=700):
    """Тривалість і хвиля (піки) для повзунка у вікні."""
    y = decode_mono(path, sr=8000)
    dur = len(y) / 8000
    n = max(1, len(y) // bins)
    peaks = [round(float(np.abs(y[i:i + n]).max()), 3) if len(y[i:i + n]) else 0.0
             for i in range(0, n * bins, n)][:bins]
    top = max(peaks) or 1.0
    return {"duration": round(dur, 2), "peaks": [round(p / top, 3) for p in peaks]}


def preview_wav(path, start, end, sr=22050):
    """Шматок пісні як data:audio/wav для прослуховування у вікні."""
    y = decode_mono(path, sr=sr)
    seg = y[int(max(0, start) * sr):int(max(start + 0.5, end) * sr)]
    seg = np.clip(seg, -1, 1)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((seg * 32767).astype(np.int16).tobytes())
    return "data:audio/wav;base64," + base64.b64encode(buf.getvalue()).decode()


def sync_offset(song_path, video_path, song_env=None):
    """Де в пісні звучить дубль: крос-кореляція «атак» звуку камери і треку.
    Повертає (offset, впевненість): момент пісні = секунда джерела + offset."""
    fps = SR / HOP
    if song_env is None:
        song_env = onset_envelope(decode_mono(song_path))
    v = onset_envelope(decode_mono(video_path))
    if len(v) < fps * 4:
        return None, 0.0
    song_env = song_env.copy()
    v = v.copy()
    song_env[:12] = 0
    song_env[-12:] = 0
    v[:12] = 0
    v[-12:] = 0
    # стискаємо гучні піки, щоб збігалися ритмічні малюнки, а не окремі удари
    a = np.log1p(song_env)
    b = np.log1p(v)
    a = (a - a.mean()) / (a.std() or 1.0)
    b = (b - b.mean()) / (b.std() or 1.0)
    n = 1
    while n < len(a) + len(b):
        n *= 2
    cc = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
    # індекс k → зсув k (пісня = відео + k); від'ємні — у кінці масиву
    lags = np.concatenate([cc[:len(a)], cc[n - len(b) + 1:]])
    ks = np.concatenate([np.arange(len(a)), np.arange(-len(b) + 1, 0)])
    # нормуємо на довжину перекриття, щоб короткі випадкові збіги не вигравали
    ov = np.minimum(len(a), ks + len(b)) - np.maximum(0, ks)
    valid = ov > max(fps * 4, 0.6 * min(len(b), len(a)))
    score = np.where(valid, lags / np.sqrt(np.maximum(ov, 1)), -1e9)
    i = int(np.argmax(score))
    # впевненість: наскільки пік вищий за найкращий інший зсув (поза ±0.5 с від нього)
    far = valid & (np.abs(ks - ks[i]) > fps * 0.5)
    second = float(score[far].max()) if far.any() else 0.0
    sv = score[valid]
    spread = float(sv.std() or 1.0)
    conf = float((score[i] - second) / spread)
    return round(float(ks[i] / fps), 3), round(conf, 2)


def song_envelope(path):
    return onset_envelope(decode_mono(path))
