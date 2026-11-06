"""
Svit Editor — стильний текст (слова пісні й субтитри) картинками з прозорим фоном.

Кожен рядок малюється у PNG розміром з кадр (Pillow): шрифт, колір, обведення, тінь, світіння, halation,
позиція за шаблоном. Ті самі функції малюють попередній перегляд у вікні, тож що бачиш у Svit — те й буде в DaVinci.
Анімацію (поява, підйом, поп, розмиття) робить DaVinci через Fusion.
"""
import base64
import io
import json
import shutil
import sys
from pathlib import Path

HOME = Path.home() / ".svit-editor"
USER_FONTS = HOME / "fonts"
FONT_DIRS = [USER_FONTS, Path.home() / "Library" / "Fonts", Path("/Library/Fonts"),
             Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"),
             Path("/usr/share/fonts")]
FONT_EXT = {".ttf", ".otf", ".ttc"}
DEFAULT_FONTS = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc",
                 "/Library/Fonts/Arial Unicode.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]

SIZES = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080), "4:3": (1440, 1080),
         "16:9": (1920, 1080)}

DEFAULT_STYLE = {"font": "", "size": 50, "color": "#FFFFFF", "outline": 0, "shadow": 40, "glow": 0,
                 "halation": 0, "pos": "bottom", "anim": "fade", "anim_strength": 50, "anim_smooth": 50,
                 "upper": False}


def canvas_size(fmt, resolution=""):
    if fmt in SIZES:
        return SIZES[fmt]
    try:
        w, h = [int(x) for x in str(resolution).lower().replace("×", "x").split("x")[:2]]
        if w > 0 and h > 0:
            return w, h
    except Exception:
        pass
    return 1920, 1080


# ------------------------------------------------------------------ шрифти
_FONTS = {"list": None}


def _face_name(path):
    from PIL import ImageFont
    try:
        f = ImageFont.truetype(str(path), 20)
        fam, sty = f.getname()
        return (fam + ("" if not sty or sty.lower() in ("regular", "normal", "roman") else " " + sty)).strip()
    except Exception:
        return None


def list_fonts(refresh=False):
    if _FONTS["list"] is not None and not refresh:
        return _FONTS["list"]
    seen, out = set(), []
    for d in FONT_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*")):
            if p.suffix.lower() not in FONT_EXT or p.name.startswith("."):
                continue
            name = _face_name(p)
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            out.append({"path": str(p), "name": name, "user": d == USER_FONTS})
    out.sort(key=lambda f: (not f["user"], f["name"].lower()))
    _FONTS["list"] = out
    return out


def import_font(src):
    src = Path(src)
    if src.suffix.lower() not in FONT_EXT:
        raise RuntimeError("Це не файл шрифту (потрібен .ttf, .otf або .ttc).")
    if not _face_name(src):
        raise RuntimeError("Шрифт не читається — можливо, файл пошкоджений.")
    USER_FONTS.mkdir(parents=True, exist_ok=True)
    dst = USER_FONTS / src.name
    shutil.copy2(src, dst)
    list_fonts(refresh=True)
    return str(dst)


def _font(path, px):
    from PIL import ImageFont
    for p in [path] + DEFAULT_FONTS:
        if p and Path(p).exists():
            try:
                return ImageFont.truetype(str(p), int(px))
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=int(px))
    except Exception:
        return ImageFont.load_default()


def _rgb(hexs, default=(255, 255, 255)):
    try:
        h = str(hexs).lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


# ------------------------------------------------------------------ малювання
def _wrap(draw, text, font, max_w, stroke):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if cur and draw.textlength(t, font=font) + stroke * 2 > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines or [""]


def position_box(pos, W, H, block_h):
    vertical = H > W
    top_m, bot_m = (0.14, 0.21) if vertical else (0.08, 0.09)
    if pos == "top":
        return int(H * top_m)
    if pos == "center":
        return int((H - block_h) / 2)
    return int(H * (1 - bot_m) - block_h)


def render(text, style, W, H):
    """RGBA-картинка W×H з текстом за стилем."""
    from PIL import Image, ImageDraw, ImageFilter
    st = dict(DEFAULT_STYLE, **(style or {}))
    if st.get("upper"):
        text = text.upper()
    base = min(W, H)
    px = max(10, int(base * (0.035 + 0.075 * float(st["size"]) / 100.0)))
    font = _font(st.get("font"), px)
    stroke = int(round(px * 0.09 * float(st["outline"]) / 100.0))
    probe = ImageDraw.Draw(Image.new("L", (8, 8)))
    lines = _wrap(probe, text, font, W * 0.84, stroke)
    asc, desc = font.getmetrics() if hasattr(font, "getmetrics") else (px, px // 4)
    lh = int((asc + desc) * 1.12)
    block_h = lh * len(lines)
    y0 = position_box(st.get("pos", "bottom"), W, H, block_h)
    color = _rgb(st["color"])

    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    for i, ln in enumerate(lines):
        tw = md.textlength(ln, font=font)
        md.text(((W - tw) / 2, y0 + i * lh), ln, font=font, fill=255, stroke_width=stroke, stroke_fill=255)
    fill_mask = Image.new("L", (W, H), 0)
    fd = ImageDraw.Draw(fill_mask)
    for i, ln in enumerate(lines):
        tw = fd.textlength(ln, font=font)
        fd.text(((W - tw) / 2, y0 + i * lh), ln, font=font, fill=255)

    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def layer(rgb, m, alpha_mul):
        a = m.point(lambda v: min(255, int(v * alpha_mul)))
        lay = Image.new("RGBA", (W, H), rgb + (0,))
        lay.putalpha(a)
        return lay

    sh = float(st["shadow"]) / 100.0
    if sh > 0:
        r = max(1, int(px * (0.04 + 0.12 * sh)))
        sm = mask.filter(ImageFilter.GaussianBlur(r))
        off = int(px * 0.05)
        sm = sm.transform((W, H), Image.AFFINE, (1, 0, -off, 0, 1, -off))
        out = Image.alpha_composite(out, layer((0, 0, 0), sm, 0.55 + 0.6 * sh))
    hal = float(st["halation"]) / 100.0
    if hal > 0:
        # halation: тонке тепле світіння впритул до літер, як на плівці
        r = max(1, int(px * (0.05 + 0.18 * hal)))
        hm = mask.filter(ImageFilter.GaussianBlur(r))
        out = Image.alpha_composite(out, layer((255, 92, 40), hm, 0.6 + 1.6 * hal))
    gl = float(st["glow"]) / 100.0
    if gl > 0:
        r = max(1, int(px * (0.08 + 0.45 * gl)))
        gm = mask.filter(ImageFilter.GaussianBlur(r))
        out = Image.alpha_composite(out, layer(color, gm, 0.5 + 1.5 * gl))
        r2 = max(1, int(px * 0.06))
        out = Image.alpha_composite(out, layer(tuple(min(255, c + 40) for c in color),
                                               mask.filter(ImageFilter.GaussianBlur(r2)), 0.5 * gl))
    if stroke:
        out = Image.alpha_composite(out, layer((0, 0, 0) if sum(color) > 380 else (255, 255, 255), mask, 1.0))
    out = Image.alpha_composite(out, layer(color, fill_mask, 1.0))
    return out


def render_items(chunks, style, W, H, out_dir, upper=False):
    """[{start,end,text}] → PNG-файли; повертає [{png,start,end}]. Сусідні рядки не перекриваються."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    st = dict(style or {})
    st["upper"] = bool(st.get("upper") or upper)
    items = sorted([c for c in chunks if c["text"].strip() and c["end"] - c["start"] > 0.15], key=lambda c: c["start"])
    res = []
    for i, c in enumerate(items, 1):
        end = c["end"]
        if i < len(items):
            end = min(end, items[i]["start"])
        if end - c["start"] < 0.15:
            continue
        p = out_dir / ("line%03d_svit.png" % i)     # без номера в кінці — інакше DaVinci склеїть їх у секвенцію
        render(c["text"], st, W, H).save(p, optimize=True)
        res.append({"png": str(p), "start": round(c["start"], 3), "end": round(end, 3), "text": c["text"]})
    return res


# ------------------------------------------------------------------ попередній перегляд
_BG = {}


def _frame(path, W, H):
    """Кадр з відео (близько третини тривалості), обрізаний під формат."""
    from PIL import Image
    key = (path, W, H)
    if key in _BG:
        return _BG[key].copy()
    img = None
    if path and Path(path).exists():
        try:
            import av
            with av.open(str(path)) as c:
                vs = c.streams.video[0]
                dur = float(c.duration or 0) / 1e6 if c.duration else 0
                if dur > 2:
                    c.seek(int(dur * 0.33 * 1e6))
                for fr in c.decode(vs):
                    img = fr.to_image()
                    break
        except Exception:
            img = None
    if img is None:
        img = Image.new("RGB", (W, H), (60, 66, 74))
        # м'який градієнт, щоб видно було світіння
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        for y in range(H):
            k = y / float(H)
            d.line([(0, y), (W, y)], fill=(int(70 + 90 * k), int(80 + 40 * k), int(110 - 40 * k)))
    sw, sh = img.size
    sc = max(W / float(sw), H / float(sh))
    img = img.resize((max(W, int(sw * sc)), max(H, int(sh * sc))))
    l, t = (img.size[0] - W) // 2, (img.size[1] - H) // 2
    img = img.crop((l, t, l + W, t + H)).convert("RGB")
    _BG.clear() if len(_BG) > 6 else None
    _BG[key] = img
    return img.copy()


def _url(img, fmt="PNG"):
    buf = io.BytesIO()
    img.save(buf, fmt, quality=82) if fmt == "JPEG" else img.save(buf, fmt)
    return "data:image/%s;base64," % fmt.lower() + base64.b64encode(buf.getvalue()).decode()


def preview(style, text, fmt, resolution="", bg_path=None, height=440):
    W, H = canvas_size(fmt, resolution)
    sc = height / float(H)
    pw, ph = max(2, int(W * sc)), int(height)
    # малюємо в половинному розмірі кадру (пропорції ті самі, що в DaVinci), потім зменшуємо
    k = max(1.0, H / 960.0)
    rw, rh = int(W / k), int(H / k)
    txt = render(text or "Приклад тексту на відео", style, rw, rh).resize((pw, ph))
    bg = _frame(bg_path, rw, rh).resize((pw, ph))
    return {"bg": _url(bg, "JPEG"), "text": _url(txt), "w": pw, "h": ph, "vertical": H > W}


if __name__ == "__main__":
    st = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    render(sys.argv[2] if len(sys.argv) > 2 else "Привіт, світе", st, 1080, 1920).save("/tmp/t.png")
