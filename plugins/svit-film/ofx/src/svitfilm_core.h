// Svit Film 2 — ядро емуляції плівки (без залежності від OpenFX, щоб його можна було тестувати окремо).
//
// Конвеєр (FILM_EMULATION_MASTER_SPEC.md §5), усе в лінійному робочому просторі Rec.2020 D65:
//   вхід → сцена-лінійне світло → експозиція / баланс білого → вінетка → MTF емульсії → halation
//   (фізичне ядро відбиття від основи) + bloom → log-експозиція (blacks / whites / компресія / міжшарові ефекти)
//   → проявлення негативу (крива щільності) → зерно в щільності → друк (2383/2393/3513DI) або скан /
//   пряме проєктування слайда → дисплей-лінійне світло → вихідний простір → Expand.
//
// УВАГА: криві плівок зараз — experimental_seeds (оцінки, див. profiles/ і docs/COVERAGE.md),
// а не оцифровані дані виробника. Плагін показує це в полі «Profile Status».
#pragma once
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <thread>
#include <vector>

#include "profiles_gen.h"

namespace svitfilm {

// ---------------- вибори в інтерфейсі
enum Input { IN_REC709 = 0, IN_REC2020, IN_APPLE20, IN_ACESCCT, IN_DWG709, IN_DWGDI, IN_CINEON, IN_SLOG3, IN_LOGC3 };
static const char* kInputNames[] = {"Rec.709",         "Rec.2020",           "Apple Gamma 2.0",
                                    "ACEScct (AP1)",   "DVR WG/Rec709",      "DVR WG/Intermediate",
                                    "Cineon Film Log", "Sony S-Log3 / SGamut3.Cine", "ARRI LogC3 / AWG3"};
static const int kNumInputs = 9;

enum Output { OUT_REC709 = 0, OUT_REC2020, OUT_P3, OUT_APPLE20, OUT_SRGB };
static const char* kOutputNames[] = {"Rec.709 Gamma 2.4", "Rec.2020 Gamma 2.4", "P3-D65 Gamma 2.6", "Apple Gamma 2.0",
                                     "sRGB"};
static const int kNumOutputs = 5;

static const float kGaugeWidthMM[] = {5.79f, 12.52f, 24.89f, 52.48f};   // ширина кадру: Super 8, Super 16, Super 35, 65 мм

static const char* kGrainProfileNames[] = {"Custom", "8 mm ISO 50", "8 mm ISO 250", "8 mm ISO 500",
    "16 mm ISO 50", "16 mm ISO 250", "16 mm ISO 500", "35 mm ISO 50", "35 mm ISO 250", "35 mm ISO 500",
    "65 mm ISO 50", "65 mm ISO 250", "65 mm ISO 500"};
static const int kNumGrainProfiles = 13;
// RMS-гранулярність σ×1000 на апертурі 48 мкм (стандарт Kodak/ANSI, щільність 1.0 над основою) і розмір
// хмарки барвника в мкм для ISO 50/250/500. ОЦІНКИ: кольорові негативи ISO 100–800 мають σ×1000 ≈ 4–5
// (Fuji Super G, патент US6667815); точні значення — з кривих granularity у тех. листах.
static const float kIsoSigma48[] = {0.0030f, 0.0045f, 0.0060f};
static const float kIsoGrainUM[] = {6.0f, 9.0f, 12.0f};
static const char* kHalProfileNames[] = {"Custom", "8 mm / Super 8", "8 mm / Super 8 No Remjet", "16 mm / Super 16",
    "16 mm / Super 16 No Remjet", "35 mm / Super 35", "35 mm / Super 35 No Remjet", "65 mm / 70 mm",
    "65 mm / 70 mm No Remjet"};
static const int kNumHalProfiles = 9;
static const char* kFilmTypeNames[] = {"Negative", "Positive"};
static const char* kGrainModeNames[] = {"Analogue", "Digital"};
static const char* kStorageNames[] = {"Fridge", "Room", "Hot Car"};
static const float kStorageRate[] = {0.4f, 1.0f, 2.2f};
static const char* kLeakPosNames[] = {"Left", "Right", "Top", "Bottom", "Random"};
static const char* kColorModeNames[] = {"Normal", "Luminance"};
static const int kNumColorModes = 2;

// друк: kPrints[0..kNumPrints-1] + «Film Scan» (без друку)
inline int printScanIndex() { return kNumPrints; }

enum Class { CL_NEG = 0, CL_REV = 1, CL_BW = 2 };

struct Params {
    int input = IN_REC709, output = OUT_REC709;
    // Exposure
    double exposure = 0, blacks = 0, whites = 0, temp = 0, tint = 0;
    // Film
    bool filmOn = true; int stock = 1; double pushPull = 0;
    // Film Developer
    bool devOn = false; double contrastBoost = 0, gammaCorr = 0, colorSep = 100, colorBoost = 0;
    // Film Compression
    bool compOn = false; double impact = 60, compWhite = 100, tonalRange = 30, colorDensity = 50;
    // Print
    bool printOn = true; int print = 0; double printExposure = 0, lightR = 0, lightG = 0, lightB = 0;
    // Halation (як у Dehancer: профіль формату/remjet + повзунки)
    bool halOn = false; int halProfile = 0;
    double srcLimiter = 15, bgGain = 80, smoothness = 50, localDiff = 15, globalDiff = 25, amplify = 70, hue = 50,
           blueComp = 100, halImpact = 70;
    bool maskMode = false;
    // Bloom (розсіювання в об'єктиві)
    double bloom = 0;
    // Film Grain
    bool grainOn = false; int grainProfile = 0;
    double grainSize = 12, grainAmount = 35, filmRes = 75, gShadows = 30, gMid = 55, gHigh = 65, chroma = 65;
    int filmType = 0, grainMode = 0; bool freezeGrain = false;
    // Camera
    double vignette = 0, weave = 0;
    // Expired Film (унікальне Svit): вік плівки і умови зберігання
    double age = 0; int storage = 1;
    // Light Leak (унікальне Svit): засвітка крізь щілину касети/дверцят камери
    double leak = 0, leakHue = 40, leakSpeed = 0.3; int leakPos = 4;
    // Lab: крос-процес і мерехтіння експозиції
    double cross = 0, flicker = 0;
    // Mix з нейтральним відтворенням
    double mix = 100;
    // Expand
    bool expandOn = true; double blackPoint = 0, whitePoint = 100; int colorMode = 0;
    // кадр і зсув зображення (щоб зерно не залежало від тайлів/обрізки)
    double frame = 0; int originX = 0, originY = 0;
    bool fastPreview = false;   // половинна роздільність для плавного перегляду
};

// ---------------- кольорові матриці (обчислені з первинних кольорів; Bradford D60→D65 для AP1)
struct M3 { float m[9]; };
inline void mul(const M3& M, const float* a, float* o) {
    float x = a[0], y = a[1], z = a[2];
    o[0] = M.m[0] * x + M.m[1] * y + M.m[2] * z;
    o[1] = M.m[3] * x + M.m[4] * y + M.m[5] * z;
    o[2] = M.m[6] * x + M.m[7] * y + M.m[8] * z;
}
static const M3 kI = {{1, 0, 0, 0, 1, 0, 0, 0, 1}};
static const M3 k709toW = {{0.627403896f, 0.329283038f, 0.043313066f, 0.069097289f, 0.919540395f, 0.011362316f, 0.016391439f, 0.088013308f, 0.895595253f}};
static const M3 kAP1toW = {{1.025824748f, -0.020053191f, -0.005771557f, -0.002234370f, 1.004586502f, -0.002352132f, -0.005013351f, -0.025290072f, 1.030303423f}};
static const M3 kDWGtoW = {{1.130302181f, -0.020392852f, -0.109909329f, -0.025547057f, 1.310849318f, -0.285302260f, -0.092598607f, -0.164653022f, 1.257251628f}};
static const M3 kSG3CtoW = {{0.960046344f, 0.119532979f, -0.079579323f, -0.052239480f, 1.264305747f, -0.212066268f, -0.028840507f, -0.059520968f, 1.088361475f}};
static const M3 kAWG3toW = {{0.990688119f, 0.092539656f, -0.083227775f, 0.046632234f, 1.187526852f, -0.234159086f, 0.001403589f, -0.094602004f, 1.093198415f}};
static const M3 kWto709 = {{1.660491002f, -0.587641139f, -0.072849863f, -0.124550475f, 1.132899897f, -0.008349423f, -0.018150763f, -0.100578898f, 1.118729661f}};
static const M3 kWtoP3 = {{1.343578253f, -0.282179671f, -0.061398582f, -0.065297453f, 1.075787916f, -0.010490463f, 0.002821787f, -0.019598495f, 1.016776707f}};
static const float kLumW[3] = {0.26270021f, 0.67799807f, 0.05930172f};   // Y для Rec.2020

inline const M3& inMatrix(int in) {
    switch (in) {
    case IN_REC2020: return kI;
    case IN_ACESCCT: return kAP1toW;
    case IN_DWG709: case IN_DWGDI: return kDWGtoW;
    case IN_SLOG3: return kSG3CtoW;
    case IN_LOGC3: return kAWG3toW;
    default: return k709toW;   // Rec.709, Apple Gamma 2.0, Cineon
    }
}
inline const M3& outMatrix(int out) {
    switch (out) {
    case OUT_REC2020: return kI;
    case OUT_P3: return kWtoP3;
    default: return kWto709;
    }
}
// дисплейні (вже «відрендерені») входи — для них світло сцени відновлюємо оберненим нейтральним конвеєром
inline bool displayReferred(int in) { return in == IN_REC709 || in == IN_REC2020 || in == IN_APPLE20 || in == IN_DWG709; }

// ---------------- передавальні функції
inline float spow(float v, float g) { return v > 0 ? std::pow(v, g) : 0.0f; }
inline float decodeTF(float v, int mode) {
    switch (mode) {
    case IN_APPLE20: return spow(v, 2.0f);
    case IN_ACESCCT:
        if (v <= 0.155251141552511f) return (v - 0.0729055341958355f) / 10.5402377416545f;
        return std::exp2(std::min(v, 1.468f) * 17.52f - 9.72f);
    case IN_DWGDI:
        return v <= 0.02740668f ? v / 10.44426855f : std::exp2(v / 0.07329248f - 7.0f) - 0.0075f;
    case IN_CINEON: {
        const float off = std::pow(10.0f, (95.0f - 685.0f) * 0.002f / 0.6f);
        return (std::pow(10.0f, (v * 1023.0f - 685.0f) * 0.002f / 0.6f) - off) / (1.0f - off);
    }
    case IN_SLOG3: {
        float x = v * 1023.0f;
        return x >= 171.2102946929f ? std::pow(10.0f, (x - 420.0f) / 261.5f) * 0.19f - 0.01f
                                    : (x - 95.0f) * 0.01125f / (171.2102946929f - 95.0f);
    }
    case IN_LOGC3:
        return v > 5.367655f * 0.010591f + 0.092809f ? (std::pow(10.0f, (v - 0.385537f) / 0.247190f) - 0.052272f) / 5.555556f
                                                    : (v - 0.092809f) / 5.367655f;
    default: return spow(v, 2.4f);   // Rec.709 / Rec.2020 / DWG-Rec709: дисплей BT.1886 (γ 2.4)
    }
}
inline float fastPow(float x, float e);
inline float encodeTF(float v, int out) {
    v = std::max(v, 0.0f);
    switch (out) {
    case OUT_P3: return fastPow(v, 1.0f / 2.6f);
    case OUT_APPLE20: return std::sqrt(v);
    case OUT_SRGB: return v <= 0.0031308f ? v * 12.92f : 1.055f * fastPow(v, 1.0f / 2.4f) - 0.055f;
    default: return fastPow(v, 1.0f / 2.4f);
    }
}
inline float decodeOutTF(float v, int out) {   // для перевірок
    switch (out) {
    case OUT_P3: return spow(v, 2.6f);
    case OUT_APPLE20: return spow(v, 2.0f);
    case OUT_SRGB: return v <= 0.04045f ? v / 12.92f : std::pow((v + 0.055f) / 1.055f, 2.4f);
    default: return spow(v, 2.4f);
    }
}

// ---------------- допоміжне
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

// DaVinci може рахувати кілька кадрів одночасно: ділимо ядра між ними, щоб не створювати сотні потоків
inline std::atomic<int>& activeRenders() { static std::atomic<int> a{0}; return a; }
struct RenderScope {
    RenderScope() { ++activeRenders(); }
    ~RenderScope() { --activeRenders(); }
};
template <class F> void parallelRows(int h, F f) {
    int hw = (int)std::max(1u, std::min(32u, std::thread::hardware_concurrency()));
    int n = std::max(1, hw / std::max(1, activeRenders().load()));
    if (h < 64) n = 1;
    std::vector<std::thread> th;
    for (int t = 0; t < n; ++t) th.emplace_back([=, &f] { for (int y = t; y < h; y += n) f(y); });
    for (auto& x : th) x.join();
}

// розділюване гаусове розмиття; повертає sqrt(Σk²) для одного напрямку (для нормування шуму)
inline float gaussBlur(std::vector<float>& buf, int w, int h, int ch, float sigma) {
    if (sigma < 0.3f || w < 2 || h < 2) return 1.0f;
    int r = std::min(std::max(1, (int)std::ceil(sigma * 2.6f)), 768);
    std::vector<float> k(2 * r + 1);
    float sum = 0, sq = 0;
    for (int i = -r; i <= r; ++i) sum += (k[i + r] = std::exp(-0.5f * i * i / (sigma * sigma)));
    for (auto& v : k) { v /= sum; sq += v * v; }
    std::vector<float> tmp(buf.size());
    const int rowN = w * ch;
    // по рядках: рядок з полями (без clamp у внутрішньому циклі)
    parallelRows(h, [&](int y) {
        std::vector<float> pad((size_t)(w + 2 * r) * ch);
        const float* in = &buf[(size_t)y * rowN];
        for (int x = -r; x < w + r; ++x) {
            const float* sp = in + std::clamp(x, 0, w - 1) * ch;
            for (int c = 0; c < ch; ++c) pad[(size_t)(x + r) * ch + c] = sp[c];
        }
        float* out = &tmp[(size_t)y * rowN];
        for (int i = 0; i < rowN; ++i) out[i] = 0;
        for (int t = 0; t <= 2 * r; ++t) {
            const float kt = k[t]; const float* pp = &pad[(size_t)t * ch];
            for (int i = 0; i < rowN; ++i) out[i] += kt * pp[i];
        }
    });
    // по стовпцях: зважена сума цілих рядків (послідовна пам'ять, векторизується)
    parallelRows(h, [&](int y) {
        float* out = &buf[(size_t)y * rowN];
        for (int i = 0; i < rowN; ++i) out[i] = 0;
        for (int t = -r; t <= r; ++t) {
            const float kt = k[t + r]; const float* row = &tmp[(size_t)std::clamp(y + t, 0, h - 1) * rowN];
            for (int i = 0; i < rowN; ++i) out[i] += kt * row[i];
        }
    });
    return std::sqrt(sq);
}

inline float sampleSmall(const std::vector<float>& b, int sw, int sh, int ch, int c, float x, float y) {
    x = std::clamp(x, 0.0f, (float)sw - 1.001f); y = std::clamp(y, 0.0f, (float)sh - 1.001f);
    int x0 = (int)x, y0 = (int)y; float fx = x - x0, fy = y - y0;
    auto at = [&](int xx, int yy) { return b[((size_t)std::min(yy, sh - 1) * sw + std::min(xx, sw - 1)) * ch + c]; };
    float a = at(x0, y0) + (at(x0 + 1, y0) - at(x0, y0)) * fx;
    float d = at(x0, y0 + 1) + (at(x0 + 1, y0 + 1) - at(x0, y0 + 1)) * fx;
    return a + (d - a) * fy;
}

// білінійна вибірка всіх 3 каналів одразу
inline void sample3(const std::vector<float>& b, int sw, int sh, float x, float y, float* o) {
    x = std::clamp(x, 0.0f, (float)sw - 1.001f); y = std::clamp(y, 0.0f, (float)sh - 1.001f);
    int x0 = (int)x, y0 = (int)y, x1 = std::min(x0 + 1, sw - 1), y1 = std::min(y0 + 1, sh - 1);
    float fx = x - x0, fy = y - y0;
    const float *a = &b[((size_t)y0 * sw + x0) * 3], *bb = &b[((size_t)y0 * sw + x1) * 3];
    const float *c = &b[((size_t)y1 * sw + x0) * 3], *d = &b[((size_t)y1 * sw + x1) * 3];
    for (int k = 0; k < 3; ++k) {
        float t = a[k] + (bb[k] - a[k]) * fx, u = c[k] + (d[k] - c[k]) * fx;
        o[k] = t + (u - t) * fy;
    }
}

inline uint32_t hash3(uint32_t x, uint32_t y, uint32_t s) {
    uint32_t h = x * 0x8da6b343u ^ y * 0xd8163841u ^ s * 0xcb1ab31fu;
    h ^= h >> 16; h *= 0x7feb352du; h ^= h >> 15; h *= 0x846ca68bu; h ^= h >> 16;
    return h;
}
// гаусівське число з хешу (Box–Muller), детерміноване для (x, y, seed)
// ---- швидка математика для гарячих циклів (похибка ~1e-6 відносно std::log2 / std::exp2)
inline float fastLog2(float x) {
    x = std::max(x, 1e-30f);
    uint32_t i; std::memcpy(&i, &x, 4);
    float e = (float)((int)((i >> 23) & 255) - 127);
    i = (i & 0x007FFFFFu) | 0x3F800000u; float m; std::memcpy(&m, &i, 4);
    float t = m - 1.0f;
    float p = ((((((0.0145987508f * t - 0.0759216121f) * t + 0.188654064f) * t - 0.321484765f) * t + 0.47172247f) * t -
                0.720202841f) * t + 1.44263371f) * t + 8.1107724e-07f;
    return e + p;
}
inline float fastExp2(float x) {
    x = std::clamp(x, -126.0f, 126.0f);
    float fi = std::floor(x), f = x - fi;
    float p = (((((0.000218712623f * f + 0.00123824155f) * f + 0.00968618629f) * f + 0.0554789125f) * f +
                0.240231097f) * f + 0.693146838f) * f + 1.00000001f;
    uint32_t i = (uint32_t)((int)fi + 127) << 23; float sc; std::memcpy(&sc, &i, 4);
    return p * sc;
}
inline float fastLog10(float x) { return fastLog2(x) * 0.30102999566f; }
inline float fastPow10(float x) { return fastExp2(x * 3.32192809489f); }
inline float fastPow(float x, float e) { return x <= 0 ? 0.0f : fastExp2(fastLog2(x) * e); }
// дешеве ~гаусівське число: сума 4 байтів хешу (Ірвін–Голл), середнє 0, σ = 1
inline float gaussFast(int x, int y, uint32_t s) {
    uint32_t h = hash3((uint32_t)x, (uint32_t)y, s);
    float sum = (float)((h & 255) + ((h >> 8) & 255) + ((h >> 16) & 255) + (h >> 24));
    return (sum - 510.0f) * (1.0f / 147.80f);
}

inline float gauss01(int x, int y, uint32_t s) {
    uint32_t a = hash3((uint32_t)x, (uint32_t)y, s), b = hash3((uint32_t)x + 0x9e3779b9u, (uint32_t)y, s ^ 0x5bd1e995u);
    float u1 = ((a >> 8) + 0.5f) * (1.0f / 16777216.0f), u2 = (b >> 8) * (1.0f / 16777216.0f);
    return std::sqrt(-2.0f * std::log(u1)) * std::cos(6.2831853f * u2);
}

inline float vnoise(float x, float y, uint32_t s) {   // гладкий value-noise для засвіток
    float xi = std::floor(x), yi = std::floor(y), fx = x - xi, fy = y - yi;
    float ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy);
    auto H = [&](float a, float b) { return (hash3((uint32_t)(int32_t)a, (uint32_t)(int32_t)b, s) >> 8) * (1.0f / 16777216.0f); };
    float a = H(xi, yi), b = H(xi + 1, yi), c = H(xi, yi + 1), d = H(xi + 1, yi + 1);
    float ab = a + (b - a) * ux, cd = c + (d - c) * ux;
    return ab + (cd - ab) * uy;
}

inline double smoothstepD(double a, double b, double x) { double t = std::clamp((x - a) / (b - a), 0.0, 1.0); return t * t * (3 - 2 * t); }
// засвітка з одного краю (без множника Amount)
inline float leakAt(int pos, uint32_t rs, int x, int y, int w, int h, float t) {
    float u = pos == 0 ? (float)x / w : pos == 1 ? 1.0f - (float)x / w : pos == 2 ? (float)y / h : 1.0f - (float)y / h;
    float along = (pos <= 1 ? (float)y / h : (float)x / w);
    float n = vnoise(along * 3.0f + t, t * 0.7f + 5.0f, rs) * 0.7f + vnoise(along * 7.0f - t * 1.3f, t + 9.0f, rs + 1u) * 0.3f;
    float reach = 0.05f + 0.16f * n;
    return 1.6f * std::exp2(-1.442695f * u / reach) * (0.25f + 1.5f * n * n);
}

inline float softplus(float z) { return z > 20 ? z : (z < -20 ? 0.0f : std::log1p(std::exp(z))); }
// «рампа» від 0 до (sh − toe) з м'якою п'ятою і плечем; монотонна
inline float ramp(float x, float toe, float sh, float tw, float sw) {
    return tw * softplus((x - toe) / tw) - sw * softplus((x - sh) / sw);
}

static const float kLog2 = 0.30103f;       // 1 стоп у log10 експозиції
static const float kMidGray = 0.18f;
static const float kTargetY = 0.12f;       // дисплей-лінійна яскравість, куди калібрується 18% сірий

// ---------------- модель плівки
struct Film {
    StockDef s; int cls = CL_NEG; int nch = 3;
    float g[3], toe[3], sh[3], dmin[3], dmax = 0;
    float colorSep = 0, colorBoost = 0, gammaCorr = 0, fog = 0;
    float speedLoss[3] = {0, 0, 0};   // прострочена плівка: шари втрачають чутливість (синій — найбільше)
    float density(int c, float x) const {
        float r = ramp(x, toe[c], sh[c], s.toeW, s.shW);
        if (cls == CL_REV) return dmax - g[c] * r;
        return dmin[c] + g[c] * r;
    }
};
struct Print {
    PrintDef p; float span[3];
    float density(int c, float xp) const { return p.dmin[c] + p.gamma[c] * ramp(xp, 0.0f, span[c], p.toeW, p.shW); }
};

inline Film makeFilm(const StockDef& sd, const Params& P, bool creative) {
    Film f; f.s = sd; f.cls = sd.cls; f.nch = sd.cls == CL_BW ? 1 : 3;
    float pp = creative ? (float)P.pushPull : 0.0f;
    float cb = (creative && P.devOn) ? (float)P.contrastBoost / 100.0f : 0.0f;
    for (int c = 0; c < 3; ++c) {
        f.g[c] = sd.gamma[c] * (1.0f + 0.12f * pp) * (1.0f + 0.5f * cb);   // push/pull і контраст проявлення
        f.dmin[c] = sd.dmin[c] + 0.03f * std::max(pp, 0.0f);              // більше вуалі при пуші
        f.toe[c] = sd.toe; f.sh[c] = sd.shoulder;
        if (sd.cls == CL_REV) {   // діапазон оборотної плівки задають Dmax−Dmin і нахил
            float span = (sd.dmax - sd.dmin[c]) / f.g[c];
            f.sh[c] = f.toe[c] + span;
        }
    }
    f.dmax = sd.dmax;
    // Expired Film. Модель (оцінка, творча): старіння = вуаль (base+fog росте, синій шар найбільше),
    // втрата чутливості шарів і падіння контрасту; лабораторія таймує середній сірий, тож лишаються
    // кольорова вуаль у тінях, кросовери і «вицвілий» контраст. a ≈ роки/10 × швидкість зберігання.
    if (creative && P.age > 0) {
        float a = (float)P.age / 10.0f * kStorageRate[std::clamp(P.storage, 0, 2)];
        const float fogK[3] = {0.030f, 0.040f, 0.065f}, lossK[3] = {0.04f, 0.06f, 0.10f};
        for (int c = 0; c < 3; ++c) {
            f.dmin[c] += fogK[c] * a;
            if (sd.cls == CL_REV) f.dmin[c] += fogK[c] * a * 0.5f;
            f.g[c] *= std::max(0.55f, 1.0f - 0.07f * a);
            f.speedLoss[c] = lossK[c] * a;
        }
        if (sd.cls == CL_REV) for (int c = 0; c < 3; ++c) f.sh[c] = f.toe[c] + (sd.dmax - f.dmin[c]) / f.g[c];
    }
    f.colorSep = sd.colorSep * ((creative && P.devOn) ? (float)P.colorSep / 100.0f : 1.0f);
    f.colorBoost = (creative && P.devOn) ? (float)P.colorBoost / 100.0f : 0.0f;
    f.gammaCorr = (creative && P.devOn) ? (float)P.gammaCorr / 100.0f : 0.0f;
    return f;
}
inline Print makePrint(const PrintDef& pd) {
    Print p; p.p = pd;
    for (int c = 0; c < 3; ++c) p.span[c] = (pd.dmax - pd.dmin[c]) / pd.gamma[c];
    return p;
}

// x: log10 експозиції відносно 18% (уже з усіма зсувами) → щільність негативу/слайда (3 канали)
inline void develop(const Film& f, const float* xin, float* D, float pushShift) {
    float x[3];
    if (f.nch == 1) { x[0] = x[1] = x[2] = xin[0] - pushShift - f.speedLoss[1]; }
    else {
        float m = (xin[0] + xin[1] + xin[2]) / 3.0f;
        for (int c = 0; c < 3; ++c) x[c] = xin[c] + f.colorSep * (xin[c] - m) + f.s.balance[c] - pushShift - f.speedLoss[c];
    }
    for (int c = 0; c < f.nch; ++c) D[c] = f.density(c, x[c]);
    if (f.nch == 1) D[1] = D[2] = D[0];
    if (f.gammaCorr != 0) {   // середні тони: щільніше на негативі = світліше на відбитку
        float sgn = f.cls == CL_REV ? -1.0f : 1.0f;
        for (int c = 0; c < 3; ++c) D[c] += sgn * f.gammaCorr * 0.22f * std::exp(-x[c] * x[c] / (2 * 0.55f * 0.55f));
    }
    if (f.colorBoost != 0 && f.nch == 3) {
        float r[3], m = 0;
        for (int c = 0; c < 3; ++c) { r[c] = D[c] - f.dmin[c]; m += r[c] / 3.0f; }
        for (int c = 0; c < 3; ++c) D[c] = f.dmin[c] + m + (r[c] - m) * (1.0f + f.colorBoost);
    }
}

// обернення монотонної функції бісекцією
template <class F> float invert(F f, float target, float lo, float hi) {
    bool inc = f(hi) > f(lo);
    for (int i = 0; i < 60; ++i) {
        float m = 0.5f * (lo + hi);
        if ((f(m) < target) == inc) lo = m; else hi = m;
    }
    return 0.5f * (lo + hi);
}

// Повна «система» для одного пікселя від log-експозиції до дисплей-лінійного світла.
struct System {
    Film film; Print print; int mode = 0;   // 0 — друк, 1 — скан, 2 — слайд напряму
    float off[3] = {0, 0, 0};                // калібрування друку/скану: 18% сірий → kTargetY
    float Dmid[3] = {0, 0, 0};
    float pushShift = 0;
    float lightShift[3] = {0, 0, 0};          // творчі printer lights / print exposure (log10 E)
    float colorDensity = 0;
    float scanGamma[3] = {1, 1, 1};
    float cross = 0;   // крос-процес (творча модель): різні контрасти/зсуви шарів у щільності відбитка
    // Expand: чорне і біле системи (дуже темна / дуже яскрава сцена) → 0 і 1 дисплея
    float yb[3] = {0, 0, 0}, yw[3] = {1, 1, 1};
    bool expand = false; int expandMode = 0;
    void measureRange() {
        float xb[3] = {-5.0f, -5.0f, -5.0f}, xw[3] = {3.5f, 3.5f, 3.5f}, D[3];
        develop(film, xb, D, pushShift); displayRaw(D, yb);
        develop(film, xw, D, pushShift); displayRaw(D, yw);
        if (expandMode == 1) {
            float b = kLumW[0] * yb[0] + kLumW[1] * yb[1] + kLumW[2] * yb[2];
            float w = kLumW[0] * yw[0] + kLumW[1] * yw[1] + kLumW[2] * yw[2];
            for (int c = 0; c < 3; ++c) { yb[c] = b; yw[c] = w; }
        }
    }
    void applyExpand(float* Y) const {
        if (!expand) return;
        for (int c = 0; c < 3; ++c) Y[c] = (Y[c] - yb[c]) / std::max(yw[c] - yb[c], 1e-4f);
    }

    // щільність (вже з зерном) → дисплей-лінійне (+ Expand)
    void display(const float* D, float* Y) const { displayRaw(D, Y); applyExpand(Y); }
    void displayRaw(const float* D, float* Y) const {
        displayBase(D, Y);
        if (cross > 0) {
            // E-6 у C-41 / C-41 в E-6: блакитні тіні, жовто-зелені світлі, жорсткий контраст
            const float g[3] = {1.25f, 1.08f, 0.78f}, o[3] = {-0.05f, 0.02f, 0.12f};
            for (int c = 0; c < 3; ++c) {
                float d = -std::log10(std::max(Y[c], 1e-6f));
                float d2 = 0.92f + (d - 0.92f) * g[c] + o[c];
                d = d + (d2 - d) * cross;
                Y[c] = std::pow(10.0f, -d);
            }
        }
        if (film.nch == 1) Y[0] = Y[2] = Y[1];
    }
    void displayBase(const float* D, float* Y) const {
        if (mode == 2) {   // слайд: пропускання відносно Dmin
            for (int c = 0; c < 3; ++c) Y[c] = std::pow(10.0f, -(D[c] - film.dmin[c]) + off[c]);
            return;
        }
        if (mode == 1) {   // скан негативу: інверсія і м'яке плече
            for (int c = 0; c < 3; ++c) {
                float e = (D[c] - Dmid[c]) / scanGamma[c];
                float y = kTargetY * std::pow(10.0f, 0.85f * e + off[c]);
                Y[c] = y / std::cbrt(1.0f + y * y * y);
            }
            return;
        }
        float Dp[3];
        for (int c = 0; c < 3; ++c) Dp[c] = print.density(c, -D[c] + off[c] + lightShift[c]);
        if (colorDensity > 0) {   // субтрактивна щільність кольору: насичені кольори темніші
            float mx = std::max({Dp[0], Dp[1], Dp[2]}), mn = std::min({Dp[0], Dp[1], Dp[2]});
            for (int c = 0; c < 3; ++c) Dp[c] += colorDensity * 0.35f * (mx - mn);
        }
        for (int c = 0; c < 3; ++c) Y[c] = std::pow(10.0f, -(Dp[c] - print.p.dmin[c]));
        if (film.nch == 1) Y[0] = Y[2] = Y[1];   // ч/б: нейтральний відбиток
    }
    void calibrate() {
        float x0[3] = {0, 0, 0}, D[3];
        // калібрування без балансу плівки: її кольоровий характер лишається
        Film nf = film; for (auto& b : nf.s.balance) b = 0; nf.gammaCorr = 0; nf.colorBoost = 0;
        develop(nf, x0, D, pushShift);   // лабораторія таймує друк на нормальний сірий і після пушу
        for (int c = 0; c < 3; ++c) Dmid[c] = D[c];
        float ls[3] = {lightShift[0], lightShift[1], lightShift[2]}; float cd = colorDensity;
        lightShift[0] = lightShift[1] = lightShift[2] = 0; colorDensity = 0;
        for (int c = 0; c < 3; ++c) {
            if (mode == 0) {
                float t = std::log10(1.0f / kTargetY) + print.p.dmin[c];
                float xp = invert([&](float z) { return print.density(c, z); }, t, -6.0f, 8.0f);
                off[c] = xp + D[c];
            } else if (mode == 1) {
                off[c] = 0;
            } else {
                off[c] = std::log10(kTargetY) + (D[c] - film.dmin[c]);
            }
        }
        lightShift[0] = ls[0]; lightShift[1] = ls[1]; lightShift[2] = ls[2]; colorDensity = cd;
    }
};

inline System makeSystem(const StockDef& sd, const PrintDef& pd, int printMode, const Params& P, bool creative) {
    System s; s.film = makeFilm(sd, P, creative); s.print = makePrint(pd);
    s.mode = sd.cls == CL_REV ? 2 : printMode;
    s.pushShift = creative ? (float)P.pushPull * kLog2 : 0.0f;
    for (int c = 0; c < 3; ++c) s.scanGamma[c] = s.film.g[c];
    s.calibrate();
    if (creative) {
        // printer points: 1 пункт = 0.025 log E; плюс = більше світла цього кольору = темніше в ньому
        float pe = -(float)P.printExposure * 0.15f;
        s.lightShift[0] = pe + (float)P.lightR * 0.025f;
        s.lightShift[1] = pe + (float)P.lightG * 0.025f;
        s.lightShift[2] = pe + (float)P.lightB * 0.025f;
        if (s.mode != 0) for (int c = 0; c < 3; ++c) s.off[c] -= s.lightShift[c] * 2.0f;   // скан/слайд: експозиція скану
        s.colorDensity = P.compOn ? (float)P.colorDensity / 100.0f : 0.0f;
        s.cross = (float)P.cross / 100.0f;
    }
    s.expand = creative ? P.expandOn : true;
    s.expandMode = creative ? P.colorMode : 0;
    if (creative && (P.age > 0 || P.cross > 0)) {
        // Expand розтягує рідний діапазон плівки; старіння і крос-процес лишаються видимими
        Params Q = P; Q.age = 0; Q.cross = 0;
        System b = makeSystem(sd, pd, printMode, Q, true);
        for (int c = 0; c < 3; ++c) { s.yb[c] = b.yb[c]; s.yw[c] = b.yw[c]; }
    } else {
        s.measureRange();
    }
    return s;
}

// log-експозиція: творчі криві до проявлення (blacks / whites / компресія)
inline float shapeX(float x, const Params& P) {
    if (P.blacks != 0) x += 0.5f * (float)P.blacks / (1.0f + std::exp((x + 0.7f) / 0.22f));
    if (P.whites != 0) x += 0.5f * (float)P.whites / (1.0f + std::exp(-(x - 0.5f) / 0.30f));
    if (P.compOn && P.impact > 0) {
        float knee = -0.3f + 2.4f * (float)P.compWhite / 100.0f, range = 0.15f + 1.5f * (float)P.tonalRange / 100.0f;
        float imp = (float)P.impact / 100.0f * 2.0f;
        if (x > knee) { float d = x - knee; x = knee + d / (1.0f + imp * d / range); }
    }
    return x;
}

// Обернений нейтральний конвеєр для дисплейних входів: дисплей-лінійне → log-експозиція сцени.
struct InverseNeutral {
    Lut inv[3];   // індекс: log10(Y)
    void build() {
        Params P0;
        System s = makeSystem(kReferenceStock, kReferencePrint, 0, P0, false);
        const int N = 4096; const float xa = -4.0f, xb = 3.0f;
        for (int c = 0; c < 3; ++c) {
            std::vector<float> xs(N + 1), ys(N + 1);
            for (int i = 0; i <= N; ++i) {
                float x = xa + (xb - xa) * i / N, xx[3] = {x, x, x}, D[3], Y[3];
                develop(s.film, xx, D, 0);
                s.display(D, Y);
                xs[i] = x; ys[i] = std::log10(std::max(Y[c], 1e-9f));
            }
            inv[c].build(-5.0f, 0.0f, 4096, [&](float ly) {
                if (ly <= ys[0]) return xs[0];
                if (ly >= ys[N]) return xs[N];
                int i = (int)(std::upper_bound(ys.begin(), ys.end(), ly) - ys.begin());
                i = std::clamp(i, 1, N);
                float t = (ly - ys[i - 1]) / std::max(ys[i] - ys[i - 1], 1e-9f);
                return xs[i - 1] + (xs[i] - xs[i - 1]) * t;
            });
        }
    }
};
inline const InverseNeutral& inverseNeutral() {
    static InverseNeutral n = [] { InverseNeutral a; a.build(); return a; }();
    return n;
}

inline const StockDef& stockFor(const Params& P) {
    return P.filmOn ? kStocks[std::clamp(P.stock, 0, kNumStocks - 1)] : kReferenceStock;
}
inline const char* statusText(const Params& P) {
    if (!P.filmOn) return "Film off - neutral reference";
    return kStocks[std::clamp(P.stock, 0, kNumStocks - 1)].status;
}

// ---------------- halation: фізична модель відбиття від основи плівки
// Світло, що пройшло емульсію, розсіюється в основу (розподіл (m+1)·cos^m θ·sinθ dθ, див. нижче), відбивається від її задньої
// поверхні (Френель для неполяризованого світла; повне внутрішнє відбиття після θc = arcsin(1/n)) і
// повертається в червоний шар на відстані r = 2·t·tanθ. Повторні проходи (light piping) — на 2r, 3r…
// Дані: триацетатна основа n ≈ 1.48 (Kodak M-63 через NRAO VLA memo), товщина ≈ 5.5 mil ≈ 0.14 мм.
// ОЦІНКИ: залишкове відбиття з remjet (0.05), пропускання емульсії для червоного (0.30), втрати між
// проходами (0.35), форма розсіювання (m = 3), ваги шарів R:G:B = 1 : 0.28 : 0 (червоний шар лежить на основі, синій поглинає жовтий фільтр).
static const float kBaseThicknessMM = 0.14f, kBaseIndex = 1.48f;
static const float kRemjetReflect = 0.05f, kEmulsionT = 0.45f, kPassLoss = 0.35f;

struct HalKernel { float s[6]; float a[6]; float total; };   // σ у товщинах основи t, a — частка енергії
inline float fresnelR(float th, float n) {
    float st = n * std::sin(th);
    if (st >= 1.0f) return 1.0f;
    float ci = std::cos(th), ct = std::sqrt(1.0f - st * st);
    float rs = (n * ci - ct) / (n * ci + ct), rp = (ci - n * ct) / (ci + n * ct);
    return 0.5f * (rs * rs + rp * rp);
}
inline HalKernel computeHalKernel(bool remjet) {
    const int NB = 480; const float dr = 0.05f;          // радіус у одиницях t, до 24t
    std::vector<double> e(NB, 0.0);
    const int NT = 40000;
    for (int i = 0; i < NT; ++i) {
        float th = (i + 0.5f) / NT * 1.5533f, dth = 1.5533f / NT;   // до 89°
        float R = remjet ? kRemjetReflect : fresnelR(th, kBaseIndex);
        // розсіювання з емульсії вперед-витягнуте: (m+1)·cos^m θ·sinθ, m = 3 (m = 1 — Ламберт).
        // m підібрано так, щоб кільце мало пік ~0.7% ширини 135-кадру і згасало до ~1–1.5%,
        // як у виміряних профілях CineStill 800T/400D (farewell-ladmin/halation.py). ОЦІНКА.
        float c = std::cos(th);
        float lamb = 4.0f * c * c * c * std::sin(th) * dth;
        float carry = R;
        for (int k = 1; k <= 2; ++k) {
            float r = 2.0f * k * std::tan(th);
            int b = (int)(r / dr);
            if (b < NB) e[b] += lamb * carry;
            carry *= kPassLoss * R;
        }
    }
    HalKernel K; const float sb[6] = {0.4f, 0.8f, 1.6f, 3.2f, 6.4f, 12.8f};
    // невід'ємна апроксимація радіального розподілу енергії сумою 2D-гаусіан (розподіл Релея)
    std::vector<std::vector<double>> B(6, std::vector<double>(NB));
    for (int j = 0; j < 6; ++j)
        for (int b = 0; b < NB; ++b) {
            double r0 = b * dr, r1 = r0 + dr, s2 = 2.0 * sb[j] * sb[j];
            B[j][b] = std::exp(-r0 * r0 / s2) - std::exp(-r1 * r1 / s2);
        }
    double a[6] = {0, 0, 0, 0, 0, 0};
    for (int it = 0; it < 3000; ++it)
        for (int j = 0; j < 6; ++j) {
            double num = 0, den = 0;
            for (int b = 0; b < NB; ++b) {
                double res = e[b];
                for (int k = 0; k < 6; ++k) if (k != j) res -= a[k] * B[k][b];
                num += res * B[j][b]; den += B[j][b] * B[j][b];
            }
            a[j] = std::max(0.0, num / std::max(den, 1e-30));
        }
    K.total = 0;
    for (int j = 0; j < 6; ++j) { K.s[j] = sb[j]; K.a[j] = (float)a[j]; K.total += (float)a[j]; }
    return K;
}
inline const HalKernel& halKernel(bool remjet) {
    static const HalKernel k0 = computeHalKernel(false), k1 = computeHalKernel(true);
    return remjet ? k1 : k0;
}

// розмиття великим σ через зменшену копію (піраміда): повертає буфер і крок ds
// м'яке обмеження джерела сяйва/bloom: кліпнуте небо з дисплейного відео інакше стає «сонцем» у 100+ разів
// яскравішим за сірий і заливає кадр. Асимптота: bloom 24, halation 64 (× рівень 1.0 у сцені).
inline float softSrc(float v, float K = 24.0f) { return v * K / (K + v); }

inline std::vector<float> blurPyr(const std::vector<float>& full, int w, int h, float sigmaPx, int dsMin, int& dsOut,
                                  int& sw, int& sh) {
    int ds = dsMin;
    while (ds < 64 && sigmaPx / (ds * 2) >= 2.5f) ds *= 2;
    sw = std::max(1, (w + ds - 1) / ds); sh = std::max(1, (h + ds - 1) / ds); dsOut = ds;
    std::vector<float> sm((size_t)sw * sh * 3, 0.0f);
    parallelRows(sh, [&](int sy) {
        for (int sx = 0; sx < sw; ++sx) {
            float b[3] = {0, 0, 0}; int n = 0;
            for (int j = 0; j < ds; ++j) for (int i = 0; i < ds; ++i) {
                int x = sx * ds + i, y = sy * ds + j;
                if (x >= w || y >= h) continue;
                for (int c = 0; c < 3; ++c) b[c] += softSrc(full[((size_t)y * w + x) * 3 + c]);
                ++n;
            }
            for (int c = 0; c < 3; ++c) sm[((size_t)sy * sw + sx) * 3 + c] = b[c] / std::max(n, 1);
        }
    });
    gaussBlur(sm, sw, sh, 3, sigmaPx / ds);
    return sm;
}

// Той самий develop + display, але через таблиці (у кілька разів швидше в гарячому циклі)
struct FastChain {
    const System& S; Lut dens[3], dispA[3], dispB[3], dispAB[3]; float base[3]; bool mono, merged;
    explicit FastChain(const System& s) : S(s) {
        const Film& f = s.film; mono = f.nch == 1;
        for (int c = 0; c < 3; ++c) {
            dens[c].build(-8.0f, 6.0f, 8192, [&](float x) {
                float d = f.density(mono ? 0 : c, x);
                if (f.gammaCorr != 0) d += (f.cls == CL_REV ? -1.0f : 1.0f) * f.gammaCorr * 0.22f * std::exp(-x * x / (2 * 0.55f * 0.55f));
                return d;
            });
            base[c] = s.mode == 0 ? s.print.p.dmin[c] : 0.0f;
            dispA[c].build(-1.0f, 7.0f, 8192, [&](float D) {
                if (s.mode == 0) return s.print.density(c, -D + s.off[c] + s.lightShift[c]);
                if (s.mode == 2) return (D - f.dmin[c]) - s.off[c];
                float e = (D - s.Dmid[c]) / s.scanGamma[c];
                float y = kTargetY * std::pow(10.0f, 0.85f * e + s.off[c]);
                return -std::log10(std::max(y / std::cbrt(1.0f + y * y * y), 1e-9f));
            });
            dispB[c].build(-3.0f, 9.0f, 8192, [&](float dp) {
                float Y = std::pow(10.0f, -(dp - base[c]));
                if (s.cross > 0) {
                    const float g[3] = {1.25f, 1.08f, 0.78f}, o[3] = {-0.05f, 0.02f, 0.12f};
                    float d = -std::log10(std::max(Y, 1e-6f));
                    float d2 = 0.92f + (d - 0.92f) * g[c] + o[c];
                    Y = std::pow(10.0f, -(d + (d2 - d) * s.cross));
                }
                if (s.expand) Y = (Y - s.yb[c]) / std::max(s.yw[c] - s.yb[c], 1e-4f);
                return Y;
            });
        }
        merged = !(s.mode == 0 && s.colorDensity > 0);
        if (merged)
            for (int c = 0; c < 3; ++c) dispAB[c].build(-1.0f, 7.0f, 16384, [&](float D) { return dispB[c](dispA[c](D)); });
    }
    void develop(const float* xin, float* D) const {
        const Film& f = S.film; float x[3];
        if (mono) { x[0] = xin[0] - S.pushShift - f.speedLoss[1]; D[0] = D[1] = D[2] = dens[0](x[0]); }
        else {
            float m = (xin[0] + xin[1] + xin[2]) * (1.0f / 3.0f);
            for (int c = 0; c < 3; ++c) D[c] = dens[c](xin[c] + f.colorSep * (xin[c] - m) + f.s.balance[c] - S.pushShift - f.speedLoss[c]);
        }
        if (f.colorBoost != 0 && !mono) {
            float r[3], mm = 0;
            for (int c = 0; c < 3; ++c) { r[c] = D[c] - f.dmin[c]; mm += r[c] / 3.0f; }
            for (int c = 0; c < 3; ++c) D[c] = f.dmin[c] + mm + (r[c] - mm) * (1.0f + f.colorBoost);
        }
    }
    void display(const float* D, float* Y) const {
        if (merged) {
            if (mono) { Y[0] = Y[1] = Y[2] = dispAB[1](D[1]); return; }
            for (int c = 0; c < 3; ++c) Y[c] = dispAB[c](D[c]);
            return;
        }
        float dp[3];
        for (int c = 0; c < 3; ++c) dp[c] = dispA[c](D[c]);
        if (S.mode == 0 && S.colorDensity > 0) {
            float mx = std::max({dp[0], dp[1], dp[2]}), mn = std::min({dp[0], dp[1], dp[2]});
            for (int c = 0; c < 3; ++c) dp[c] += S.colorDensity * 0.35f * (mx - mn);
        }
        if (mono) { Y[0] = Y[1] = Y[2] = dispB[1](dp[1]); return; }
        for (int c = 0; c < 3; ++c) Y[c] = dispB[c](dp[c]);
    }
};

// ---------------- рендер
// src/dst: RGBA float, рядки по rowFloats чисел. Розміри однакові.
inline void renderFull(const float* src, std::ptrdiff_t srcRowFloats, float* dst, std::ptrdiff_t dstRowFloats,
                       int w, int h, const Params& P);

// Швидкий перегляд: обробити кадр у половинній роздільності і збільшити. Фізичний масштаб (зерно,
// halation) не змінюється, бо він рахується від ширини кадру.
inline void render(const float* src, std::ptrdiff_t srcRowFloats, float* dst, std::ptrdiff_t dstRowFloats,
                   int w, int h, const Params& P) {
    if (!P.fastPreview || w < 640 || h < 360) { renderFull(src, srcRowFloats, dst, dstRowFloats, w, h, P); return; }
    const int hw = (w + 1) / 2, hh = (h + 1) / 2;
    std::vector<float> s2((size_t)hw * hh * 4), d2(s2.size());
    parallelRows(hh, [&](int y) {
        for (int x = 0; x < hw; ++x)
            for (int c = 0; c < 4; ++c) {
                float a = 0; int n = 0;
                for (int j = 0; j < 2; ++j) for (int i = 0; i < 2; ++i) {
                    int xx = std::min(2 * x + i, w - 1), yy = std::min(2 * y + j, h - 1);
                    float v = src[(std::ptrdiff_t)yy * srcRowFloats + xx * 4 + c];
                    if (std::isfinite(v)) { a += v; ++n; }
                }
                s2[((size_t)y * hw + x) * 4 + c] = n ? a / n : 0.0f;
            }
    });
    Params Q = P; Q.originX /= 2; Q.originY /= 2;
    renderFull(s2.data(), hw * 4, d2.data(), hw * 4, hw, hh, Q);
    parallelRows(h, [&](int y) {
        float fy = std::clamp((y + 0.5f) * 0.5f - 0.5f, 0.0f, hh - 1.0f);
        int y0 = (int)fy, y1 = std::min(y0 + 1, hh - 1); float ty = fy - y0;
        for (int x = 0; x < w; ++x) {
            float fxx = std::clamp((x + 0.5f) * 0.5f - 0.5f, 0.0f, hw - 1.0f);
            int x0 = (int)fxx, x1 = std::min(x0 + 1, hw - 1); float tx = fxx - x0;
            float* o = dst + (std::ptrdiff_t)y * dstRowFloats + x * 4;
            for (int c = 0; c < 3; ++c) {
                auto at = [&](int xx, int yy) { return d2[((size_t)yy * hw + xx) * 4 + c]; };
                float a = at(x0, y0) + (at(x1, y0) - at(x0, y0)) * tx, b = at(x0, y1) + (at(x1, y1) - at(x0, y1)) * tx;
                o[c] = a + (b - a) * ty;
            }
            o[3] = src[(std::ptrdiff_t)y * srcRowFloats + x * 4 + 3];
        }
    });
}

inline void renderFull(const float* src, std::ptrdiff_t srcRowFloats, float* dst, std::ptrdiff_t dstRowFloats,
                       int w, int h, const Params& P) {
    RenderScope scope;
    const StockDef& sd = stockFor(P);
    const bool scan = P.printOn && P.print >= kNumPrints;
    const PrintDef& pd = (!P.printOn || scan) ? kReferencePrint : kPrints[std::clamp(P.print, 0, kNumPrints - 1)];
    const System sys = makeSystem(sd, pd, scan ? 1 : 0, P, true);
    const Film& film = sys.film;
    const bool mono = film.nch == 1;
    const bool dispIn = displayReferred(P.input);
    const InverseNeutral* invN = dispIn ? &inverseNeutral() : nullptr;
    // дисплей-лінійне → сцена-лінійне одним LUT за √L (√ — апаратна, точність у тінях достатня)
    Lut invSq[3];
    if (dispIn)
        for (int c = 0; c < 3; ++c)
            invSq[c].build(0.0f, 1.2f, 16384, [&](float u) {
                return kMidGray * std::pow(10.0f, invN->inv[c](std::log10(std::max(u * u, 1e-9f))));
            });
    Params P0;
    const System refSys = makeSystem(kReferenceStock, kReferencePrint, 0, P0, false);
    const M3& Min = inMatrix(P.input);
    const M3& Mout = outMatrix(P.output);
    // формат плівки для зерна (Film Grain → Profile) і для halation (Halation → Profile)
    const int gp = std::clamp(P.grainProfile, 0, kNumGrainProfiles - 1);
    const float grainGaugeW = gp == 0 ? kGaugeWidthMM[2] : kGaugeWidthMM[(gp - 1) / 3];
    const float pixUM = grainGaugeW * 1000.0f / w;
    const int hp = std::clamp(P.halProfile, 0, kNumHalProfiles - 1);
    const float halGaugeW = hp == 0 ? kGaugeWidthMM[2] : kGaugeWidthMM[(hp - 1) / 2];
    const bool remjet = hp == 0 ? !(sd.halation > 1.0f) : ((hp - 1) % 2 == 0);
    const float halPxPerMM = w / halGaugeW;

    // мерехтіння: випадкова (детермінована для кадру) зміна експозиції, ±0.25 стопа при 1
    const uint32_t fseed = (uint32_t)(int64_t)std::floor(P.frame);
    const float flick = P.flicker > 0 ? (float)P.flicker * 0.5f * ((hash3(fseed, 77, 9) >> 8) / 16777216.0f - 0.5f) : 0.0f;
    const float ev = std::exp2((float)P.exposure + flick);
    // засвітка: колір від червоного до жовтого (світло крізь основу засвічує насамперед червоний шар)
    float leakCol[3];
    {
        float hcol = (float)P.leakHue / 100.0f;
        leakCol[0] = 1.0f; leakCol[1] = 0.10f + 0.75f * hcol; leakCol[2] = 0.02f + 0.25f * hcol * hcol;
    }
    // засвітка «дихає» безперервно; у режимі Random край і візерунок плавно перетікають у наступні
    // протягом останньої третини кожного ~5-секундного циклу (а не перемикаються стрибком)
    const double rollF = P.frame / 120.0;
    const uint32_t roll = (uint32_t)(int64_t)std::floor(rollF);
    const float rollS = (float)smoothstepD(0.65, 1.0, rollF - std::floor(rollF));
    int leakPos = std::clamp(P.leakPos, 0, 4), leakPos1 = leakPos;
    if (leakPos == 4) { leakPos = (int)(hash3(roll, 5, 11) % 4u); leakPos1 = (int)(hash3(roll + 1u, 5, 11) % 4u); }
    const float leakT = (float)P.frame * (float)P.leakSpeed * 0.03f;
    const float wb[3] = {std::exp2((float)P.temp * 0.30f), std::exp2(-(float)P.tint * 0.20f), std::exp2(-(float)P.temp * 0.30f)};
    const uint32_t seed = P.freezeGrain ? 1u : (uint32_t)(int64_t)std::floor(P.frame) * 2654435761u + 7u;
    const float sc = w / 1920.0f;
    const int dx = (int)std::lround(((hash3(seed, 1, 3) >> 8) / 16777216.0f - 0.5f) * 2.0f * P.weave * 3.0f * sc);
    const int dy = (int)std::lround(((hash3(seed, 2, 5) >> 8) / 16777216.0f - 0.5f) * 2.0f * P.weave * 2.0f * sc);

    // 1) вхід → сцена-лінійне (робочий простір), експозиція, баланс, вінетка
    Lut dec; dec.build(-0.1f, 1.1f, 8192, [&](float v) { return decodeTF(v, P.input); });
    // піксель (x, y) → сцена-лінійна експозиція o[3]
    auto stage1 = [&](int x, int y, float* o) {
        {
            int yy = std::clamp(y + dy, 0, h - 1);
            const float* row = src + (std::ptrdiff_t)yy * srcRowFloats;
            int xx = std::clamp(x + dx, 0, w - 1);
            float a[3], L[3];
            for (int c = 0; c < 3; ++c) {
                float v = row[xx * 4 + c];
                if (!std::isfinite(v)) v = 0;
                a[c] = (v >= -0.1f && v <= 1.1f) ? dec(v) : decodeTF(v, P.input);
            }
            mul(Min, a, L);
            if (dispIn)
                for (int c = 0; c < 3; ++c)
                    L[c] = invSq[c](std::sqrt(std::max(L[c], 0.0f)));
            float vig = 1.0f;
            if (P.vignette > 0) {
                float nx = (x - w * 0.5f) / (w * 0.5f), ny = (y - h * 0.5f) / (w * 0.5f);
                float r = std::sqrt(nx * nx + ny * ny) / 0.75f;
                float t = std::clamp((r - 0.45f) / 0.8f, 0.0f, 1.0f);
                vig = 1.0f - (float)P.vignette * 0.85f * t * t * (3 - 2 * t);
            }
            for (int c = 0; c < 3; ++c) o[c] = std::max(L[c], 0.0f) * ev * wb[c] * vig;
            if (P.leak > 0) {   // додаткова експозиція від краю кадру (до проявлення — тож вона і halation дає)
                float I = leakAt(leakPos, roll, x, y, w, h, leakT);
                if (rollS > 0) I = I * (1.0f - rollS) + leakAt(leakPos1, roll + 1u, x, y, w, h, leakT) * rollS;
                I *= (float)P.leak;
                for (int c = 0; c < 3; ++c) o[c] += I * leakCol[c];
            }
            if (mono) {   // панхроматичний шар: одне число
                float m = sd.mono[0] * o[0] + sd.mono[1] * o[1] + sd.mono[2] * o[2];
                o[0] = o[1] = o[2] = m;
            }
        }
    };
    // просторові ефекти (halation, bloom, MTF, маска) потребують кадру в пам'яті; без них — один прохід
    const float filmResPx = (100.0f - (float)P.filmRes) / 25.0f * 3.7f / pixUM;
    const bool needFrame = (P.halOn && P.halImpact > 0 && P.amplify > 0) || P.bloom > 0 ||
                           (P.grainOn && filmResPx >= 0.3f);
    std::vector<float> lin;
    if (needFrame) {
        lin.resize((size_t)w * h * 3);
        parallelRows(h, [&](int y) { for (int x = 0; x < w; ++x) stage1(x, y, &lin[((size_t)y * w + x) * 3]); });
    }

    // 1б) роздільна здатність плівки (MTF емульсії): гаусове розмиття ~3.7 мкм при 75
    //     (гаусова MTF з 50% на ~50 цикл/мм — оцінка порядку величини для 500T, не з тех. листа)
    {
        if (needFrame && P.grainOn && filmResPx >= 0.3f) gaussBlur(lin, w, h, 3, filmResPx);
    }

    // 2) halation: додаткова експозиція червоного (і трохи зеленого) шару світлом, відбитим від основи.
    //    Додається до експозиції (світло, яке інакше пішло б крізь основу) — до проявлення, без порогів
    //    у фізиці; Source Limiter / Background Gain — творчі маски, як у Dehancer.
    std::vector<float> halo;
    const bool halOn = P.halOn && P.halImpact > 0 && P.amplify > 0;
    if (halOn) {
        const HalKernel& K = halKernel(remjet);
        // Local Diffusion 15 → ефективна товщина 0.5·t: з нею пік кільця ~0.4–0.5% ширини кадру, як у
        // виміряних профілях CineStill (пік 0.2–0.6%, згасання ~1%). Геометричне 2t·tanθc дало б ~1%.
        const float tMM = kBaseThicknessMM * (0.25f + 1.67f * (float)P.localDiff / 100.0f);
        const float sSm = (float)P.smoothness / 100.0f * 0.10f;   // мм: розсіювання в емульсії
        const float T = P.srcLimiter <= 0 ? 0.0f : kMidGray * (std::exp2((float)P.srcLimiter / 10.0f) - 1.0f);
        // піраміда джерела: рівень 0 — крок ds0, далі кожен удвічі менший
        const int ds0 = std::max(1, std::min(4, w / 960));
        struct Lvl { int ds, w, h; std::vector<float> b; };
        std::vector<Lvl> pyr;
        {
            Lvl l0; l0.ds = ds0; l0.w = std::max(1, (w + ds0 - 1) / ds0); l0.h = std::max(1, (h + ds0 - 1) / ds0);
            l0.b.assign((size_t)l0.w * l0.h * 3, 0.0f);
            parallelRows(l0.h, [&](int sy) {
                for (int sx = 0; sx < l0.w; ++sx) {
                    float b[3] = {0, 0, 0}; int n = 0;
                    for (int j = 0; j < ds0; ++j) for (int i = 0; i < ds0; ++i) {
                        int x = sx * ds0 + i, y = sy * ds0 + j;
                        if (x >= w || y >= h) continue;
                        const float* L = &lin[((size_t)y * w + x) * 3];
                        float Y = kLumW[0] * L[0] + kLumW[1] * L[1] + kLumW[2] * L[2];
                        float g = T > 0 ? Y / (Y + T) : 1.0f;
                        for (int c = 0; c < 3; ++c) b[c] += softSrc(L[c], 64.0f) * g;   // halation: м'якше обмеження
                        ++n;
                    }
                    for (int c = 0; c < 3; ++c) l0.b[((size_t)sy * l0.w + sx) * 3 + c] = b[c] / std::max(n, 1);
                }
            });
            pyr.push_back(std::move(l0));
            while (pyr.back().w > 8 && pyr.back().h > 8 && pyr.back().ds < 64) {
                const Lvl& p = pyr.back();
                Lvl q; q.ds = p.ds * 2; q.w = (p.w + 1) / 2; q.h = (p.h + 1) / 2;
                q.b.assign((size_t)q.w * q.h * 3, 0.0f);
                for (int y = 0; y < q.h; ++y)
                    for (int x = 0; x < q.w; ++x)
                        for (int c = 0; c < 3; ++c) {
                            float a = 0; int n = 0;
                            for (int j = 0; j < 2; ++j) for (int i = 0; i < 2; ++i) {
                                int xx = 2 * x + i, yy = 2 * y + j;
                                if (xx < p.w && yy < p.h) { a += p.b[((size_t)yy * p.w + xx) * 3 + c]; ++n; }
                            }
                            q.b[((size_t)y * q.w + x) * 3 + c] = a / std::max(n, 1);
                        }
                pyr.push_back(std::move(q));
            }
        }
        const int aw = pyr[0].w, ah = pyr[0].h;
        std::vector<float> acc((size_t)aw * ah * 3, 0.0f);
        auto addComp = [&](float sigmaMM, float weight) {
            if (weight <= 0.02f * K.total) return;   // складові <2% енергії не варті розмиття
            float sPx = sigmaMM * halPxPerMM;
            size_t li = 0;
            while (li + 1 < pyr.size() && sPx / pyr[li + 1].ds >= 1.6f) ++li;
            const Lvl& L = pyr[li];
            std::vector<float> b = L.b;
            gaussBlur(b, L.w, L.h, 3, sPx / L.ds);
            const float k = (float)ds0 / L.ds;
            parallelRows(ah, [&](int ay) {
                for (int ax = 0; ax < aw; ++ax) {
                    float v[3];
                    sample3(b, L.w, L.h, (ax + 0.5f) * k - 0.5f, (ay + 0.5f) * k - 0.5f, v);
                    float* a = &acc[((size_t)ay * aw + ax) * 3];
                    a[0] += weight * v[0]; a[1] += weight * v[1]; a[2] += weight * v[2];
                }
            });
        };
        for (int j = 0; j < 6; ++j) addComp(std::sqrt(std::pow(K.s[j] * tMM, 2.0f) + sSm * sSm), K.a[j]);
        // Global Diffusion: широке вторинне розсіювання (вуаль), ~3% ширини кадру
        addComp(0.03f * halGaugeW, (float)P.globalDiff / 100.0f * 0.25f * K.total);
        const float strength = kEmulsionT * std::pow((float)P.amplify / 70.0f, 1.5f) * (float)P.halImpact / 100.0f;
        const float wc[3] = {mono ? 1.0f : 1.0f, mono ? 1.0f : 0.28f * (float)P.hue / 50.0f, mono ? 1.0f : 0.0f};
        const float bgTh = kMidGray * std::exp2((float)P.bgGain / 100.0f * 12.0f - 4.0f);
        if (P.maskMode) halo.assign((size_t)w * h * 3, 0.0f);
        parallelRows(h, [&](int y) {
            for (int x = 0; x < w; ++x) {
                float* L = &lin[((size_t)y * w + x) * 3];
                float Y = kLumW[0] * L[0] + kLumW[1] * L[1] + kLumW[2] * L[2];
                float gate = P.bgGain >= 100 ? 1.0f : 1.0f / (1.0f + (Y / bgTh) * (Y / bgTh));
                float blue = std::clamp((L[2] - std::max(L[0], L[1])) / (L[2] + 1e-6f), 0.0f, 1.0f);
                float f = strength * gate * (1.0f + (float)P.blueComp / 100.0f * 1.5f * blue);
                float av[3];
                sample3(acc, aw, ah, (x + 0.5f) / ds0 - 0.5f, (y + 0.5f) / ds0 - 0.5f, av);
                for (int c = 0; c < 3; ++c) {
                    float hv = f * wc[c] * av[mono ? 1 : c];
                    L[c] += hv;
                    if (!halo.empty()) halo[((size_t)y * w + x) * 3 + c] = hv;
                }
            }
        });
    }

    // 2б) bloom — розсіювання в об'єктиві (змішування з розмитою копією, енергія зберігається)
    if (P.bloom > 0) {
        int ds, sw, sh;
        auto b = blurPyr(lin, w, h, 0.035f * w, std::max(1, std::min(4, w / 960)), ds, sw, sh);
        const float a = std::min((float)P.bloom * 0.10f, 0.9f);
        parallelRows(h, [&](int y) {
            for (int x = 0; x < w; ++x) {
                float fx = (x + 0.5f) / ds - 0.5f, fy = (y + 0.5f) / ds - 0.5f;
                float* L = &lin[((size_t)y * w + x) * 3];
                for (int c = 0; c < 3; ++c) L[c] = std::max(L[c] + a * (sampleSmall(b, sw, sh, 3, c, fx, fy) - L[c]), 0.0f);
            }
        });
    }

    // 3) проявлення: log-експозиція → щільність (таблиці для швидкості)
    //    зерно — у щільності, з фізичним масштабом: σ на піксель із RMS-гранулярності на апертурі 48 мкм
    // Film Grain: σ на піксель із RMS-гранулярності σ48 за законом Селвина (σ·√A = const),
    // з ефективною апертурою √(піксель² + зерно²), щоб на дрібних пікселях не було «перезерна».
    const bool grainOn = P.grainOn && P.grainAmount > 0;
    float sigma48 = gp == 0 ? 0.0060f * sd.grain : kIsoSigma48[(gp - 1) % 3];
    const float sizeUM = gp == 0 ? (float)P.grainSize : kIsoGrainUM[(gp - 1) % 3] * (float)P.grainSize / 12.0f;
    sigma48 *= (float)P.grainAmount / 35.0f * (1.0f + 0.25f * std::max((float)P.pushPull, 0.0f)) *
               (1.0f + 0.03f * (float)P.age * kStorageRate[std::clamp(P.storage, 0, 2)]);
    const float sigmaPix = sigma48 * 48.0f / std::sqrt(pixUM * pixUM + sizeUM * sizeUM);
    const float grainBlur = 0.5f * sizeUM / pixUM;
    const float rho = mono ? 1.0f : 1.0f - 0.85f * (float)P.chroma / 100.0f;   // спільна частина між шарами
    const bool analogue = P.grainMode == 0;
    const float sRho = std::sqrt(rho), sRho1 = std::sqrt(1.0f - rho);
    const bool positive = P.filmType == 1 && film.cls != CL_REV;
    auto toneW = [&](float r) {   // r: 0 — тіні, 1 — середні, 2 — світлі (у термінах сцени)
        float a = (float)P.gShadows, b = (float)P.gMid, c = (float)P.gHigh;
        float v = r <= 1.0f ? a + (b - a) * std::clamp(r, 0.0f, 1.0f) : b + (c - b) * std::clamp(r - 1.0f, 0.0f, 1.0f);
        return v / 55.0f;
    };
    // Шум зерна на ґратці з кроком ≈ розмір зерна (а не повнокадрові буфери): значення у вузлах —
    // незалежні гаусівські, між вузлами — гладка інтерполяція (smoothstep), нормована до σ = 1.
    const int nf = grainOn ? (mono ? 1 : 4) : 0;
    struct Lattice { float sp = 1; int gw = 0, gh = 0, ox = 0, oy = 0; std::vector<float> v; };
    auto makeLattice = [&](float spacing, uint32_t sd0) {
        Lattice L; L.sp = std::max(1.0f, spacing);
        L.ox = (int)std::floor(P.originX / L.sp); L.oy = (int)std::floor(P.originY / L.sp);
        L.gw = (int)std::ceil(w / L.sp) + 2; L.gh = (int)std::ceil(h / L.sp) + 2;
        L.v.resize((size_t)L.gw * L.gh * nf);
        parallelRows(L.gh, [&](int gy) {
            for (int gx = 0; gx < L.gw; ++gx)
                for (int k = 0; k < nf; ++k)
                    L.v[((size_t)gy * L.gw + gx) * nf + k] = gaussFast(gx + L.ox, gy + L.oy, sd0 + (uint32_t)k);
        });
        return L;
    };
    Lattice lat1, lat2;
    const bool perPixel = grainBlur < 0.6f;   // зерно дрібніше за піксель — білий шум прямо в пікселі
    if (nf) {
        if (!perPixel) lat1 = makeLattice(2.0f * grainBlur, seed * 8u);
        if (analogue) lat2 = makeLattice(std::max(2.0f, 5.0f * grainBlur), seed * 8u + 4u);
    }
    // усі канали шуму одразу: ваги інтерполяції рахуються один раз на піксель
    auto latAll = [&](const Lattice& L, int x, int y, float* out) {
        float fx = (x + P.originX) / L.sp - L.ox, fy = (y + P.originY) / L.sp - L.oy;
        int x0 = std::clamp((int)fx, 0, L.gw - 2), y0 = std::clamp((int)fy, 0, L.gh - 2);
        float u = std::clamp(fx - x0, 0.0f, 1.0f), v = std::clamp(fy - y0, 0.0f, 1.0f);
        u = u * u * (3 - 2 * u); v = v * v * (3 - 2 * v);
        float w00 = (1 - u) * (1 - v) * 1.346f, w10 = u * (1 - v) * 1.346f, w01 = (1 - u) * v * 1.346f, w11 = u * v * 1.346f;
        const float* a = &L.v[((size_t)y0 * L.gw + x0) * nf];
        const float* b = a + nf;
        const float* c = a + (size_t)L.gw * nf;
        const float* d = c + nf;
        for (int k = 0; k < nf; ++k) out[k] = w00 * a[k] + w10 * b[k] + w01 * c[k] + w11 * d[k];
    };
    auto grainAll = [&](int x, int y, float* g) {   // g[nf]
        if (perPixel) {
            uint32_t base = seed * 8u;
            for (int k = 0; k < nf; ++k) g[k] = gaussFast(x + P.originX, y + P.originY, base + (uint32_t)k);
        } else {
            latAll(lat1, x, y, g);
        }
        if (analogue) {
            float g2[4];
            latAll(lat2, x, y, g2);
            for (int k = 0; k < nf; ++k) {
                float t = (g[k] + 0.35f * g2[k]) * (1.0f / 1.06f);
                g[k] = t + 0.12f * (t * t - 1.0f);   // асиметрія булевої моделі: рідкісні темні скупчення
            }
        }
    };

    // таблиці для пікселя: shapeX (blacks/whites/компресія), крива плівки, друк/скан, дисплей
    const bool shapeOn = P.blacks != 0 || P.whites != 0 || (P.compOn && P.impact > 0);
    Lut shapeLut;
    if (shapeOn) shapeLut.build(-8.0f, 6.0f, 8192, [&](float v) { return shapeX(v, P); });
    const FastChain fx(sys);
    Lut encLut; encLut.build(0.0f, 1.1f, 16384, [&](float u) { return encodeTF(u * u, P.output); });

    parallelRows(h, [&](int y) {
        const float* srow = src + (std::ptrdiff_t)y * srcRowFloats;
        float* drow = dst + (std::ptrdiff_t)y * dstRowFloats;
        for (int x = 0; x < w; ++x) {
            float Lb[3];
            const float* L = Lb;
            if (needFrame) L = &lin[((size_t)y * w + x) * 3]; else stage1(x, y, Lb);
            float xs[3], D[3], Y[3], o[3];
            for (int c = 0; c < 3; ++c) xs[c] = fastLog10(std::max(L[c], 1e-7f) * (1.0f / kMidGray));
            if (shapeOn) for (int c = 0; c < 3; ++c) xs[c] = shapeLut(xs[c]);
            fx.develop(xs, D);
            float gn[3] = {0, 0, 0};
            if (nf) {
                float g[4];
                grainAll(x, y, g);
                for (int c = 0; c < 3; ++c) gn[c] = mono ? g[0] : sRho * g[0] + sRho1 * g[1 + c];
            }
            if (nf && !positive) {   // зерно в щільності плівки (негатив або слайд)
                for (int c = 0; c < 3; ++c) {
                    float r = film.cls == CL_REV ? (film.dmax - D[c]) : (D[c] - film.dmin[c]);   // 0 — тіні сцени
                    float zone = film.cls == CL_REV ? r / 1.2f : r / 0.75f;
                    D[c] += gn[c] * sigmaPix * toneW(zone);
                }
            }
            fx.display(D, Y);
            if (nf && positive) {   // зерно у щільності позитиву (відбитка)
                for (int c = 0; c < 3; ++c) {
                    float dp = -fastLog10(std::max(Y[c], 1e-5f));
                    float zone = 2.0f - std::clamp(dp / 0.9f, 0.0f, 2.0f);   // темне = тіні
                    dp += gn[c] * sigmaPix * 2.0f * toneW(zone);
                    Y[c] = fastPow10(-dp);
                }
            }
            if (!halo.empty()) for (int c = 0; c < 3; ++c) { float hv = halo[((size_t)y * w + x) * 3 + c]; Y[c] = hv / (hv + 0.25f); }
            mul(Mout, Y, o);
            for (int c = 0; c < 3; ++c) o[c] = o[c] <= 0.0f ? 0.0f : o[c] <= 1.2f ? encLut(std::sqrt(o[c])) : encodeTF(o[c], P.output);
            if (P.mix < 100 && halo.empty()) {   // змішування з нейтральним відтворенням того ж пікселя
                float a[3], Ln[3], Yn[3], on[3];
                for (int c = 0; c < 3; ++c) { float v = srow[x * 4 + c]; a[c] = decodeTF(std::isfinite(v) ? v : 0.0f, P.input); }
                mul(Min, a, Ln);
                if (dispIn) { for (int c = 0; c < 3; ++c) Yn[c] = std::max(Ln[c], 0.0f); }
                else {
                    float xr[3], Dr[3];
                    for (int c = 0; c < 3; ++c) xr[c] = std::log10(std::max(Ln[c], 1e-7f) / kMidGray);
                    develop(refSys.film, xr, Dr, 0); refSys.display(Dr, Yn);
                }
                mul(Mout, Yn, on);
                float m = std::clamp((float)P.mix / 100.0f, 0.0f, 1.0f);
                for (int c = 0; c < 3; ++c) o[c] = encodeTF(on[c], P.output) + (o[c] - encodeTF(on[c], P.output)) * m;
            }
            if (P.expandOn && (P.blackPoint != 0 || P.whitePoint != 100)) {
                float bp = (float)P.blackPoint / 100.0f, wp = (float)P.whitePoint / 100.0f;
                float sc2 = 1.0f / std::max(wp - bp, 0.05f);
                if (P.colorMode == 1) {
                    float Yl = 0.2126f * o[0] + 0.7152f * o[1] + 0.0722f * o[2];
                    float Yn = (Yl - bp) * sc2;
                    for (auto& c : o) c = Yl > 1e-5f ? c * Yn / Yl : Yn;
                } else {
                    for (auto& c : o) c = (c - bp) * sc2;
                }
            }
            for (int c = 0; c < 3; ++c) drow[x * 4 + c] = std::isfinite(o[c]) ? std::clamp(o[c], 0.0f, 1.0f) : 0.0f;
            drow[x * 4 + 3] = srow[x * 4 + 3];
        }
    });
}

}  // namespace svitfilm
