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


_PREV_CACHE = {}


def preview_wav(path, start, end, sr=22050):
    """Шматок пісні як data:audio/wav для прослуховування у вікні."""
    key = (str(path), sr)
    if _PREV_CACHE.get("key") != key:          # трек декодуємо один раз — далі шматки вирізаються миттєво
        _PREV_CACHE.clear()
        _PREV_CACHE.update(key=key, y=decode_mono(path, sr=sr))
    y = _PREV_CACHE["y"]
    seg = y[int(max(0, start) * sr):int(max(start + 0.5, end) * sr)]
    seg = np.clip(seg, -1, 1)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((seg * 32767).astype(np.int16).tobytes())
    return "data:audio/wav;base64," + base64.b64encode(buf.getvalue()).decode()


def chroma(y, sr=SR):
    """Гармонія по кадрах (12 нот): стійка до поганого мікрофона й кімнати, на відміну від ударів."""
    n = 1 + (len(y) - NFFT) // HOP
    if n < 8:
        return np.zeros((8, 12), dtype=np.float32)
    freqs = np.fft.rfftfreq(NFFT, 1.0 / sr)
    ok = (freqs > 80) & (freqs < 5000)
    pc = np.zeros(len(freqs), dtype=int)
    pc[ok] = (np.round(12 * np.log2(freqs[ok] / 440.0)) + 69).astype(int) % 12
    M = np.zeros((len(freqs), 12), dtype=np.float32)
    M[np.where(ok)[0], pc[ok]] = 1.0
    win = np.hanning(NFFT).astype(np.float32)
    out = np.zeros((n, 12), dtype=np.float32)
    step = 256
    for i0 in range(0, n, step):
        idx = np.arange(NFFT)[None, :] + HOP * np.arange(i0, min(n, i0 + step))[:, None]
        p = np.abs(np.fft.rfft(y[idx] * win, axis=1)) ** 2
        out[i0:i0 + len(p)] = np.log1p(100.0 * (p @ M))
    out /= (np.linalg.norm(out, axis=1, keepdims=True) + 1e-6)
    out -= out.mean(axis=0, keepdims=True)
    out /= (out.std(axis=0, keepdims=True) + 1e-6)
    return out


def _xcorr(a, b):
    n = 1
    while n < len(a) + len(b):
        n *= 2
    cc = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
    return np.concatenate([cc[:len(a)], cc[n - len(b) + 1:]])


def song_features(path):
    y = decode_mono(path)
    return {"env": onset_envelope(y), "chroma": chroma(y)}


def sync_offset(song_path, video_path, song_env=None, window=None):
    """Де в пісні звучить дубль: крос-кореляція ударів і гармонії звуку камери з треком.
    window=(початок, кінець) шматка пісні в секундах — шукаємо лише зсуви, де дубль перекриває цей шматок.
    Повертає (offset, впевненість): момент пісні = секунда джерела + offset."""
    fps = SR / HOP
    if not isinstance(song_env, dict):
        song_env = {"env": song_env} if isinstance(song_env, np.ndarray) else song_features(song_path)
    yv = decode_mono(video_path)
    v = onset_envelope(yv)
    if len(v) < fps * 4:
        return None, 0.0
    a = song_env["env"].astype(np.float64).copy()
    b = v.astype(np.float64).copy()
    a[:12] = 0
    a[-12:] = 0
    b[:12] = 0
    b[-12:] = 0
    a, b = np.log1p(a), np.log1p(b)
    a = (a - a.mean()) / (a.std() or 1.0)
    b = (b - b.mean()) / (b.std() or 1.0)
    ks = np.concatenate([np.arange(len(a)), np.arange(-len(b) + 1, 0)])
    ov = np.minimum(len(a), ks + len(b)) - np.maximum(0, ks)
    valid = ov > max(fps * 4, 0.35 * min(len(b), len(a)))
    if window:
        w0, w1 = window[0] * fps, window[1] * fps
        cover = np.minimum(w1, ks + len(b)) - np.maximum(w0, ks)
        valid &= cover > min(len(b), w1 - w0) * 0.3
    if not valid.any():
        return None, 0.0
    norm = np.sqrt(np.maximum(ov, 1))

    def z(x):
        sv = x[valid]
        return (x - sv.mean()) / (sv.std() or 1.0)
    score = z(_xcorr(a, b) / norm)
    ca = song_env.get("chroma")
    if ca is not None:
        cb = chroma(yv)
        la, lb = min(len(ca), len(a)), min(len(cb), len(b))
        if la == len(a) and lb == len(b):
            cc = sum(_xcorr(ca[:, j].astype(np.float64), cb[:, j].astype(np.float64)) for j in range(12))
            score = score + 1.3 * z(cc / norm)
    score = np.where(valid, score, -1e9)
    i = int(np.argmax(score))
    far = valid & (np.abs(ks - ks[i]) > fps * 0.5)
    second = float(score[far].max()) if far.any() else 0.0
    spread = float(score[valid].std() or 1.0)
    conf = float((score[i] - second) / spread)
    return round(float(ks[i] / fps), 3), round(conf, 2)


def song_envelope(path):
    return song_features(path)


def decode_stereo(path, start, end, sr=48000):
    """Шматок треку [start, end] у стерео float32 (n, 2)."""
    import av
    c = av.open(str(path))
    try:
        if not c.streams.audio:
            raise RuntimeError("У файлі немає звуку.")
        res = av.AudioResampler(format="s16", layout="stereo", rate=sr)
        chunks = []
        for frame in c.decode(c.streams.audio[0]):
            for f in res.resample(frame):
                chunks.append(f.to_ndarray().reshape(-1, 2))
        try:
            for f in res.resample(None):
                chunks.append(f.to_ndarray().reshape(-1, 2))
        except Exception:
            pass
    finally:
        c.close()
    y = np.concatenate(chunks).astype(np.float32) / 32768.0
    return y[int(max(0, start) * sr):int(max(start, end) * sr)]


def ducked_bed(path, start, end, voice, out_path, bed_db=-4.0, duck_db=-17.0, ramp=0.25, sr=48000):
    """Музична підкладка під голос: шматок треку, який притихає там, де говорять (voice — [(від, до)] у секундах
    від початку ролика). Плавні переходи ramp секунд. Пише 16-бітний WAV."""
    y = decode_stereo(path, start, end, sr)
    n = len(y)
    t = np.arange(n) / sr
    g_db = np.full(n, bed_db, np.float32)
    for a, b in voice:
        a0, b1 = max(0.0, a - ramp), b + ramp
        m = (t >= a0) & (t <= b1)
        if not m.any():
            continue
        # трапеція: спуск за ramp до початку голосу, тримаємо, підйом після
        k = np.minimum(np.clip((t[m] - a0) / ramp, 0, 1), np.clip((b1 - t[m]) / ramp, 0, 1))
        g_db[m] = np.minimum(g_db[m], bed_db + (duck_db - bed_db) * k)
    y = y * (10 ** (g_db / 20.0))[:, None]
    y = np.clip(y, -1, 1)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((y * 32767).astype(np.int16).tobytes())
    return n / sr


# ======================================================================= саундтрек влогу: кілька треків

_STEREO_CACHE = {}


def _stereo_full(path, sr=48000):
    """Увесь трек у стерео (int16, щоб не тримати в пам'яті float32). Кешується на час збірки."""
    key = (str(path), sr)
    if key not in _STEREO_CACHE:
        y = decode_stereo(path, 0, 1e9, sr)
        _STEREO_CACHE[key] = (np.clip(y, -1, 1) * 32767).astype(np.int16)
    return _STEREO_CACHE[key]


def track_profile(path):
    """Короткий опис треку для Claude і для склейок: тривалість, темп, удари й такти по всьому треку,
    енергія кожні 10 с (0–9) і найгучніша ділянка (приблизно приспів / кульмінація)."""
    y = decode_mono(path)
    dur = len(y) / SR
    env = onset_envelope(y)
    fps = SR / HOP
    bpm = estimate_bpm(env, fps)
    beats = track_beats(env, fps, bpm)
    if len(beats) < 4:
        beats = np.arange(0.0, dur, 60.0 / bpm)
    on = [env[min(len(env) - 1, int(b * fps))] for b in beats]
    phase = int(np.argmax([sum(on[p::4]) for p in range(4)])) if len(on) >= 8 else 0
    bars = [round(float(b), 3) for b in beats[phase::4]]
    step = 10.0
    rms = []
    for a in np.arange(0.0, dur, step):
        seg = y[int(a * SR):int(min(dur, a + step) * SR)]
        rms.append(float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0)
    r = np.array(rms) if rms else np.zeros(1)
    lo, hi = np.percentile(r, 5), np.percentile(r, 98)
    lo = min(lo, 0.5 * hi)          # рівний за гучністю трек — не роздуваємо дрібні різниці до 0…9
    energy = [int(max(0, min(9, round(9 * (v - lo) / max(hi - lo, 1e-9))))) for v in r]
    win = max(1, min(len(r), 3))
    sm = np.convolve(r, np.ones(win) / win, mode="valid") if len(r) >= win else r
    k = int(np.argmax(sm)) if len(sm) else 0
    if len(beats) > 3:
        bpm = 60.0 / float(np.median(np.diff(beats)))
    return {"path": str(path), "duration": round(dur, 2), "bpm": round(bpm, 1),
            "beats": [round(float(b), 3) for b in beats], "bars": bars, "energy": energy,
            "peak": [round(k * step, 1), round(min(dur, (k + win) * step), 1)]}


def snap_to_bar(t, prof, tol=1.2):
    """Секунда треку → найближчий початок такту (або удар), щоб трек входив у ритм, а не з півноти."""
    for grid in (prof.get("bars") or [], prof.get("beats") or []):
        if grid:
            b = min(grid, key=lambda x: abs(x - t))
            if abs(b - t) <= tol:
                return float(b)
    return float(t)


def video_features(video_path):
    yv = decode_mono(video_path)
    return {"env": onset_envelope(yv), "chroma": chroma(yv), "dur": len(yv) / SR}


def find_track(track_feats, vfeat, min_conf=1.3):
    """Чи звучить у відео один із треків. track_feats — [features] (song_features), vfeat — video_features.
    Повертає (індекс треку, зсув, впевненість) або None: момент треку = секунда відео + зсув."""
    fps = SR / HOP
    b0, cb = vfeat["env"], vfeat["chroma"]
    if len(b0) < fps * 6:
        return None
    best = None
    for ti, tf in enumerate(track_feats):
        a = tf["env"].astype(np.float64).copy()
        b = b0.astype(np.float64).copy()
        a[:12] = a[-12:] = 0
        b[:12] = b[-12:] = 0
        a, b = np.log1p(a), np.log1p(b)
        a = (a - a.mean()) / (a.std() or 1.0)
        b = (b - b.mean()) / (b.std() or 1.0)
        ks = np.concatenate([np.arange(len(a)), np.arange(-len(b) + 1, 0)])
        ov = np.minimum(len(a), ks + len(b)) - np.maximum(0, ks)
        valid = ov > max(fps * 6, 0.25 * min(len(b), len(a)))
        if not valid.any():
            continue
        norm = np.sqrt(np.maximum(ov, 1))

        def z(x):
            sv = x[valid]
            return (x - sv.mean()) / (sv.std() or 1.0)
        score = z(_xcorr(a, b) / norm)
        ca = tf.get("chroma")
        if ca is not None and len(ca) == len(a) and len(cb) == len(b):
            cc = sum(_xcorr(ca[:, j].astype(np.float64), cb[:, j].astype(np.float64)) for j in range(12))
            score = score + 1.3 * z(cc / norm)
        score = np.where(valid, score, -1e9)
        i = int(np.argmax(score))
        far = valid & (np.abs(ks - ks[i]) > fps * 0.5)
        second = float(score[far].max()) if far.any() else 0.0
        conf = float((score[i] - second) / float(score[valid].std() or 1.0))
        if conf >= min_conf and (best is None or conf > best[2]):
            best = (ti, round(float(ks[i] / fps), 3), round(conf, 2))
    return best


def _duck_gain(n, sr, voice, bed_db, duck_db, ramp):
    t = np.arange(n) / sr
    g_db = np.full(n, bed_db, np.float32)
    for a, b in voice:
        a0, b1 = max(0.0, a - ramp), b + ramp
        i0, i1 = int(a0 * sr), min(n, int(b1 * sr) + 1)
        if i1 <= i0:
            continue
        tt = t[i0:i1]
        k = np.minimum(np.clip((tt - a0) / ramp, 0, 1), np.clip((b1 - tt) / ramp, 0, 1))
        g_db[i0:i1] = np.minimum(g_db[i0:i1], bed_db + (duck_db - bed_db) * k)
    return (10 ** (g_db / 20.0)).astype(np.float32)


def soundtrack_bed(tracks, cues, total, voice, out_path, xfade=3.0, bed_db=-3.0, duck_db=-16.0,
                   ramp=0.45, end_fade=3.5, sr=48000, log=None):
    """Музична доріжка влогу з кількох треків.
    tracks — {id: профіль (track_profile)}; cues — [{"at": с ролика, "track": id або 0 (тиша), "from": с треку,
    "xfade": с}], відсортовані; total — довжина ролика; voice — [(від, до)] де говорять (там музика притихає).
    Переходи між треками — плавний крос-фейд (рівна потужність), трек входить з початку такту.
    Якщо трек закінчився раніше за наступну зміну — сам переходимо в наступний трек списку.
    Повертає [(at, track, from, до)] — що реально звучить, для журналу."""
    n = int(round(total * sr))
    mix = np.zeros((n, 2), np.float32)
    ids = [k for k in tracks]
    cues = sorted([c for c in cues if 0 <= c["at"] < total - 0.5], key=lambda c: c["at"])
    if not cues or cues[0]["at"] > 0.05:
        first = cues[0] if cues else {"track": ids[0], "from": 0.0}
        cues = [{"at": 0.0, "track": first["track"], "from": first.get("from", 0.0)}] + cues
    played = []
    i = 0
    while i < len(cues):
        c = cues[i]
        at = float(c["at"])
        nxt = float(cues[i + 1]["at"]) if i + 1 < len(cues) else total
        tid = c.get("track")
        if not tid or tid not in tracks:
            i += 1
            continue
        prof = tracks[tid]
        tdur = prof["duration"]
        frm = max(0.0, min(float(c.get("from", 0.0)), tdur - 4.0))
        xf = float(c.get("xfade", xfade))
        run = nxt - at
        left = tdur - frm
        if left < run - 0.5:
            # трек скінчився раніше — далі наступний трек плейлиста з його початку, той самий плавний перехід
            if len(ids) > 1:
                k = (ids.index(tid) + 1) % len(ids)
                nt = ids[k]
                cut = at + max(4.0, left - xfade)
                cues.insert(i + 1, {"at": round(cut, 2), "track": nt, "from": snap_to_bar(0.0, tracks[nt]),
                                    "auto": True})
                nxt = cut
                run = nxt - at
            else:
                run = left
        pre = min(xf / 2, at, frm) if at > 0 else 0.0           # новий трек починає звучати трохи до склейки
        post = 0.0 if nxt >= total - 1e-3 else min(xf / 2, max(0.0, tdur - frm - run))
        y = _stereo_full(prof["path"], sr)
        a_i = int(round((frm - pre) * sr))
        b_i = int(round((frm + run + post) * sr))
        piece = y[max(0, a_i):min(len(y), b_i)].astype(np.float32) / 32768.0
        m = len(piece)
        if not m:
            i += 1
            continue
        g = np.ones(m, np.float32)
        fin = int(round((2 * pre if at > 0 else 0.4) * sr))
        fout = int(round((2 * post if nxt < total - 1e-3 else 0) * sr))
        if fin > 1:
            fin = min(fin, m)
            g[:fin] *= np.sin(np.linspace(0, np.pi / 2, fin)) ** 1
        if fout > 1:
            fout = min(fout, m)
            g[-fout:] *= np.cos(np.linspace(0, np.pi / 2, fout))
        o = int(round((at - pre) * sr))
        o0, o1 = max(0, o), min(n, o + m)
        if o1 > o0:
            mix[o0:o1] += piece[o0 - o:o1 - o] * g[o0 - o:o1 - o, None]
        played.append((round(at, 2), tid, round(frm, 2), round(at + run, 2)))
        i += 1
    if end_fade > 0 and n:
        k = min(n, int(end_fade * sr))
        mix[-k:] *= np.linspace(1, 0, k)[:, None] ** 1.5
    mix *= _duck_gain(n, sr, voice, bed_db, duck_db, ramp)[:, None]
    mix = np.clip(mix, -1, 1)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    return played


def clear_cache():
    _STEREO_CACHE.clear()
