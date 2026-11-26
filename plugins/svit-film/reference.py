"""Еталонна копія математики Svit Film (той самий алгоритм, що й у Svit Film.dctl) — для перевірки вигляду."""
import math
import numpy as np
from PIL import Image

# ---- плівки: (контраст R,G,B), (зсув R,G,B у стопах), (чорне R,G,B), (біле R,G,B), насиченість, ч/б
LOOKS = {
    "Neutral Negative": ((1.00, 1.00, 1.00), (0.00, 0.00, 0.00), (0.025, 0.025, 0.030), (0.965, 0.960, 0.950), 1.00, 0),
    "Warm Day 250":     ((1.02, 1.00, 0.94), (0.16, 0.04, -0.14), (0.030, 0.034, 0.040), (0.975, 0.955, 0.900), 1.08, 0),
    "Tungsten Night 500": ((0.92, 0.98, 1.06), (-0.12, 0.02, 0.16), (0.020, 0.032, 0.048), (0.950, 0.960, 0.965), 0.92, 0),
    "Pastel Portrait 160": ((0.80, 0.82, 0.80), (0.10, 0.06, 0.00), (0.055, 0.055, 0.060), (0.960, 0.950, 0.930), 0.82, 0),
    "Vivid Slide 100":  ((1.30, 1.28, 1.34), (0.04, 0.00, -0.02), (0.006, 0.006, 0.012), (0.985, 0.980, 0.975), 1.30, 0),
    "Faded 70s":        ((0.86, 0.90, 0.78), (0.20, 0.14, -0.20), (0.090, 0.075, 0.070), (0.930, 0.910, 0.840), 0.85, 0),
    "BW 400":           ((1.10, 1.10, 1.10), (0.00, 0.00, 0.00), (0.020, 0.020, 0.020), (0.970, 0.970, 0.970), 0.00, 1),
    "Bleach Bypass":    ((1.35, 1.35, 1.35), (0.02, 0.00, 0.02), (0.012, 0.012, 0.014), (0.975, 0.975, 0.970), 0.45, 0),
}
BASE_S = 0.62          # нахил кривої плівки (на стоп), домножується на «контраст»
MID = 0.46             # куди лягає 18% сірий
HI_BOOST = 1.30        # у світлих тонах крива крутіша — біле лишається білим


def decode(v, mode):
    if mode == "rec709":
        return np.power(np.clip(v, 0, None), 2.4)
    if mode == "di":  # DaVinci Intermediate
        return np.where(v <= 0.02740668, v / 10.44426855, np.power(2.0, v / 0.07329248 - 7.0) - 0.0075)
    if mode == "slog3":
        x = v * 1023.0
        return np.where(x >= 171.2102946929, np.power(10.0, (x - 420.0) / 261.5) * 0.19 - 0.01,
                        (x - 95.0) * 0.01125 / (171.2102946929 - 95.0))
    if mode == "logc3":
        return np.where(v > 5.367655 * 0.010591 + 0.092809, (np.power(10.0, (v - 0.385537) / 0.247190) - 0.052272) / 5.555556,
                        (v - 0.092809) / 5.367655)
    raise ValueError(mode)


def fract(x):
    return x - np.floor(x)


def hash2(x, y, s):
    return fract(np.sin(x * 12.9898 + y * 78.233 + s * 37.719) * 43758.5453)


def vnoise(x, y, s):
    """Значеннєвий шум: гладка інтерполяція між випадковими значеннями у вузлах сітки."""
    xi, yi = np.floor(x), np.floor(y)
    fx, fy = x - xi, y - yi
    ux, uy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = hash2(xi, yi, s), hash2(xi + 1, yi, s)
    c, d = hash2(xi, yi + 1, s), hash2(xi + 1, yi + 1, s)
    return (a + (b - a) * ux) + ((c + (d - c) * ux) - (a + (b - a) * ux)) * uy


N_SAMPLES = 24


def spiral(i):
    """Точки розмиття: спіраль із золотим кутом, рівномірно в колі радіуса 1."""
    r = math.sqrt((i + 0.5) / N_SAMPLES)
    a = i * 2.39996323
    return r * math.cos(a), r * math.sin(a)


def render(img, mode="rec709", look="Warm Day 250", exposure=0.0, contrast=1.0, saturation=1.0,
           halation=0.5, hal_radius=1.0, bloom=0.2, grain=0.5, grain_size=1.0, grain_color=0.3,
           vignette=0.25, weave=0.0, seed=0.0, temp=0.0, tint=0.0, fade=0.0):
    src = np.asarray(img).astype(np.float32) / 255.0
    H, W = src.shape[:2]
    sc = W / 1920.0
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)

    # дрижання кадру (gate weave): одне зміщення на кадр
    dx = (hash2(seed, 1.0, 0.0) - 0.5) * 2 * weave * 3.0 * sc
    dy = (hash2(seed, 2.0, 0.0) - 0.5) * 2 * weave * 2.0 * sc

    def tex(ox, oy):
        xx = np.clip(np.round(xs + dx + ox), 0, W - 1).astype(int)
        yy = np.clip(np.round(ys + dy + oy), 0, H - 1).astype(int)
        return src[yy, xx]

    ev = 2.0 ** exposure

    def lin_at(ox, oy):
        return decode(tex(ox, oy), mode) * ev

    lin = lin_at(0, 0)

    # halation: червонувате сяйво навколо яскравого
    if halation > 0:
        R = 14.0 * hal_radius * sc
        acc = np.zeros((H, W), np.float32)
        for i in range(N_SAMPLES):
            sx, sy = spiral(i)
            s = lin_at(sx * R, sy * R)
            L = 0.2126 * s[..., 0] + 0.7152 * s[..., 1] + 0.0722 * s[..., 2]
            acc += np.maximum(L - 0.8, 0)
        h = acc / N_SAMPLES * halation * 4.0
        lin = lin + np.stack([h * 1.0, h * 0.32, h * 0.07], -1)
    # bloom: м'яке світіння від світлих ділянок
    if bloom > 0:
        R = 46.0 * sc
        acc = np.zeros_like(lin)
        for i in range(N_SAMPLES):
            sx, sy = spiral(i)
            s = lin_at(sx * R, sy * R)
            acc += np.maximum(s - 0.35, 0)
        lin = lin + acc / N_SAMPLES * bloom * 0.6

    # віньєтка (в лінійному світлі, як в об'єктиві)
    if vignette > 0:
        nx = (xs - W * 0.5) / (W * 0.5)
        ny = (ys - H * 0.5) / (W * 0.5)
        r = np.sqrt(nx * nx + ny * ny) / 0.75
        t = np.clip((r - 0.45) / (1.25 - 0.45), 0, 1)
        t = t * t * (3 - 2 * t)
        lin = lin * (1 - vignette * 0.85 * t)[..., None]

    # баланс білого (температура/відтінок) до плівки
    lin = lin * np.array([2 ** (temp * 0.35), 2 ** (-tint * 0.25), 2 ** (-temp * 0.35)], np.float32)

    cs, sh, lo, hi, sat, bw = LOOKS[look]
    if bw:
        L = 0.30 * lin[..., 0] + 0.62 * lin[..., 1] + 0.08 * lin[..., 2]
        lin = np.stack([L, L, L], -1)
    le = np.log2(np.maximum(lin, 1e-6) / 0.18)
    out = np.empty_like(lin)
    for c in range(3):
        lo_c = lo[c] + fade * 0.12
        hi_c = hi[c] - fade * 0.03
        k0 = math.log((MID - lo_c) / (hi_c - MID))
        s = BASE_S * cs[c] * contrast
        e = le[..., c] + sh[c]
        x = s * e * np.where(e > 0, HI_BOOST, 1.0) + k0
        out[..., c] = lo_c + (hi_c - lo_c) / (1 + np.exp(-x))
    Y = 0.2126 * out[..., 0] + 0.7152 * out[..., 1] + 0.0722 * out[..., 2]
    out = Y[..., None] + (out - Y[..., None]) * (sat * saturation)

    # зерно: сильніше в середніх тонах, анімоване (seed змінюється щокадру)
    if grain > 0:
        gs = max(0.5, 1.6 * grain_size * sc)
        n0 = vnoise(xs / gs, ys / gs, seed) - 0.5
        n0 = n0 + 0.5 * (vnoise(xs / gs * 2.1 + 17.0, ys / gs * 2.1 + 3.0, seed) - 0.5)
        nr = vnoise(xs / gs + 31.0, ys / gs + 7.0, seed) - 0.5
        nb = vnoise(xs / gs + 59.0, ys / gs + 13.0, seed) - 0.5
        Y = 0.2126 * out[..., 0] + 0.7152 * out[..., 1] + 0.0722 * out[..., 2]
        amp = grain * 0.11 * (0.35 + 2.6 * Y * (1 - Y))
        gc = grain_color
        out = out + np.stack([n0 * (1 - gc) + nr * gc, n0, n0 * (1 - gc) + nb * gc], -1) * amp[..., None]

    out = np.clip(out, 0, 1)
    return Image.fromarray((out * 255 + 0.5).astype(np.uint8))


def chart(W=1280, H=720):
    """Нейтральна тестова сцена: сіра шкала, кольорові плашки, шкіра, небо й яскраві вогні."""
    img = np.zeros((H, W, 3), np.float32)
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    # небо-градієнт
    sky = np.stack([0.25 + 0.25 * ys / H, 0.42 + 0.2 * ys / H, 0.75 - 0.1 * ys / H], -1)
    img[:] = sky
    # підлога/стіна
    img[int(H * 0.55):] = [0.30, 0.22, 0.16]
    # сіра шкала (лінійна експозиція -6..+3 стопи), записана у Rec.709
    n = 12
    for i in range(n):
        lin = 0.18 * 2 ** (-6 + 9 * i / (n - 1))
        v = min(1.0, lin ** (1 / 2.4))
        x0 = int(40 + i * (W - 80) / n)
        img[int(H * 0.62):int(H * 0.72), x0:x0 + int((W - 80) / n) - 4] = v
    # кольорові плашки
    cols = [(0.75, 0.2, 0.2), (0.2, 0.65, 0.25), (0.2, 0.3, 0.8), (0.9, 0.8, 0.2), (0.85, 0.35, 0.75),
            (0.2, 0.75, 0.8), (0.85, 0.6, 0.48), (0.55, 0.38, 0.30)]
    for i, c in enumerate(cols):
        x0 = int(40 + i * (W - 80) / len(cols))
        img[int(H * 0.78):int(H * 0.92), x0:x0 + int((W - 80) / len(cols)) - 6] = c
    # «обличчя»: тон шкіри з освітленням
    cx, cy = W * 0.25, H * 0.33
    r = np.sqrt((xs - cx) ** 2 + ((ys - cy) * 1.2) ** 2)
    m = r < H * 0.17
    shade = np.clip(1.15 - (xs - cx + 40) / (H * 0.4), 0.45, 1.2)
    img[m] = (np.array([0.86, 0.62, 0.50]) * shade[m][:, None])
    # вогні сцени (для halation) — переекспоновані точки й лінія неону
    for (lx, ly, rad) in [(W * 0.62, H * 0.18, 10), (W * 0.72, H * 0.24, 7), (W * 0.82, H * 0.15, 12), (W * 0.9, H * 0.3, 5)]:
        rr = np.sqrt((xs - lx) ** 2 + (ys - ly) ** 2)
        img[rr < rad] = 1.0
    img[int(H * 0.44):int(H * 0.455), int(W * 0.55):int(W * 0.95)] = [1.0, 0.95, 0.9]
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))


if __name__ == "__main__":
    import sys
    c = chart()
    c.save("chart.png")
    frame = Image.open("frame_piano.png").convert("RGB")
    tiles = []
    for name in LOOKS:
        a = render(c, look=name, seed=3.0).resize((640, 360))
        tiles.append((name, a))
    from PIL import ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except Exception:
        font = None
    sheet = Image.new("RGB", (640 * 3, 360 * 3), (20, 20, 20))
    sheet.paste(c.resize((640, 360)), (0, 0))
    ImageDraw.Draw(sheet).text((12, 10), "ORIGINAL", fill=(255, 255, 255), font=font)
    for i, (name, a) in enumerate(tiles):
        k = i + 1
        x, y = (k % 3) * 640, (k // 3) * 360
        sheet.paste(a, (x, y))
        d = ImageDraw.Draw(sheet)
        d.text((x + 12, y + 10), name.upper(), fill=(255, 255, 255), font=font)
    sheet.save("looks_chart.jpg", quality=88)
    print("ok")
