"""
Svit Editor — у якому профілі знято відео.
Sony пише це в сам файл MP4 (CaptureGammaEquation / CaptureColorPrimaries): PP1/709, S-Log3, S-Log2, HLG.
Потрібно, щоб монтувати лише з лог-кадрів.
"""
import re
from pathlib import Path


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
    if any(x in v for x in ("709", "cinetone", "cine", "still", "movie", "itu", "1886", "2.2", "2.4")):
        return "rec709"        # rec709, rec709-xvycc, s-cinetone, cine1…4, still — «звичайний» (не лог)
    return None                # незнайоме значення — не вгадуємо (у вікні «?» з тим, що записала камера)


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


def is_log(prof):
    """True — лог (S-Log3/S-Log2/HLG), False — звичайний 709 (PP1, S-Cinetone…), None — не вдалося визначити."""
    g = (prof or {}).get("gamma")
    if not g:
        return None
    return g != "rec709"


SHORT = {"slog3": "S-Log3", "slog2": "S-Log2", "hlg": "HLG", "rec709": "709"}
_CACHE = {}


def profile_info(path):
    """{"k": slog3 / slog2 / hlg / rec709 / None, "raw": що записала камера}. Кешується за розміром і часом файлу."""
    p = Path(path)
    try:
        st = p.stat()
        ck = (str(p), st.st_size, int(st.st_mtime))
    except Exception:
        return {"k": None, "raw": ""}
    if ck not in _CACHE:
        try:
            d = detect(p)
            _CACHE[ck] = {"k": d.get("gamma"), "raw": d.get("raw") or ""}
        except Exception:
            _CACHE[ck] = {"k": None, "raw": ""}
    return _CACHE[ck]


def profile_key(path):
    return profile_info(path)["k"]
