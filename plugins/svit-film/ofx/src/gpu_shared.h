// Svit Film — спільний код пікселя для Metal і для перевірки на процесорі.
// Цей файл компілюється і як Metal Shading Language (на Маку, під час роботи плагіна), і як C++
// (у тестах на Linux), тому тут лише прості типи: float, int, uint, масиви, жодних std:: і double.
#ifndef SVIT_GPU_SHARED_H
#define SVIT_GPU_SHARED_H

#ifdef __METAL_VERSION__
#include <metal_stdlib>
using namespace metal;
#define DEVC device const
#define DEVW device
#define CONSTP constant
#define THR thread
inline float f_exp2(float x) { return exp2(x); }
inline float f_log2(float x) { return log2(x); }
inline float f_log10(float x) { return log10(x); }
inline float f_pow(float x, float e) { return pow(x, e); }
inline float f_sqrt(float x) { return sqrt(x); }
inline float f_floor(float x) { return floor(x); }
inline float f_exp(float x) { return exp(x); }
inline bool f_finite(float x) { return isfinite(x); }
inline float f_ceil(float x) { return ceil(x); }
inline float f_sin(float x) { return sin(x); }
inline float f_cos(float x) { return cos(x); }
inline float f_abs(float x) { return fabs(x); }
#else
#include <cmath>
#include <cstdint>
typedef uint32_t uint;
#define DEVC const
#define DEVW
#define CONSTP const
#define THR
inline float f_exp2(float x) { return std::exp2(x); }
inline float f_log2(float x) { return std::log2(x); }
inline float f_log10(float x) { return std::log10(x); }
inline float f_pow(float x, float e) { return std::pow(x, e); }
inline float f_sqrt(float x) { return std::sqrt(x); }
inline float f_floor(float x) { return std::floor(x); }
inline float f_exp(float x) { return std::exp(x); }
inline bool f_finite(float x) { return std::isfinite(x); }
inline float f_ceil(float x) { return std::ceil(x); }
inline float f_sin(float x) { return std::sin(x); }
inline float f_cos(float x) { return std::cos(x); }
inline float f_abs(float x) { return std::fabs(x); }
#endif

inline float fmn(float a, float b) { return a < b ? a : b; }
inline float fmx(float a, float b) { return a > b ? a : b; }
inline float fcl(float x, float a, float b) { return x < a ? a : (x > b ? b : x); }
inline int imn(int a, int b) { return a < b ? a : b; }
inline int imx(int a, int b) { return a > b ? a : b; }
inline int icl(int x, int a, int b) { return x < a ? a : (x > b ? b : x); }

// таблиці (LUT) в одному буфері
enum {
    G_DEC = 0, G_INV0 = 1, G_SHAPE = 4, G_DENS0 = 5, G_DA0 = 8, G_DB0 = 11, G_DAB0 = 14, G_ENC = 17,
    G_RDENS0 = 18, G_RDAB0 = 21, G_NLUT = 24
};

struct KParams {
    int w, h, srcRow, dstRow, offX, offY, srcW, srcH;
    int input, output, dispIn, mono, needFrame, shapeOn, cls, sysMode;
    int merged, nf, perPixel, analogue, positive, maskOn, leakOn, leakPos;
    int expandUser, colorMode, mixOn, dx, dy, originX, originY, bgAll;
    uint roll, seed, pad0, pad1;
    int leakPos1, pad3; float leakS, pad4;
    float Min[9], Mout[9];
    float ev, vignette, leakAmt, leakT;
    float wb[3], leakCol[3], monoW[3];
    float colorSep, pushShift, colorBoost, dmax, colorDensity;
    float balance[3], speedLoss[3], dmin[3];
    float sigmaPix, sRho, sRho1, toneS, toneM, toneH;
    float lat1sp, lat2sp; int lat1ox, lat1oy, lat2ox, lat2oy;
    float mix, bp, wp;
    // lens
    int lensOn, frameMode, pad5, pad6;
    float lcx, lcy, lRn, lRs, lK, lS, lCA, lBlur, lSwirl, lTilt, lVig, fHalfW, fHalfH, fRc, fSoft, lHalfH;
    // halation
    float bgTh, strength, blueComp, halT;
    float wc[3];
    int ds0, aw, ah, pad2;
    // bloom
    float bloomA; int bloomDs, bloomW, bloomH;
    // LUT
    float lutA[G_NLUT], lutInv[G_NLUT];
    int lutN[G_NLUT], lutOff[G_NLUT];
};

inline float lutAt(DEVC float* T, CONSTP KParams& k, int id, float x) {
    float a = k.lutA[id], inv = k.lutInv[id];
    int n = k.lutN[id];                       // кількість значень (= кроків + 1)
    float b = a + (float)(n - 1) / inv;
    float u = (fcl(x, a, b) - a) * inv;
    int i = imn((int)u, n - 2);
    DEVC float* t = T + k.lutOff[id];
    return t[i] + (t[i + 1] - t[i]) * (u - (float)i);
}

inline uint hash3(uint x, uint y, uint s) {
    uint h = x * 0x8da6b343u ^ y * 0xd8163841u ^ s * 0xcb1ab31fu;
    h ^= h >> 16; h *= 0x7feb352du; h ^= h >> 15; h *= 0x846ca68bu; h ^= h >> 16;
    return h;
}
inline float gaussFastG(int x, int y, uint s) {
    uint h = hash3((uint)x, (uint)y, s);
    float sum = (float)((h & 255u) + ((h >> 8) & 255u) + ((h >> 16) & 255u) + (h >> 24));
    return (sum - 510.0f) * (1.0f / 147.80f);
}
inline float vnoiseG(float x, float y, uint s) {
    float xi = f_floor(x), yi = f_floor(y), fx = x - xi, fy = y - yi;
    float ux = fx * fx * (3.0f - 2.0f * fx), uy = fy * fy * (3.0f - 2.0f * fy);
    uint ix = (uint)(int)xi, iy = (uint)(int)yi;
    float a = (float)(hash3(ix, iy, s) >> 8) * (1.0f / 16777216.0f);
    float b = (float)(hash3(ix + 1u, iy, s) >> 8) * (1.0f / 16777216.0f);
    float c = (float)(hash3(ix, iy + 1u, s) >> 8) * (1.0f / 16777216.0f);
    float d = (float)(hash3(ix + 1u, iy + 1u, s) >> 8) * (1.0f / 16777216.0f);
    float ab = a + (b - a) * ux, cd = c + (d - c) * ux;
    return ab + (cd - ab) * uy;
}

inline float leakAtG(int pos, uint rs, int x, int y, int w, int h, float t) {
    float u = pos == 0 ? (float)x / w : pos == 1 ? 1.0f - (float)x / w : pos == 2 ? (float)y / h : 1.0f - (float)y / h;
    float along = (pos <= 1 ? (float)y / h : (float)x / w);
    float n = vnoiseG(along * 3.0f + t, t * 0.7f + 5.0f, rs) * 0.7f + vnoiseG(along * 7.0f - t * 1.3f, t + 9.0f, rs + 1u) * 0.3f;
    float reach = 0.05f + 0.16f * n;
    return 1.6f * f_exp2(-1.442695f * u / reach) * (0.25f + 1.5f * n * n);
}

inline float spowG(float v, float g) { return v > 0.0f ? f_pow(v, g) : 0.0f; }
inline float decodeTFG(float v, int mode) {
    if (mode == 2) return spowG(v, 2.0f);                                   // Apple Gamma 2.0
    if (mode == 3) {                                                        // ACEScct
        if (v <= 0.155251141552511f) return (v - 0.0729055341958355f) / 10.5402377416545f;
        return f_exp2(fmn(v, 1.468f) * 17.52f - 9.72f);
    }
    if (mode == 5) return v <= 0.02740668f ? v / 10.44426855f : f_exp2(v / 0.07329248f - 7.0f) - 0.0075f;   // DI
    if (mode == 6) {                                                        // Cineon
        float off = f_pow(10.0f, (95.0f - 685.0f) * 0.002f / 0.6f);
        return (f_pow(10.0f, (v * 1023.0f - 685.0f) * 0.002f / 0.6f) - off) / (1.0f - off);
    }
    if (mode == 7) {                                                        // S-Log3
        float x = v * 1023.0f;
        return x >= 171.2102946929f ? f_pow(10.0f, (x - 420.0f) / 261.5f) * 0.19f - 0.01f
                                    : (x - 95.0f) * 0.01125f / (171.2102946929f - 95.0f);
    }
    if (mode == 8)                                                          // LogC3
        return v > 5.367655f * 0.010591f + 0.092809f ? (f_pow(10.0f, (v - 0.385537f) / 0.247190f) - 0.052272f) / 5.555556f
                                                    : (v - 0.092809f) / 5.367655f;
    if (mode == 9) {   // HLG
        float e = v <= 0.5f ? v * v / 3.0f : (f_exp((v - 0.55991073f) / 0.17883277f) + 0.28466892f) / 12.0f;
        return e / 0.2647f;
    }
    if (mode == 10 || mode == 11) {   // Apple Log / Apple Log 2
        float Pt = 47.28711236f * (0.01f + 0.05641088f) * (0.01f + 0.05641088f);
        if (v >= Pt) return f_exp2((v - 0.69336945f) / 0.08550479f) - 0.00964052f;
        if (v >= 0.0f) return f_sqrt(v / 47.28711236f) - 0.05641088f;
        return -0.05641088f;
    }
    if (mode == 12) {   // S-Log2
        float y = (v * 1023.0f - 64.0f) / 876.0f;
        float x = y >= 0.030001222851889303f ? f_pow(10.0f, (y - 0.646596f) / 0.432699f) - 0.037584f
                                             : (y - 0.030001222851889303f) / 5.0f;
        return x * 0.9f * 219.0f / 155.0f;
    }
    if (mode == 13) {   // S-Log3 / S-Gamut3
        float x = v * 1023.0f;
        return x >= 171.2102946929f ? f_pow(10.0f, (x - 420.0f) / 261.5f) * 0.19f - 0.01f
                                    : (x - 95.0f) * 0.01125f / (171.2102946929f - 95.0f);
    }
    if (mode == 14) {   // LogC4
        float a = (262144.0f - 16.0f) / 117.45f, b = (1023.0f - 95.0f) / 1023.0f, c = 95.0f / 1023.0f;
        float s = (7.0f * 0.69314718f * f_exp2(7.0f - 14.0f * c / b)) / (a * b);
        float t = (f_exp2(14.0f * (-c / b) + 6.0f) - 64.0f) / a;
        return v >= 0.0f ? (f_exp2(14.0f * (v - c) / b + 6.0f) - 64.0f) / a : v * s + t;
    }
    if (mode == 15) return v < 0.181f ? (v - 0.125f) / 5.6f : f_pow(10.0f, (v - 0.598206f) / 0.241514f) - 0.00873f;
    if (mode == 16) return v >= 0.100537775223865f ? (f_pow(10.0f, (v - 0.790453f) / 0.344676f) - 0.009468f) / 0.555556f
                                                   : (v - 0.092864f) / 8.735631f;
    if (mode == 17) return v >= 0.100686685370811f ? (f_pow(10.0f, (v - 0.384316f) / 0.245281f) - 0.064829f) / 5.555556f
                                                   : (v - 0.092864f) / 8.799461f;
    if (mode == 18) return v <= 0.14f ? (v - 0.0929f) / 6.025f : (f_pow(10.0f, 3.89616f * v - 2.27752f) - 0.0108f) / 0.9892f;
    if (mode == 19) {
        float D = 8.283605932402494f, E = 0.09246575342465753f;
        return v < D * 0.005f + E ? (v - E) / D : f_exp((v - 0.5300133392291939f) / 0.08692876065491224f) - 0.005494072432257808f;
    }
    if (mode == 20) return v < 0.0f ? v / 15.1927f - 0.01f : (f_pow(10.0f, v / 0.224282f) - 1.0f) / 155.975327f - 0.01f;
    return spowG(v, 2.4f);
}
inline float encodeTFG(float v, int out) {
    v = fmx(v, 0.0f);
    if (out == 2) return f_pow(v, 1.0f / 2.6f);
    if (out == 3) return f_sqrt(v);
    if (out == 4) return v <= 0.0031308f ? v * 12.92f : 1.055f * f_pow(v, 1.0f / 2.4f) - 0.055f;
    return f_pow(v, 1.0f / 2.4f);
}
inline void mul9(CONSTP float* M, THR const float* a, THR float* o) {
    float x = a[0], y = a[1], z = a[2];
    o[0] = M[0] * x + M[1] * y + M[2] * z;
    o[1] = M[3] * x + M[4] * y + M[5] * z;
    o[2] = M[6] * x + M[7] * y + M[8] * z;
}
inline int srcIndex(CONSTP KParams& k, int x, int y) {   // піксель кадру результату → індекс у джерелі
    int sx = icl(x + k.offX, 0, k.srcW - 1), sy = icl(y + k.offY, 0, k.srcH - 1);
    return sy * k.srcRow + sx * 4;
}

// ---- Lens (як lensSample/lensMask у svitfilm_core.h)
inline float srcAtG(DEVC float* src, CONSTP KParams& k, int x, int y, int c) {
    float v = src[srcIndex(k, icl(x, 0, k.w - 1), icl(y, 0, k.h - 1)) + c];
    return f_finite(v) ? v : 0.0f;
}
inline float lensTapG(DEVC float* src, DEVC float* T, CONSTP KParams& k, float sx, float sy, int c) {
    sx -= 0.5f; sy -= 0.5f;
    float fx = f_floor(sx), fy = f_floor(sy);
    int x0 = (int)fx, y0 = (int)fy; float ux = sx - fx, uy = sy - fy;
    float a = srcAtG(src, k, x0, y0, c), b = srcAtG(src, k, x0 + 1, y0, c);
    float cc = srcAtG(src, k, x0, y0 + 1, c), d = srcAtG(src, k, x0 + 1, y0 + 1, c);
    float v0 = a + (b - a) * ux, v1 = cc + (d - cc) * ux;
    float v = v0 + (v1 - v0) * uy;
    return (v >= -0.1f && v <= 1.1f) ? lutAt(T, k, G_DEC, v) : decodeTFG(v, k.input);
}
inline void lensSampleG(DEVC float* src, DEVC float* T, CONSTP KParams& k, int x, int y, THR float* a) {
    float px = (float)x + 0.5f - k.lcx, py = (float)y + 0.5f - k.lcy;
    float nx = px / k.lRn, ny = py / k.lRn, r2 = nx * nx + ny * ny;
    float f = k.lS * (1.0f + k.lK * r2) * k.lRs / k.lRn;
    for (int c = 0; c < 3; ++c) {
        float fc = f * (c == 0 ? 1.0f + k.lCA : (c == 2 ? 1.0f - k.lCA : 1.0f));
        a[c] = lensTapG(src, T, k, k.lcx + px * fc + (float)k.dx, k.lcy + py * fc + (float)k.dy, c);
    }
}
inline float lensMaskG(CONSTP KParams& k, int x, int y) {
    float px = (float)x + 0.5f - k.lcx, py = (float)y + 0.5f - k.lcy, m = 1.0f;
    if (k.lVig > 0.0f) {
        float nx = px / k.lRn, ny = py / k.lRn, q = 1.0f / (1.0f + 1.4f * (nx * nx + ny * ny));
        m *= 1.0f - k.lVig * (1.0f - q * q);
    }
    if (k.frameMode > 0) {
        float dd;
        if (k.frameMode == 1) dd = f_sqrt(px * px + py * py) - k.fHalfH;
        else {
            float qx = f_abs(px) - (k.fHalfW - k.fRc), qy = f_abs(py) - (k.fHalfH - k.fRc);
            float mx = fmx(qx, 0.0f), my = fmx(qy, 0.0f);
            dd = f_sqrt(mx * mx + my * my) + fmn(fmx(qx, qy), 0.0f) - k.fRc;
        }
        float t = fcl((dd + k.fSoft) / k.fSoft, 0.0f, 1.0f);
        m *= 1.0f - t * t * (3.0f - 2.0f * t);
    }
    return m;
}

// вхід → сцена-лінійна експозиція (як stage1 у svitfilm_core.h)
inline void stage1G(DEVC float* src, DEVC float* T, CONSTP KParams& k, int x, int y, THR float* o) {
    float a[3], L[3];
    if (k.lensOn != 0) lensSampleG(src, T, k, x, y, a);
    else {
    int yy = icl(y + k.dy, 0, k.h - 1), xx = icl(x + k.dx, 0, k.w - 1);
    int si = srcIndex(k, xx, yy);
    for (int c = 0; c < 3; ++c) {
        float v = src[si + c];
        if (!f_finite(v)) v = 0.0f;
        a[c] = (v >= -0.1f && v <= 1.1f) ? lutAt(T, k, G_DEC, v) : decodeTFG(v, k.input);
    }
    }
    mul9(k.Min, a, L);
    if (k.dispIn != 0)
        for (int c = 0; c < 3; ++c) L[c] = lutAt(T, k, G_INV0 + c, f_sqrt(fmx(L[c], 0.0f)));
    float vig = 1.0f;
    if (k.vignette > 0.0f) {
        float nx = ((float)x - k.w * 0.5f) / (k.w * 0.5f), ny = ((float)y - k.h * 0.5f) / (k.w * 0.5f);
        float r = f_sqrt(nx * nx + ny * ny) / 0.75f;
        float t = fcl((r - 0.45f) / 0.8f, 0.0f, 1.0f);
        vig = 1.0f - k.vignette * 0.85f * t * t * (3.0f - 2.0f * t);
    }
    if (k.lensOn != 0) vig *= lensMaskG(k, x, y);
    for (int c = 0; c < 3; ++c) o[c] = fmx(L[c], 0.0f) * k.ev * k.wb[c] * vig;
    if (k.leakOn != 0) {
        float I = leakAtG(k.leakPos, k.roll, x, y, k.w, k.h, k.leakT);
        if (k.leakS > 0.0f) I = I * (1.0f - k.leakS) + leakAtG(k.leakPos1, k.roll + 1u, x, y, k.w, k.h, k.leakT) * k.leakS;
        I *= k.leakAmt;
        for (int c = 0; c < 3; ++c) o[c] += I * k.leakCol[c];
    }
    if (k.mono != 0) {
        float m = k.monoW[0] * o[0] + k.monoW[1] * o[1] + k.monoW[2] * o[2];
        o[0] = m; o[1] = m; o[2] = m;
    }
}

inline void gamutCompressG(THR float* o) {
    float ach = fmx(o[0], fmx(o[1], o[2]));
    if (ach <= 1e-6f) return;
    float t = 0.985f, l = 1.3f, p = 1.2f;
    float sc = (l - t) / f_pow(f_pow((1.0f - t) / (l - t), -p) - 1.0f, 1.0f / p);
    for (int c = 0; c < 3; ++c) {
        float d = (ach - o[c]) / ach;
        if (d <= t) continue;
        float x = (d - t) / sc;
        float cd = t + sc * x / f_pow(1.0f + f_pow(x, p), 1.0f / p);
        o[c] = ach - cd * ach;
    }
}
inline float toneWG(CONSTP KParams& k, float r) {
    float v = r <= 1.0f ? k.toneS + (k.toneM - k.toneS) * fcl(r, 0.0f, 1.0f)
                        : k.toneM + (k.toneH - k.toneM) * fcl(r - 1.0f, 0.0f, 1.0f);
    return v / 55.0f;
}
// шум зерна на ґратці: значення у вузлах — той самий хеш, що й на процесорі
inline void latAllG(CONSTP KParams& k, float sp, int ox, int oy, uint sd, int x, int y, THR float* res) {
    float fx = ((float)(x + k.originX)) / sp - (float)ox, fy = ((float)(y + k.originY)) / sp - (float)oy;
    int gw = (int)f_ceil((float)k.w / sp) + 2, gh = (int)f_ceil((float)k.h / sp) + 2;
    int x0 = icl((int)fx, 0, gw - 2), y0 = icl((int)fy, 0, gh - 2);
    float u = fcl(fx - (float)x0, 0.0f, 1.0f), v = fcl(fy - (float)y0, 0.0f, 1.0f);
    u = u * u * (3.0f - 2.0f * u); v = v * v * (3.0f - 2.0f * v);
    float w00 = (1.0f - u) * (1.0f - v) * 1.346f, w10 = u * (1.0f - v) * 1.346f;
    float w01 = (1.0f - u) * v * 1.346f, w11 = u * v * 1.346f;
    for (int q = 0; q < k.nf; ++q) {
        uint s = sd + (uint)q;
        res[q] = w00 * gaussFastG(x0 + ox, y0 + oy, s) + w10 * gaussFastG(x0 + 1 + ox, y0 + oy, s) +
                 w01 * gaussFastG(x0 + ox, y0 + 1 + oy, s) + w11 * gaussFastG(x0 + 1 + ox, y0 + 1 + oy, s);
    }
}

// експозиція L → вихідний піксель (як фінальний цикл renderFull)
inline void finalG(DEVC float* src, DEVC float* T, CONSTP KParams& k, int x, int y, THR const float* L,
                   THR const float* haloPx, THR float* res) {
    float xs[3], D[3], Y[3], o[3];
    for (int c = 0; c < 3; ++c) xs[c] = f_log10(fmx(L[c], 1e-7f) * (1.0f / 0.18f));
    if (k.shapeOn != 0) for (int c = 0; c < 3; ++c) xs[c] = lutAt(T, k, G_SHAPE, xs[c]);
    // проявлення
    if (k.mono != 0) {
        float d = lutAt(T, k, G_DENS0, xs[0] - k.pushShift - k.speedLoss[1]);
        D[0] = d; D[1] = d; D[2] = d;
    } else {
        float m = (xs[0] + xs[1] + xs[2]) * (1.0f / 3.0f);
        for (int c = 0; c < 3; ++c)
            D[c] = lutAt(T, k, G_DENS0 + c, xs[c] + k.colorSep * (xs[c] - m) + k.balance[c] - k.pushShift - k.speedLoss[c]);
        if (k.colorBoost != 0.0f) {
            float r[3], mm = 0.0f;
            for (int c = 0; c < 3; ++c) { r[c] = D[c] - k.dmin[c]; mm += r[c] / 3.0f; }
            float spread = fmx(r[0], fmx(r[1], r[2])) - fmn(r[0], fmn(r[1], r[2]));
            float kb = k.colorBoost > 0.0f ? 1.0f + k.colorBoost / (1.0f + spread * 2.0f) : 1.0f + k.colorBoost;
            for (int c = 0; c < 3; ++c) D[c] = k.dmin[c] + mm + (r[c] - mm) * kb;
        }
    }
    // зерно
    float gn[3] = {0.0f, 0.0f, 0.0f};
    if (k.nf > 0) {
        float g[4] = {0.0f, 0.0f, 0.0f, 0.0f};
        if (k.perPixel != 0) {
            for (int q = 0; q < k.nf; ++q) g[q] = gaussFastG(x + k.originX, y + k.originY, k.seed * 8u + (uint)q);
        } else {
            latAllG(k, k.lat1sp, k.lat1ox, k.lat1oy, k.seed * 8u, x, y, g);
        }
        if (k.analogue != 0) {
            float g2[4] = {0.0f, 0.0f, 0.0f, 0.0f};
            latAllG(k, k.lat2sp, k.lat2ox, k.lat2oy, k.seed * 8u + 4u, x, y, g2);
            for (int q = 0; q < k.nf; ++q) {
                float t = (g[q] + 0.35f * g2[q]) * (1.0f / 1.06f);
                g[q] = t + 0.12f * (t * t - 1.0f);
            }
        }
        for (int c = 0; c < 3; ++c) gn[c] = k.mono != 0 ? g[0] : k.sRho * g[0] + k.sRho1 * g[1 + c];
        if (k.positive == 0)
            for (int c = 0; c < 3; ++c) {
                float r = k.cls == 1 ? (k.dmax - D[c]) : (D[c] - k.dmin[c]);
                float zone = k.cls == 1 ? r / 1.2f : r / 0.75f;
                D[c] += gn[c] * k.sigmaPix * toneWG(k, zone);
            }
    }
    // друк / скан / слайд → дисплей
    if (k.merged != 0) {
        if (k.mono != 0) { float v = lutAt(T, k, G_DAB0 + 1, D[1]); Y[0] = v; Y[1] = v; Y[2] = v; }
        else for (int c = 0; c < 3; ++c) Y[c] = lutAt(T, k, G_DAB0 + c, D[c]);
    } else {
        float dp[3];
        for (int c = 0; c < 3; ++c) dp[c] = lutAt(T, k, G_DA0 + c, D[c]);
        if (k.sysMode == 0 && k.colorDensity > 0.0f) {
            float mx = fmx(dp[0], fmx(dp[1], dp[2])), mn = fmn(dp[0], fmn(dp[1], dp[2]));
            for (int c = 0; c < 3; ++c) dp[c] += k.colorDensity * 0.35f * (mx - mn);
        }
        if (k.mono != 0) { float v = lutAt(T, k, G_DB0 + 1, dp[1]); Y[0] = v; Y[1] = v; Y[2] = v; }
        else for (int c = 0; c < 3; ++c) Y[c] = lutAt(T, k, G_DB0 + c, dp[c]);
    }
    if (k.nf > 0 && k.positive != 0)
        for (int c = 0; c < 3; ++c) {
            float dpp = -f_log10(fmx(Y[c], 1e-5f));
            float zone = 2.0f - fcl(dpp / 0.9f, 0.0f, 2.0f);
            dpp += gn[c] * k.sigmaPix * 2.0f * toneWG(k, zone);
            Y[c] = f_pow(10.0f, -dpp);
        }
    if (k.maskOn != 0) for (int c = 0; c < 3; ++c) Y[c] = haloPx[c] / (haloPx[c] + 0.25f);
    mul9(k.Mout, Y, o);
    gamutCompressG(o);
    for (int c = 0; c < 3; ++c)
        o[c] = o[c] <= 0.0f ? 0.0f : (o[c] <= 1.2f ? lutAt(T, k, G_ENC, f_sqrt(o[c])) : encodeTFG(o[c], k.output));
    int si = srcIndex(k, x, y);
    if (k.mixOn != 0 && k.maskOn == 0) {
        float a[3], Ln[3], Yn[3], on[3];
        for (int c = 0; c < 3; ++c) { float v = src[si + c]; a[c] = decodeTFG(f_finite(v) ? v : 0.0f, k.input); }
        mul9(k.Min, a, Ln);
        if (k.dispIn != 0) { for (int c = 0; c < 3; ++c) Yn[c] = fmx(Ln[c], 0.0f); }
        else for (int c = 0; c < 3; ++c) {
            float xr = f_log10(fmx(Ln[c], 1e-7f) / 0.18f);
            Yn[c] = lutAt(T, k, G_RDAB0 + c, lutAt(T, k, G_RDENS0 + c, xr));
        }
        mul9(k.Mout, Yn, on);
        for (int c = 0; c < 3; ++c) { float e = encodeTFG(on[c], k.output); o[c] = e + (o[c] - e) * k.mix; }
    }
    if (k.expandUser != 0) {
        float sc2 = 1.0f / fmx(k.wp - k.bp, 0.05f);
        if (k.colorMode == 1) {
            float Yl = 0.2126f * o[0] + 0.7152f * o[1] + 0.0722f * o[2];
            float Yn = (Yl - k.bp) * sc2;
            for (int c = 0; c < 3; ++c) o[c] = Yl > 1e-5f ? o[c] * Yn / Yl : Yn;
        } else {
            for (int c = 0; c < 3; ++c) o[c] = (o[c] - k.bp) * sc2;
        }
    }
    for (int c = 0; c < 3; ++c) res[c] = f_finite(o[c]) ? fcl(o[c], 0.0f, 1.0f) : 0.0f;
    res[3] = src[si + 3];
}

// білінійна вибірка 3-канального буфера
inline void sample3G(DEVC float* b, int sw, int sh, float x, float y, THR float* o) {
    x = fcl(x, 0.0f, (float)sw - 1.001f); y = fcl(y, 0.0f, (float)sh - 1.001f);
    int x0 = (int)x, y0 = (int)y, x1 = imn(x0 + 1, sw - 1), y1 = imn(y0 + 1, sh - 1);
    float fx = x - (float)x0, fy = y - (float)y0;
    for (int q = 0; q < 3; ++q) {
        float a = b[(y0 * sw + x0) * 3 + q], bb = b[(y0 * sw + x1) * 3 + q];
        float c = b[(y1 * sw + x0) * 3 + q], d = b[(y1 * sw + x1) * 3 + q];
        float t = a + (bb - a) * fx, u = c + (d - c) * fx;
        o[q] = t + (u - t) * fy;
    }
}

// параметри допоміжних ядер
struct BlurP { int w, h, r, pad; };
struct DownP { int w, h, ds, ow, oh, clampSrc, pad0, pad1; float T, pad2, pad3, pad4; };
struct Down2P { int iw, ih, ow, oh; };
struct AccP { int bw, bh, aw, ah; float k, weight, pad0, pad1; };

inline void blurHG(DEVC float* inb, DEVW float* out, DEVC float* wts, CONSTP BlurP& p, int x, int y) {
    float a0 = 0.0f, a1 = 0.0f, a2 = 0.0f;
    for (int t = -p.r; t <= p.r; ++t) {
        int xx = icl(x + t, 0, p.w - 1);
        float wt = wts[t + p.r];
        int i = (y * p.w + xx) * 3;
        a0 += wt * inb[i]; a1 += wt * inb[i + 1]; a2 += wt * inb[i + 2];
    }
    int o = (y * p.w + x) * 3;
    out[o] = a0; out[o + 1] = a1; out[o + 2] = a2;
}
inline void blurVG(DEVC float* inb, DEVW float* out, DEVC float* wts, CONSTP BlurP& p, int x, int y) {
    float a0 = 0.0f, a1 = 0.0f, a2 = 0.0f;
    for (int t = -p.r; t <= p.r; ++t) {
        int yy = icl(y + t, 0, p.h - 1);
        float wt = wts[t + p.r];
        int i = (yy * p.w + x) * 3;
        a0 += wt * inb[i]; a1 += wt * inb[i + 1]; a2 += wt * inb[i + 2];
    }
    int o = (y * p.w + x) * 3;
    out[o] = a0; out[o + 1] = a1; out[o + 2] = a2;
}
inline void downG(DEVC float* lin, DEVW float* out, CONSTP DownP& p, int sx, int sy) {
    float b0 = 0.0f, b1 = 0.0f, b2 = 0.0f; int n = 0;
    for (int j = 0; j < p.ds; ++j) for (int i = 0; i < p.ds; ++i) {
        int x = sx * p.ds + i, y = sy * p.ds + j;
        if (x >= p.w || y >= p.h) continue;
        int q = (y * p.w + x) * 3;
        float L0 = lin[q], L1 = lin[q + 1], L2 = lin[q + 2];
        float g = 1.0f;
        if (p.T > 0.0f) { float Y = 0.26270021f * L0 + 0.67799807f * L1 + 0.05930172f * L2; g = Y * Y / (Y * Y + p.T * p.T); }
        if (p.clampSrc != 0) {
            float K = p.clampSrc == 1 ? 64.0f : 24.0f;   // 1 — halation, 2 — bloom
            L0 = L0 * K / (K + L0); L1 = L1 * K / (K + L1); L2 = L2 * K / (K + L2);
        }
        b0 += L0 * g; b1 += L1 * g; b2 += L2 * g; ++n;
    }
    float inv = 1.0f / (float)imx(n, 1);
    int o = (sy * p.ow + sx) * 3;
    out[o] = b0 * inv; out[o + 1] = b1 * inv; out[o + 2] = b2 * inv;
}
inline void down2G(DEVC float* inb, DEVW float* out, CONSTP Down2P& p, int x, int y) {
    for (int c = 0; c < 3; ++c) {
        float a = 0.0f; int n = 0;
        for (int j = 0; j < 2; ++j) for (int i = 0; i < 2; ++i) {
            int xx = 2 * x + i, yy = 2 * y + j;
            if (xx < p.iw && yy < p.ih) { a += inb[(yy * p.iw + xx) * 3 + c]; ++n; }
        }
        out[(y * p.ow + x) * 3 + c] = a / (float)imx(n, 1);
    }
}
inline void accumG(DEVC float* b, DEVW float* acc, CONSTP AccP& p, int ax, int ay) {
    float v[3];
    sample3G(b, p.bw, p.bh, ((float)ax + 0.5f) * p.k - 0.5f, ((float)ay + 0.5f) * p.k - 0.5f, v);
    int o = (ay * p.aw + ax) * 3;
    acc[o] += p.weight * v[0]; acc[o + 1] += p.weight * v[1]; acc[o + 2] += p.weight * v[2];
}
inline void halApplyG(DEVW float* lin, DEVC float* acc, DEVW float* halo, CONSTP KParams& k, int x, int y) {
    int q = (y * k.w + x) * 3;
    float L0 = lin[q], L1 = lin[q + 1], L2 = lin[q + 2];
    float Y = 0.26270021f * L0 + 0.67799807f * L1 + 0.05930172f * L2;
    float gate = k.bgAll != 0 ? 1.0f : 1.0f / (1.0f + (Y / k.bgTh) * (Y / k.bgTh));
    float blue = fcl((L2 - fmx(L0, L1)) / (L2 + 1e-6f), 0.0f, 1.0f);
    float f = k.strength * gate * (1.0f + k.blueComp * 1.5f * blue);
    float av[3];
    sample3G(acc, k.aw, k.ah, ((float)x + 0.5f) / (float)k.ds0 - 0.5f, ((float)y + 0.5f) / (float)k.ds0 - 0.5f, av);
    for (int c = 0; c < 3; ++c) {
        float hv = f * k.wc[c] * av[k.mono != 0 ? 1 : c];
        lin[q + c] += hv;
        if (k.maskOn != 0) halo[q + c] = hv;
    }
}
inline void bloomMixG(DEVW float* lin, DEVC float* b, CONSTP KParams& k, int x, int y) {
    float v[3];
    sample3G(b, k.bloomW, k.bloomH, ((float)x + 0.5f) / (float)k.bloomDs - 0.5f, ((float)y + 0.5f) / (float)k.bloomDs - 0.5f, v);
    int q = (y * k.w + x) * 3;
    for (int c = 0; c < 3; ++c) lin[q + c] = fmx(lin[q + c] + k.bloomA * (v[c] - lin[q + c]), 0.0f);
}

// ---- Lens: розмиття до країв / tilt-shift / swirl по кадру в лінійному світлі.
// Три заздалегідь розмиті копії (σ: 0.18, 0.45, 1.0 від максимуму) — кожен піксель плавно переходить між ними
// за своїм радіусом розмиття; swirl — вибірка вздовж дотичної (боке «закручується» навколо центру).
// Розмито в лінійному світлі сцени, тож яскраві точки розпливаються яскравими плямами, як у справжньому об'єктиві.
struct LensP {
    int w, h, d1, w1, h1, d2, w2, h2, d3, w3, h3, pad;
    float cx, cy, Rn, blur, tilt, swirl, halfH, s1, s2, s3, pad1, pad2;
};
inline void lensTapsG(DEVC float* b, int bw, int bh, int ds, float x, float y, float tx, float ty, float len, int n, THR float* o) {
    o[0] = 0.0f; o[1] = 0.0f; o[2] = 0.0f;
    for (int i = 0; i < n; ++i) {
        float off = n > 1 ? ((float)i / (float)(n - 1) * 2.0f - 1.0f) * len : 0.0f;
        float v[3];
        sample3G(b, bw, bh, (x + tx * off) / (float)ds - 0.5f, (y + ty * off) / (float)ds - 0.5f, v);
        o[0] += v[0]; o[1] += v[1]; o[2] += v[2];
    }
    o[0] /= (float)n; o[1] /= (float)n; o[2] /= (float)n;
}
inline void lensMixG(DEVW float* lin, DEVC float* b1, DEVC float* b2, DEVC float* b3, CONSTP LensP& p, int x, int y) {
    float px = (float)x + 0.5f - p.cx, py = (float)y + 0.5f - p.cy;
    float nx = px / p.Rn, ny = py / p.Rn, r = f_sqrt(nx * nx + ny * ny);
    float e = fcl((r - 0.2f) / 0.8f, 0.0f, 1.0f); e = e * e * (3.0f - 2.0f * e);
    float be = p.blur * e * e;
    float at = fcl((f_abs(py) / p.halfH - 0.12f) / 0.78f, 0.0f, 1.0f); at = at * at * (3.0f - 2.0f * at);
    float bt = p.tilt * at;
    float sg = f_sqrt(be * be + bt * bt);   // потрібна σ розмиття в пікселях
    if (sg < 0.25f) return;
    float sw = p.swirl * be / sg;
    float len = sw * sg * 2.5f;
    float pr = f_sqrt(px * px + py * py);
    float tx = 1.0f, ty = 0.0f; if (pr > 1e-3f) { tx = -py / pr; ty = px / pr; }
    int n = len > 0.75f ? 9 : 1;
    float fx = (float)x + 0.5f, fy = (float)y + 0.5f;
    int q = (y * p.w + x) * 3;
    float lo[3], hi[3], t;
    if (sg <= p.s1) {
        lo[0] = lin[q]; lo[1] = lin[q + 1]; lo[2] = lin[q + 2];
        lensTapsG(b1, p.w1, p.h1, p.d1, fx, fy, tx, ty, len, n, hi);
        t = sg / p.s1;
    } else if (sg <= p.s2) {
        lensTapsG(b1, p.w1, p.h1, p.d1, fx, fy, tx, ty, len, n, lo);
        lensTapsG(b2, p.w2, p.h2, p.d2, fx, fy, tx, ty, len, n, hi);
        t = (sg - p.s1) / (p.s2 - p.s1);
    } else {
        lensTapsG(b2, p.w2, p.h2, p.d2, fx, fy, tx, ty, len, n, lo);
        lensTapsG(b3, p.w3, p.h3, p.d3, fx, fy, tx, ty, len, n, hi);
        t = fcl((sg - p.s2) / (p.s3 - p.s2), 0.0f, 1.0f);
    }
    for (int c = 0; c < 3; ++c) lin[q + c] = fmx(lo[c] + (hi[c] - lo[c]) * t, 0.0f);
}

#endif
