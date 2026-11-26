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
#include <cmath>
#include <cstddef>
#include <cstdint>
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
    bool halOn = true; int halProfile = 0;
    double srcLimiter = 15, bgGain = 80, smoothness = 50, localDiff = 15, globalDiff = 25, amplify = 70, hue = 50,
           blueComp = 100, halImpact = 70;
    bool maskMode = false;
    // Bloom (розсіювання в об'єктиві)
    double bloom = 0;
    // Film Grain
    bool grainOn = true; int grainProfile = 0;
    double grainSize = 12, grainAmount = 35, filmRes = 75, gShadows = 30, gMid = 55, gHigh = 65, chroma = 65;
    int filmType = 0, grainMode = 0; bool freezeGrain = false;
    // Camera
    double vignette = 0, weave = 0;
    // Expand
    bool expandOn = true; double blackPoint = 0, whitePoint = 100; int colorMode = 0;
    // кадр і зсув зображення (щоб зерно не залежало від тайлів/обрізки)
    double frame = 0; int originX = 0, originY = 0;
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
inline float encodeTF(float v, int out) {
    v = std::max(v, 0.0f);
    switch (out) {
    case OUT_P3: return std::pow(v, 1.0f / 2.6f);
    case OUT_APPLE20: return std::pow(v, 0.5f);
    case OUT_SRGB: return v <= 0.0031308f ? v * 12.92f : 1.055f * std::pow(v, 1.0f / 2.4f) - 0.055f;
    default: return std::pow(v, 1.0f / 2.4f);
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

template <class F> void parallelRows(int h, F f) {
    int n = (int)std::max(1u, std::min(32u, std::thread::hardware_concurrency()));
    if (h < 64) n = 1;
    std::vector<std::thread> th;
    for (int t = 0; t < n; ++t) th.emplace_back([=, &f] { for (int y = t; y < h; y += n) f(y); });
    for (auto& x : th) x.join();
}

// розділюване гаусове розмиття; повертає sqrt(Σk²) для одного напрямку (для нормування шуму)
inline float gaussBlur(std::vector<float>& buf, int w, int h, int ch, float sigma) {
    if (sigma < 0.3f || w < 2 || h < 2) return 1.0f;
    int r = std::min(std::max(1, (int)std::ceil(sigma * 3.0f)), 768);
    std::vector<float> k(2 * r + 1);
    float sum = 0, sq = 0;
    for (int i = -r; i <= r; ++i) sum += (k[i + r] = std::exp(-0.5f * i * i / (sigma * sigma)));
    for (auto& v : k) { v /= sum; sq += v * v; }
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

inline uint32_t hash3(uint32_t x, uint32_t y, uint32_t s) {
    uint32_t h = x * 0x8da6b343u ^ y * 0xd8163841u ^ s * 0xcb1ab31fu;
    h ^= h >> 16; h *= 0x7feb352du; h ^= h >> 15; h *= 0x846ca68bu; h ^= h >> 16;
    return h;
}
// гаусівське число з хешу (Box–Muller), детерміноване для (x, y, seed)
inline float gauss01(int x, int y, uint32_t s) {
    uint32_t a = hash3((uint32_t)x, (uint32_t)y, s), b = hash3((uint32_t)x + 0x9e3779b9u, (uint32_t)y, s ^ 0x5bd1e995u);
    float u1 = ((a >> 8) + 0.5f) * (1.0f / 16777216.0f), u2 = (b >> 8) * (1.0f / 16777216.0f);
    return std::sqrt(-2.0f * std::log(u1)) * std::cos(6.2831853f * u2);
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
    if (f.nch == 1) { x[0] = x[1] = x[2] = xin[0] - pushShift; }
    else {
        float m = (xin[0] + xin[1] + xin[2]) / 3.0f;
        for (int c = 0; c < 3; ++c) x[c] = xin[c] + f.colorSep * (xin[c] - m) + f.s.balance[c] - pushShift;
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
    }
    s.expand = creative ? P.expandOn : true;
    s.expandMode = creative ? P.colorMode : 0;
    s.measureRange();
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
                for (int c = 0; c < 3; ++c) b[c] += full[((size_t)y * w + x) * 3 + c];
                ++n;
            }
            for (int c = 0; c < 3; ++c) sm[((size_t)sy * sw + sx) * 3 + c] = b[c] / std::max(n, 1);
        }
    });
    gaussBlur(sm, sw, sh, 3, sigmaPx / ds);
    return sm;
}

// ---------------- рендер
// src/dst: RGBA float, рядки по rowFloats чисел. Розміри однакові.
inline void render(const float* src, std::ptrdiff_t srcRowFloats, float* dst, std::ptrdiff_t dstRowFloats,
                   int w, int h, const Params& P) {
    const StockDef& sd = stockFor(P);
    const bool scan = P.printOn && P.print >= kNumPrints;
    const PrintDef& pd = (!P.printOn || scan) ? kReferencePrint : kPrints[std::clamp(P.print, 0, kNumPrints - 1)];
    const System sys = makeSystem(sd, pd, scan ? 1 : 0, P, true);
    const Film& film = sys.film;
    const bool mono = film.nch == 1;
    const bool dispIn = displayReferred(P.input);
    const InverseNeutral* invN = dispIn ? &inverseNeutral() : nullptr;
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

    const float ev = std::exp2((float)P.exposure);
    const float wb[3] = {std::exp2((float)P.temp * 0.30f), std::exp2(-(float)P.tint * 0.20f), std::exp2(-(float)P.temp * 0.30f)};
    const uint32_t seed = P.freezeGrain ? 1u : (uint32_t)(int64_t)std::floor(P.frame) * 2654435761u + 7u;
    const float sc = w / 1920.0f;
    const int dx = (int)std::lround(((hash3(seed, 1, 3) >> 8) / 16777216.0f - 0.5f) * 2.0f * P.weave * 3.0f * sc);
    const int dy = (int)std::lround(((hash3(seed, 2, 5) >> 8) / 16777216.0f - 0.5f) * 2.0f * P.weave * 2.0f * sc);

    // 1) вхід → сцена-лінійне (робочий простір), експозиція, баланс, вінетка
    Lut dec; dec.build(-0.1f, 1.1f, 8192, [&](float v) { return decodeTF(v, P.input); });
    std::vector<float> lin((size_t)w * h * 3);
    parallelRows(h, [&](int y) {
        int yy = std::clamp(y + dy, 0, h - 1);
        const float* row = src + (std::ptrdiff_t)yy * srcRowFloats;
        for (int x = 0; x < w; ++x) {
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
                    L[c] = kMidGray * std::pow(10.0f, invN->inv[c](std::log10(std::max(L[c], 1e-9f))));
            float vig = 1.0f;
            if (P.vignette > 0) {
                float nx = (x - w * 0.5f) / (w * 0.5f), ny = (y - h * 0.5f) / (w * 0.5f);
                float r = std::sqrt(nx * nx + ny * ny) / 0.75f;
                float t = std::clamp((r - 0.45f) / 0.8f, 0.0f, 1.0f);
                vig = 1.0f - (float)P.vignette * 0.85f * t * t * (3 - 2 * t);
            }
            float* o = &lin[((size_t)y * w + x) * 3];
            for (int c = 0; c < 3; ++c) o[c] = std::max(L[c], 0.0f) * ev * wb[c] * vig;
            if (mono) {   // панхроматичний шар: одне число
                float m = sd.mono[0] * o[0] + sd.mono[1] * o[1] + sd.mono[2] * o[2];
                o[0] = o[1] = o[2] = m;
            }
        }
    });

    // 1б) роздільна здатність плівки (MTF емульсії): гаусове розмиття ~3.7 мкм при 75
    //     (гаусова MTF з 50% на ~50 цикл/мм — оцінка порядку величини для 500T, не з тех. листа)
    {
        float sUM = (100.0f - (float)P.filmRes) / 25.0f * 3.7f;
        float sPx = sUM / pixUM;
        if (P.grainOn && sPx >= 0.3f) gaussBlur(lin, w, h, 3, sPx);
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
        std::vector<float> S((size_t)w * h * 3);
        parallelRows(h, [&](int y) {
            for (int x = 0; x < w; ++x) {
                const float* L = &lin[((size_t)y * w + x) * 3];
                float Y = kLumW[0] * L[0] + kLumW[1] * L[1] + kLumW[2] * L[2];
                float g = T > 0 ? Y / (Y + T) : 1.0f;
                for (int c = 0; c < 3; ++c) S[((size_t)y * w + x) * 3 + c] = std::min(L[c], 4000.0f) * g;
            }
        });
        const int ds0 = std::max(1, std::min(4, w / 960));
        const int aw = std::max(1, (w + ds0 - 1) / ds0), ah = std::max(1, (h + ds0 - 1) / ds0);
        std::vector<float> acc((size_t)aw * ah * 3, 0.0f);
        auto addComp = [&](float sigmaMM, float weight) {
            if (weight <= 0) return;
            int ds, sw, sh;
            auto b = blurPyr(S, w, h, sigmaMM * halPxPerMM, ds0, ds, sw, sh);
            parallelRows(ah, [&](int ay) {
                for (int ax = 0; ax < aw; ++ax) {
                    float fx = ((ax + 0.5f) * ds0) / ds - 0.5f, fy = ((ay + 0.5f) * ds0) / ds - 0.5f;
                    for (int c = 0; c < 3; ++c) acc[((size_t)ay * aw + ax) * 3 + c] += weight * sampleSmall(b, sw, sh, 3, c, fx, fy);
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
                float fx = (x + 0.5f) / ds0 - 0.5f, fy = (y + 0.5f) / ds0 - 0.5f;
                for (int c = 0; c < 3; ++c) {
                    float hv = f * wc[c] * sampleSmall(acc, aw, ah, 3, mono ? 1 : c, fx, fy);
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
    sigma48 *= (float)P.grainAmount / 35.0f * (1.0f + 0.25f * std::max((float)P.pushPull, 0.0f));
    const float sigmaPix = sigma48 * 48.0f / std::sqrt(pixUM * pixUM + sizeUM * sizeUM);
    const float grainBlur = 0.5f * sizeUM / pixUM;
    const float rho = mono ? 1.0f : 1.0f - 0.85f * (float)P.chroma / 100.0f;   // спільна частина між шарами
    const bool analogue = P.grainMode == 0;
    const bool positive = P.filmType == 1 && film.cls != CL_REV;
    auto toneW = [&](float r) {   // r: 0 — тіні, 1 — середні, 2 — світлі (у термінах сцени)
        float a = (float)P.gShadows, b = (float)P.gMid, c = (float)P.gHigh;
        float v = r <= 1.0f ? a + (b - a) * std::clamp(r, 0.0f, 1.0f) : b + (c - b) * std::clamp(r - 1.0f, 0.0f, 1.0f);
        return v / 55.0f;
    };
    std::vector<float> nz, nz2;
    float nzNorm = 1.0f, nz2Norm = 1.0f;
    const int nf = grainOn ? (mono ? 1 : 4) : 0;
    int w2 = (w + 1) / 2, h2 = (h + 1) / 2;
    if (nf) {
        nz.resize((size_t)w * h * nf);
        parallelRows(h, [&](int y) {
            for (int x = 0; x < w; ++x)
                for (int k = 0; k < nf; ++k)
                    nz[((size_t)y * w + x) * nf + k] = gauss01(x + P.originX, y + P.originY, seed * 8u + (uint32_t)k);
        });
        float q = gaussBlur(nz, w, h, nf, grainBlur);
        nzNorm = 1.0f / (q * q);   // std розмитого білого шуму = Σk² (2D)
        if (analogue) {   // скупчення зерен: друга октава в 2.5 раза більша (на половинній роздільності)
            nz2.resize((size_t)w2 * h2 * nf);
            parallelRows(h2, [&](int y) {
                for (int x = 0; x < w2; ++x)
                    for (int k = 0; k < nf; ++k)
                        nz2[((size_t)y * w2 + x) * nf + k] =
                            gauss01(x + P.originX / 2, y + P.originY / 2, seed * 8u + 4u + (uint32_t)k);
            });
            float q2 = gaussBlur(nz2, w2, h2, nf, grainBlur * 2.5f / 2.0f);
            nz2Norm = 1.0f / (q2 * q2);
        }
    }
    auto grainAt = [&](int x, int y, int k) {
        float g = nz[((size_t)y * w + x) * nf + k] * nzNorm;
        if (analogue) {
            int x2 = std::min(x / 2, w2 - 1), y2 = std::min(y / 2, h2 - 1);
            g = (g + 0.35f * nz2[((size_t)y2 * w2 + x2) * nf + k] * nz2Norm) / 1.06f;
            g += 0.12f * (g * g - 1.0f);   // асиметрія булевої моделі: рідкісні темні скупчення
        }
        return g;
    };

    parallelRows(h, [&](int y) {
        const float* srow = src + (std::ptrdiff_t)y * srcRowFloats;
        float* drow = dst + (std::ptrdiff_t)y * dstRowFloats;
        for (int x = 0; x < w; ++x) {
            const float* L = &lin[((size_t)y * w + x) * 3];
            float xs[3], D[3], Y[3], o[3];
            for (int c = 0; c < 3; ++c) xs[c] = shapeX(std::log10(std::max(L[c], 1e-7f) / kMidGray), P);
            develop(film, xs, D, sys.pushShift);
            float gn[3] = {0, 0, 0};
            if (nf) {
                float g0 = grainAt(x, y, 0);
                for (int c = 0; c < 3; ++c)
                    gn[c] = mono ? g0 : std::sqrt(rho) * g0 + std::sqrt(1.0f - rho) * grainAt(x, y, 1 + c);
            }
            if (nf && !positive) {   // зерно в щільності плівки (негатив або слайд)
                for (int c = 0; c < 3; ++c) {
                    float r = film.cls == CL_REV ? (film.dmax - D[c]) : (D[c] - film.dmin[c]);   // 0 — тіні сцени
                    float zone = film.cls == CL_REV ? r / 1.2f : r / 0.75f;
                    D[c] += gn[c] * sigmaPix * toneW(zone);
                }
            }
            sys.display(D, Y);
            if (nf && positive) {   // зерно у щільності позитиву (відбитка)
                for (int c = 0; c < 3; ++c) {
                    float dp = -std::log10(std::max(Y[c], 1e-5f));
                    float zone = 2.0f - std::clamp(dp / 0.9f, 0.0f, 2.0f);   // темне = тіні
                    dp += gn[c] * sigmaPix * 2.0f * toneW(zone);
                    Y[c] = std::pow(10.0f, -dp);
                }
            }
            if (!halo.empty()) for (int c = 0; c < 3; ++c) { float hv = halo[((size_t)y * w + x) * 3 + c]; Y[c] = hv / (hv + 0.25f); }
            mul(Mout, Y, o);
            for (int c = 0; c < 3; ++c) o[c] = encodeTF(o[c], P.output);
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
