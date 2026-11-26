// Svit Film — ядро обробки (без залежності від OpenFX, щоб його можна було перевіряти окремо).
// Та сама математика, що й у Svit Film.dctl, але розмиття для halation/bloom — справжнє
// гаусове на зменшеній копії кадру: швидко навіть на процесорі і без «зернистого» сяйва.
#pragma once
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <thread>
#include <vector>

namespace svitfilm {

enum Input { IN_REC709 = 0, IN_DI, IN_SLOG3, IN_LOGC3 };
enum Look { L_NEUTRAL = 0, L_WARM, L_TUNGSTEN, L_PASTEL, L_VIVID, L_FADED, L_BW, L_BLEACH };

static const char* kInputNames[] = {"Rec709 Gamma 2.4", "DaVinci Intermediate", "Sony S-Log3", "ARRI LogC3"};
static const char* kLookNames[] = {"Neutral Negative", "Warm Day 250", "Tungsten Night 500", "Pastel Portrait 160",
                                   "Vivid Slide 100", "Faded 70s", "BW 400", "Bleach Bypass"};
static const int kNumInputs = 4, kNumLooks = 8;

struct Params {
    int input = IN_REC709, look = L_WARM;
    double exposure = 0, contrast = 1, saturation = 1, temp = 0, tint = 0, fade = 0;
    double halation = 0.5, halSize = 1, bloom = 0.2;
    double grain = 0.5, grainSize = 1, grainColour = 0.3;
    double vignette = 0.25, weave = 0;
    bool freezeGrain = false;
    double frame = 0;   // номер кадру — для живого зерна й дрижання
};

struct LookDef { float c[3], s[3], lo[3], hi[3], sat; int bw; };
static const LookDef kLooks[] = {
    {{1.00f, 1.00f, 1.00f}, {0.00f, 0.00f, 0.00f}, {0.025f, 0.025f, 0.030f}, {0.965f, 0.960f, 0.950f}, 1.00f, 0},
    {{1.02f, 1.00f, 0.94f}, {0.16f, 0.04f, -0.14f}, {0.030f, 0.034f, 0.040f}, {0.975f, 0.955f, 0.900f}, 1.08f, 0},
    {{0.92f, 0.98f, 1.06f}, {-0.12f, 0.02f, 0.16f}, {0.020f, 0.032f, 0.048f}, {0.950f, 0.960f, 0.965f}, 0.92f, 0},
    {{0.80f, 0.82f, 0.80f}, {0.10f, 0.06f, 0.00f}, {0.055f, 0.055f, 0.060f}, {0.960f, 0.950f, 0.930f}, 0.82f, 0},
    {{1.30f, 1.28f, 1.34f}, {0.04f, 0.00f, -0.02f}, {0.006f, 0.006f, 0.012f}, {0.985f, 0.980f, 0.975f}, 1.30f, 0},
    {{0.86f, 0.90f, 0.78f}, {0.20f, 0.14f, -0.20f}, {0.090f, 0.075f, 0.070f}, {0.930f, 0.910f, 0.840f}, 0.85f, 0},
    {{1.10f, 1.10f, 1.10f}, {0.00f, 0.00f, 0.00f}, {0.020f, 0.020f, 0.020f}, {0.970f, 0.970f, 0.970f}, 0.00f, 1},
    {{1.35f, 1.35f, 1.35f}, {0.02f, 0.00f, 0.02f}, {0.012f, 0.012f, 0.014f}, {0.975f, 0.975f, 0.970f}, 0.45f, 0},
};

static const float BASE_S = 0.62f, MID = 0.46f, HI_BOOST = 1.30f;

inline float decode(float v, int mode) {
    switch (mode) {
    case IN_DI: return v <= 0.02740668f ? v / 10.44426855f : std::exp2(v / 0.07329248f - 7.0f) - 0.0075f;
    case IN_SLOG3: {
        float x = v * 1023.0f;
        return x >= 171.2102946929f ? std::pow(10.0f, (x - 420.0f) / 261.5f) * 0.19f - 0.01f
                                    : (x - 95.0f) * 0.01125f / (171.2102946929f - 95.0f);
    }
    case IN_LOGC3:
        return v > 5.367655f * 0.010591f + 0.092809f ? (std::pow(10.0f, (v - 0.385537f) / 0.247190f) - 0.052272f) / 5.555556f
                                                    : (v - 0.092809f) / 5.367655f;
    default: return std::pow(std::max(v, 0.0f), 2.4f);
    }
}

inline float film1(float lin, float s, float shift, float lo, float hi) {
    float le = std::log2(std::max(lin, 1e-6f) / 0.18f) + shift;
    float k0 = std::log((MID - lo) / (hi - MID));
    float x = s * le * (le > 0.0f ? HI_BOOST : 1.0f) + k0;
    return lo + (hi - lo) / (1.0f + std::exp(-x));
}

inline float fractf(float x) { return x - std::floor(x); }
inline float hash2(float x, float y, float s) {
    // цілочисельний хеш (швидший за sin) → [0, 1)
    uint32_t h = (uint32_t)(int32_t)x * 0x8da6b343u ^ (uint32_t)(int32_t)y * 0xd8163841u ^ (uint32_t)(int32_t)(s * 997.0f) * 0xcb1ab31fu;
    h ^= h >> 16; h *= 0x7feb352du; h ^= h >> 15; h *= 0x846ca68bu; h ^= h >> 16;
    return (h >> 8) * (1.0f / 16777216.0f);
}
inline float vnoise(float x, float y, float s) {
    float xi = std::floor(x), yi = std::floor(y), fx = x - xi, fy = y - yi;
    float ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy);
    float a = hash2(xi, yi, s), b = hash2(xi + 1, yi, s), c = hash2(xi, yi + 1, s), d = hash2(xi + 1, yi + 1, s);
    float ab = a + (b - a) * ux, cd = c + (d - c) * ux;
    return ab + (cd - ab) * uy;
}

// таблиця для гладкої функції на відрізку [a, b] з лінійною інтерполяцією
struct Lut {
    float a = 0, b = 1, inv = 1; std::vector<float> t;
    template <class F> void build(float a_, float b_, int n, F f) {
        a = a_; b = b_; t.resize(n + 1); inv = n / (b - a);
        for (int i = 0; i <= n; ++i) t[i] = f(a + (b - a) * i / n);
    }
    float operator()(float x) const {
        float u = (std::clamp(x, a, b) - a) * inv; int i = std::min((int)u, (int)t.size() - 2);
        return t[i] + (t[i + 1] - t[i]) * (u - i);
    }
};

template <class F> void parallelRows(int h, F f) {
    int n = std::max(1u, std::min(32u, std::thread::hardware_concurrency()));
    if (h < 64) n = 1;
    std::vector<std::thread> th;
    for (int t = 0; t < n; ++t)
        th.emplace_back([=, &f] { for (int y = t; y < h; y += n) f(y); });
    for (auto& x : th) x.join();
}

// гаусове розмиття (окремо по рядках і стовпцях) одноканального або 3-канального буфера
inline void gaussBlur(std::vector<float>& buf, int w, int h, int ch, float sigma) {
    if (sigma < 0.3f || w < 2 || h < 2) return;
    int r = std::min(std::max(1, (int)std::ceil(sigma * 2.5f)), 512);
    std::vector<float> k(2 * r + 1);
    float sum = 0;
    for (int i = -r; i <= r; ++i) sum += (k[i + r] = std::exp(-0.5f * i * i / (sigma * sigma)));
    for (auto& v : k) v /= sum;
    std::vector<float> tmp(buf.size());
    parallelRows(h, [&](int y) {
        for (int x = 0; x < w; ++x)
            for (int c = 0; c < ch; ++c) {
                float a = 0;
                for (int i = -r; i <= r; ++i) a += k[i + r] * buf[((size_t)y * w + std::clamp(x + i, 0, w - 1)) * ch + c];
                tmp[((size_t)y * w + x) * ch + c] = a;
            }
    });
    parallelRows(h, [&](int y) {
        for (int x = 0; x < w; ++x)
            for (int c = 0; c < ch; ++c) {
                float a = 0;
                for (int i = -r; i <= r; ++i) a += k[i + r] * tmp[((size_t)std::clamp(y + i, 0, h - 1) * w + x) * ch + c];
                buf[((size_t)y * w + x) * ch + c] = a;
            }
    });
}

// білінійна вибірка зі зменшеного буфера
inline float sampleSmall(const std::vector<float>& b, int sw, int sh, int ch, int c, float x, float y) {
    x = std::clamp(x, 0.0f, (float)sw - 1.001f); y = std::clamp(y, 0.0f, (float)sh - 1.001f);
    int x0 = (int)x, y0 = (int)y; float fx = x - x0, fy = y - y0;
    auto at = [&](int xx, int yy) { return b[((size_t)yy * sw + xx) * ch + c]; };
    float a = at(x0, y0) + (at(x0 + 1, y0) - at(x0, y0)) * fx;
    float d = at(x0, y0 + 1) + (at(x0 + 1, y0 + 1) - at(x0, y0 + 1)) * fx;
    return a + (d - a) * fy;
}

// src/dst: RGBA float, рядки по rowFloats чисел (може бути більше за w*4). Розміри однакові.
inline void render(const float* src, std::ptrdiff_t srcRowFloats, float* dst, std::ptrdiff_t dstRowFloats,
                   int w, int h, const Params& p) {
    const float sc = w / 1920.0f;
    const float ev = std::exp2((float)p.exposure);
    const float seed = p.freezeGrain ? 0.0f : fractf((float)p.frame * 0.618034f) * 100.0f;
    const int dx = (int)std::lround((hash2(seed, 1, 0) - 0.5f) * 2.0f * p.weave * 3.0f * sc);
    const int dy = (int)std::lround((hash2(seed, 2, 0) - 0.5f) * 2.0f * p.weave * 2.0f * sc);

    // 1) лінійне світло (з дрижанням кадру)
    std::vector<float> lin((size_t)w * h * 3);
    Lut dec; dec.build(0.0f, 1.0f, 8192, [&](float v) { return decode(v, p.input); });
    auto decodeFast = [&](float v) { return (v >= 0.0f && v <= 1.0f) ? dec(v) : decode(v, p.input); };
    parallelRows(h, [&](int y) {
        int yy = std::clamp(y + dy, 0, h - 1);
        const float* row = src + (std::ptrdiff_t)yy * srcRowFloats;
        for (int x = 0; x < w; ++x) {
            int xx = std::clamp(x + dx, 0, w - 1);
            for (int c = 0; c < 3; ++c) lin[((size_t)y * w + x) * 3 + c] = decodeFast(row[xx * 4 + c]) * ev;
        }
    });

    // 2) halation і bloom — на зменшеній у 4 рази копії
    const int ds = 4, sw = std::max(1, (w + ds - 1) / ds), shh = std::max(1, (h + ds - 1) / ds);
    std::vector<float> hal, blo;
    if (p.halation > 0 || p.bloom > 0) {
        if (p.halation > 0) hal.assign((size_t)sw * shh, 0.0f);
        if (p.bloom > 0) blo.assign((size_t)sw * shh * 3, 0.0f);
        parallelRows(shh, [&](int sy) {
            for (int sx = 0; sx < sw; ++sx) {
                float hs = 0, b[3] = {0, 0, 0}; int n = 0;
                for (int j = 0; j < ds; ++j) for (int i = 0; i < ds; ++i) {
                    int x = sx * ds + i, y = sy * ds + j;
                    if (x >= w || y >= h) continue;
                    const float* L = &lin[((size_t)y * w + x) * 3];
                    hs += std::max(0.2126f * L[0] + 0.7152f * L[1] + 0.0722f * L[2] - 0.8f, 0.0f);
                    for (int c = 0; c < 3; ++c) b[c] += std::max(L[c] - 0.35f, 0.0f);
                    ++n;
                }
                n = std::max(n, 1);
                if (!hal.empty()) hal[(size_t)sy * sw + sx] = hs / n;
                if (!blo.empty()) for (int c = 0; c < 3; ++c) blo[((size_t)sy * sw + sx) * 3 + c] = b[c] / n;
            }
        });
        if (!hal.empty()) gaussBlur(hal, sw, shh, 1, 14.0f * (float)p.halSize * sc * 0.55f / ds);
        if (!blo.empty()) gaussBlur(blo, sw, shh, 3, 46.0f * sc * 0.55f / ds);
    }

    const LookDef& lk = kLooks[std::clamp(p.look, 0, kNumLooks - 1)];
    const float fl = (float)p.fade * 0.12f, fh = (float)p.fade * 0.03f;
    const float tR = std::exp2((float)p.temp * 0.35f), tG = std::exp2((float)-p.tint * 0.25f), tB = std::exp2((float)-p.temp * 0.35f);
    const float S = lk.sat * (float)p.saturation;
    const float gs = std::max(0.5f, 1.6f * (float)p.grainSize * sc);
    // криві плівки як таблиці від log2(світла): −20…+12 стопів
    Lut film[3];
    for (int c = 0; c < 3; ++c) {
        float s_ = BASE_S * lk.c[c] * (float)p.contrast, sh = lk.s[c], lo = lk.lo[c] + fl, hi = lk.hi[c] - fh;
        film[c].build(-20.0f, 12.0f, 4096, [&](float l2) { return film1(std::exp2(l2), s_, sh, lo, hi); });
    }

    parallelRows(h, [&](int y) {
        const float* srow = src + (std::ptrdiff_t)y * srcRowFloats;
        float* drow = dst + (std::ptrdiff_t)y * dstRowFloats;
        for (int x = 0; x < w; ++x) {
            float L[3];
            for (int c = 0; c < 3; ++c) L[c] = lin[((size_t)y * w + x) * 3 + c];
            float fx = (x + 0.5f) / ds - 0.5f, fy = (y + 0.5f) / ds - 0.5f;
            if (!hal.empty()) {
                float hh = sampleSmall(hal, sw, shh, 1, 0, fx, fy) * (float)p.halation * 4.0f;
                L[0] += hh; L[1] += hh * 0.32f; L[2] += hh * 0.07f;
            }
            if (!blo.empty())
                for (int c = 0; c < 3; ++c) L[c] += sampleSmall(blo, sw, shh, 3, c, fx, fy) * (float)p.bloom * 0.6f;
            if (p.vignette > 0) {
                float nx = (x - w * 0.5f) / (w * 0.5f), ny = (y - h * 0.5f) / (w * 0.5f);
                float r = std::sqrt(nx * nx + ny * ny) / 0.75f;
                float t = std::clamp((r - 0.45f) / 0.8f, 0.0f, 1.0f);
                t = t * t * (3 - 2 * t);
                float v = 1.0f - (float)p.vignette * 0.85f * t;
                for (auto& c : L) c *= v;
            }
            L[0] *= tR; L[1] *= tG; L[2] *= tB;
            if (lk.bw) { float m = 0.30f * L[0] + 0.62f * L[1] + 0.08f * L[2]; L[0] = L[1] = L[2] = m; }
            float o[3];
            for (int c = 0; c < 3; ++c) o[c] = film[c](std::log2(std::max(L[c], 1e-6f)));
            float Yl = 0.2126f * o[0] + 0.7152f * o[1] + 0.0722f * o[2];
            for (auto& c : o) c = Yl + (c - Yl) * S;
            if (p.grain > 0) {
                float gx = x / gs, gy = y / gs;
                float n0 = vnoise(gx, gy, seed) - 0.5f;
                n0 += 0.5f * (vnoise(gx * 2.1f + 17, gy * 2.1f + 3, seed) - 0.5f);
                float nr = vnoise(gx + 31, gy + 7, seed) - 0.5f, nb = vnoise(gx + 59, gy + 13, seed) - 0.5f;
                float Yg = 0.2126f * o[0] + 0.7152f * o[1] + 0.0722f * o[2];
                float amp = (float)p.grain * 0.11f * (0.35f + 2.6f * Yg * (1 - Yg));
                float gc = (float)p.grainColour;
                o[0] += (n0 * (1 - gc) + nr * gc) * amp; o[1] += n0 * amp; o[2] += (n0 * (1 - gc) + nb * gc) * amp;
            }
            for (int c = 0; c < 3; ++c) drow[x * 4 + c] = std::clamp(o[c], 0.0f, 1.0f);
            drow[x * 4 + 3] = srow[x * 4 + 3];
        }
    });
}

}  // namespace svitfilm
