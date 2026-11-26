// Svit Film — план кадру для відеокарти: усі параметри, таблиці й кроки розмиття, порахані на процесорі.
// Той самий план виконується або Metal-ядрами (metal_backend.h), або на процесорі (runPlanCPU, для тестів).
#pragma once
#include <cstring>
#include <vector>

#include "gpu_shared.h"
#include "svitfilm_core.h"

namespace svitfilm {

struct BlurStep { float sigmaPx = 0; float weight = 0; };
struct FramePlan {
    KParams k;
    std::vector<float> luts;
    float filmResPx = 0;                 // розмиття MTF (у пікселях кадру)
    bool halOn = false; float halT = 0; std::vector<BlurStep> halComps;
    bool bloomOn = false; float bloomSigma = 0; int bloomDsMin = 1;
};

inline void putLut(FramePlan& fp, int id, const Lut& L) {
    fp.k.lutA[id] = L.a; fp.k.lutInv[id] = L.inv; fp.k.lutN[id] = (int)L.t.size();
    fp.k.lutOff[id] = (int)fp.luts.size();
    fp.luts.insert(fp.luts.end(), L.t.begin(), L.t.end());
}
inline void putM(float* d, const M3& M) { for (int i = 0; i < 9; ++i) d[i] = M.m[i]; }

// Те саме, що на початку renderFull, але результат — план, а не пікселі.
inline FramePlan buildPlan(const Params& P, int w, int h) {
    FramePlan fp; KParams& k = fp.k;
    std::memset(&k, 0, sizeof k);
    k.w = w; k.h = h;
    const StockDef& sd = stockFor(P);
    const bool scan = P.printOn && P.print >= kNumPrints;
    const PrintDef& pd = (!P.printOn || scan) ? kReferencePrint : kPrints[std::clamp(P.print, 0, kNumPrints - 1)];
    const System sys = makeSystem(sd, pd, scan ? 1 : 0, P, true);
    const Film& film = sys.film;
    const bool mono = film.nch == 1;
    const bool dispIn = displayReferred(P.input);
    Params P0;
    const System refSys = makeSystem(kReferenceStock, kReferencePrint, 0, P0, false);
    k.input = P.input; k.output = P.output; k.dispIn = dispIn; k.mono = mono;
    putM(k.Min, inMatrix(P.input)); putM(k.Mout, outMatrix(P.output));

    const int gp = std::clamp(P.grainProfile, 0, kNumGrainProfiles - 1);
    const float grainGaugeW = gp == 0 ? kGaugeWidthMM[2] : kGaugeWidthMM[(gp - 1) / 3];
    const float pixUM = grainGaugeW * 1000.0f / w;
    const int hp = std::clamp(P.halProfile, 0, kNumHalProfiles - 1);
    const float halGaugeW = hp == 0 ? kGaugeWidthMM[2] : kGaugeWidthMM[(hp - 1) / 2];
    const bool remjet = hp == 0 ? !(sd.halation > 1.0f) : ((hp - 1) % 2 == 0);
    const float halPxPerMM = w / halGaugeW;

    const uint32_t fseed = (uint32_t)(int64_t)std::floor(P.frame);
    const float flick = P.flicker > 0 ? (float)P.flicker * 0.5f * ((hash3(fseed, 77, 9) >> 8) / 16777216.0f - 0.5f) : 0.0f;
    k.ev = std::exp2((float)P.exposure + flick);
    {
        float hcol = (float)P.leakHue / 100.0f;
        k.leakCol[0] = 1.0f; k.leakCol[1] = 0.10f + 0.75f * hcol; k.leakCol[2] = 0.02f + 0.25f * hcol * hcol;
    }
    int leakPos = std::clamp(P.leakPos, 0, 4);
    const uint32_t roll = (uint32_t)(int64_t)std::floor(P.frame / 48.0);
    if (leakPos == 4) leakPos = (int)(hash3(roll, 5, 11) % 4u);
    k.leakOn = P.leak > 0; k.leakPos = leakPos; k.leakAmt = (float)P.leak; k.roll = roll;
    k.leakT = (float)P.frame * (float)P.leakSpeed * 0.03f;
    k.wb[0] = std::exp2((float)P.temp * 0.30f); k.wb[1] = std::exp2(-(float)P.tint * 0.20f); k.wb[2] = std::exp2(-(float)P.temp * 0.30f);
    const uint32_t seed = P.freezeGrain ? 1u : (uint32_t)(int64_t)std::floor(P.frame) * 2654435761u + 7u;
    k.seed = seed;
    const float sc = w / 1920.0f;
    k.dx = (int)std::lround(((hash3(seed, 1, 3) >> 8) / 16777216.0f - 0.5f) * 2.0f * P.weave * 3.0f * sc);
    k.dy = (int)std::lround(((hash3(seed, 2, 5) >> 8) / 16777216.0f - 0.5f) * 2.0f * P.weave * 2.0f * sc);
    k.vignette = (float)P.vignette;
    for (int c = 0; c < 3; ++c) k.monoW[c] = sd.mono[c];

    // таблиці входу
    Lut dec; dec.build(-0.1f, 1.1f, 8192, [&](float v) { return decodeTF(v, P.input); });
    putLut(fp, G_DEC, dec);
    for (int c = 0; c < 3; ++c) {
        Lut inv;
        if (dispIn) {
            const InverseNeutral& invN = inverseNeutral();
            inv.build(0.0f, 1.2f, 16384, [&](float u) {
                return kMidGray * std::pow(10.0f, invN.inv[c](std::log10(std::max(u * u, 1e-9f))));
            });
        } else inv.build(0.0f, 1.0f, 2, [](float u) { return u; });
        putLut(fp, G_INV0 + c, inv);
    }

    // просторові кроки
    fp.filmResPx = (100.0f - (float)P.filmRes) / 25.0f * 3.7f / pixUM;
    const bool halOn = P.halOn && P.halImpact > 0 && P.amplify > 0;
    k.needFrame = halOn || P.bloom > 0 || (P.grainOn && fp.filmResPx >= 0.3f);
    if (!(P.grainOn && fp.filmResPx >= 0.3f)) fp.filmResPx = 0;
    fp.halOn = halOn;
    if (halOn) {
        const HalKernel& K = halKernel(remjet);
        const float tMM = kBaseThicknessMM * (0.25f + 1.67f * (float)P.localDiff / 100.0f);
        const float sSm = (float)P.smoothness / 100.0f * 0.10f;
        fp.halT = P.srcLimiter <= 0 ? 0.0f : kMidGray * (std::exp2((float)P.srcLimiter / 10.0f) - 1.0f);
        for (int j = 0; j < 6; ++j)
            if (K.a[j] > 0.02f * K.total)
                fp.halComps.push_back({std::sqrt(std::pow(K.s[j] * tMM, 2.0f) + sSm * sSm) * halPxPerMM, K.a[j]});
        float gw = (float)P.globalDiff / 100.0f * 0.25f * K.total;
        if (gw > 0.02f * K.total) fp.halComps.push_back({0.03f * halGaugeW * halPxPerMM, gw});
        k.strength = kEmulsionT * std::pow((float)P.amplify / 70.0f, 1.5f) * (float)P.halImpact / 100.0f;
        k.wc[0] = 1.0f; k.wc[1] = mono ? 1.0f : 0.28f * (float)P.hue / 50.0f; k.wc[2] = mono ? 1.0f : 0.0f;
        k.bgTh = kMidGray * std::exp2((float)P.bgGain / 100.0f * 12.0f - 4.0f);
        k.bgAll = P.bgGain >= 100;
        k.blueComp = (float)P.blueComp / 100.0f;
        k.ds0 = std::max(1, std::min(4, w / 960));
        k.aw = std::max(1, (w + k.ds0 - 1) / k.ds0); k.ah = std::max(1, (h + k.ds0 - 1) / k.ds0);
        k.maskOn = P.maskMode;
    }
    if (P.bloom > 0) {
        fp.bloomOn = true; fp.bloomSigma = 0.035f * w; fp.bloomDsMin = std::max(1, std::min(4, w / 960));
        k.bloomA = std::min((float)P.bloom * 0.10f, 0.9f);
        int ds = fp.bloomDsMin;
        while (ds < 64 && fp.bloomSigma / (ds * 2) >= 2.5f) ds *= 2;
        k.bloomDs = ds; k.bloomW = std::max(1, (w + ds - 1) / ds); k.bloomH = std::max(1, (h + ds - 1) / ds);
    }

    // зерно
    const bool grainOn = P.grainOn && P.grainAmount > 0;
    float sigma48 = gp == 0 ? 0.0060f * sd.grain : kIsoSigma48[(gp - 1) % 3];
    const float sizeUM = gp == 0 ? (float)P.grainSize : kIsoGrainUM[(gp - 1) % 3] * (float)P.grainSize / 12.0f;
    sigma48 *= (float)P.grainAmount / 35.0f * (1.0f + 0.25f * std::max((float)P.pushPull, 0.0f)) *
               (1.0f + 0.03f * (float)P.age * kStorageRate[std::clamp(P.storage, 0, 2)]);
    k.sigmaPix = sigma48 * 48.0f / std::sqrt(pixUM * pixUM + sizeUM * sizeUM);
    const float grainBlur = 0.5f * sizeUM / pixUM;
    const float rho = mono ? 1.0f : 1.0f - 0.85f * (float)P.chroma / 100.0f;
    k.sRho = std::sqrt(rho); k.sRho1 = std::sqrt(1.0f - rho);
    k.analogue = P.grainMode == 0;
    k.positive = P.filmType == 1 && film.cls != CL_REV;
    k.toneS = (float)P.gShadows; k.toneM = (float)P.gMid; k.toneH = (float)P.gHigh;
    k.nf = grainOn ? (mono ? 1 : 4) : 0;
    k.perPixel = grainBlur < 0.6f;
    k.originX = P.originX; k.originY = P.originY;
    k.lat1sp = std::max(1.0f, 2.0f * grainBlur);
    k.lat1ox = (int)std::floor(P.originX / k.lat1sp); k.lat1oy = (int)std::floor(P.originY / k.lat1sp);
    k.lat2sp = std::max(1.0f, std::max(2.0f, 5.0f * grainBlur));
    k.lat2ox = (int)std::floor(P.originX / k.lat2sp); k.lat2oy = (int)std::floor(P.originY / k.lat2sp);

    // плівка, друк, дисплей
    k.cls = film.cls; k.sysMode = sys.mode;
    k.colorSep = film.colorSep; k.pushShift = sys.pushShift; k.colorBoost = film.colorBoost;
    k.dmax = film.dmax; k.colorDensity = sys.colorDensity;
    for (int c = 0; c < 3; ++c) { k.balance[c] = film.s.balance[c]; k.speedLoss[c] = film.speedLoss[c]; k.dmin[c] = film.dmin[c]; }
    k.shapeOn = P.blacks != 0 || P.whites != 0 || (P.compOn && P.impact > 0);
    Lut shapeLut;
    if (k.shapeOn) shapeLut.build(-8.0f, 6.0f, 8192, [&](float v) { return shapeX(v, P); });
    else shapeLut.build(0.0f, 1.0f, 2, [](float v) { return v; });
    putLut(fp, G_SHAPE, shapeLut);
    const FastChain fx(sys);
    k.merged = fx.merged;
    for (int c = 0; c < 3; ++c) {
        putLut(fp, G_DENS0 + c, fx.dens[c]);
        putLut(fp, G_DA0 + c, fx.dispA[c]);
        putLut(fp, G_DB0 + c, fx.dispB[c]);
        if (fx.merged) putLut(fp, G_DAB0 + c, fx.dispAB[c]);
        else { Lut z; z.build(0.0f, 1.0f, 2, [](float v) { return v; }); putLut(fp, G_DAB0 + c, z); }
    }
    Lut enc; enc.build(0.0f, 1.1f, 16384, [&](float u) { return encodeTF(u * u, P.output); });
    putLut(fp, G_ENC, enc);
    // нейтральне відтворення для Mix
    k.mixOn = P.mix < 100;
    k.mix = std::clamp((float)P.mix / 100.0f, 0.0f, 1.0f);
    {
        const FastChain rf(refSys);
        for (int c = 0; c < 3; ++c) {
            putLut(fp, G_RDENS0 + c, rf.dens[c]);
            if (rf.merged) putLut(fp, G_RDAB0 + c, rf.dispAB[c]);
            else { Lut z; z.build(-3.0f, 9.0f, 4096, [&](float D) { return rf.dispB[c](rf.dispA[c](D)); }); putLut(fp, G_RDAB0 + c, z); }
        }
    }
    k.expandUser = P.expandOn && (P.blackPoint != 0 || P.whitePoint != 100);
    k.bp = (float)P.blackPoint / 100.0f; k.wp = (float)P.whitePoint / 100.0f; k.colorMode = P.colorMode;
    return fp;
}

inline std::vector<float> blurWeights(float sigma, int& r) {
    r = std::min(std::max(1, (int)std::ceil(sigma * 2.6f)), 768);
    std::vector<float> k(2 * r + 1);
    float sum = 0;
    for (int i = -r; i <= r; ++i) sum += (k[i + r] = std::exp(-0.5f * i * i / (sigma * sigma)));
    for (auto& v : k) v /= sum;
    return k;
}

// ---------- виконання плану на процесорі (еталон для перевірки Metal-ядер)
inline void cpuBlur(std::vector<float>& buf, int w, int h, float sigma) {
    if (sigma < 0.3f || w < 2 || h < 2) return;
    int r; auto wt = blurWeights(sigma, r);
    BlurP p{w, h, r, 0};
    std::vector<float> tmp(buf.size());
    for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) blurHG(buf.data(), tmp.data(), wt.data(), p, x, y);
    for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) blurVG(tmp.data(), buf.data(), wt.data(), p, x, y);
}

inline void runPlanCPU(const float* src, int srcRowFloats, float* dst, int dstRowFloats, int w, int h, FramePlan fp) {
    KParams& k = fp.k;
    k.srcRow = srcRowFloats; k.dstRow = dstRowFloats; k.offX = 0; k.offY = 0; k.srcW = w; k.srcH = h;
    const float* T = fp.luts.data();
    std::vector<float> lin, halo;
    if (k.needFrame) {
        lin.resize((size_t)w * h * 3);
        for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) stage1G(src, T, k, x, y, &lin[((size_t)y * w + x) * 3]);
        if (fp.filmResPx >= 0.3f) cpuBlur(lin, w, h, fp.filmResPx);
        if (fp.halOn) {
            struct Lv { int ds, w, h; std::vector<float> b; };
            std::vector<Lv> pyr;
            Lv l0{k.ds0, k.aw, k.ah, std::vector<float>((size_t)k.aw * k.ah * 3)};
            DownP dp{w, h, k.ds0, k.aw, k.ah, 1, 0, 0, fp.halT, 0, 0, 0};
            for (int y = 0; y < l0.h; ++y) for (int x = 0; x < l0.w; ++x) downG(lin.data(), l0.b.data(), dp, x, y);
            pyr.push_back(std::move(l0));
            while (pyr.back().w > 8 && pyr.back().h > 8 && pyr.back().ds < 64) {
                const Lv& p = pyr.back();
                Lv q{p.ds * 2, (p.w + 1) / 2, (p.h + 1) / 2, {}};
                q.b.resize((size_t)q.w * q.h * 3);
                Down2P d2{p.w, p.h, q.w, q.h};
                for (int y = 0; y < q.h; ++y) for (int x = 0; x < q.w; ++x) down2G(p.b.data(), q.b.data(), d2, x, y);
                pyr.push_back(std::move(q));
            }
            std::vector<float> acc((size_t)k.aw * k.ah * 3, 0.0f);
            for (auto& cpt : fp.halComps) {
                size_t li = 0;
                while (li + 1 < pyr.size() && cpt.sigmaPx / pyr[li + 1].ds >= 1.6f) ++li;
                std::vector<float> b = pyr[li].b;
                cpuBlur(b, pyr[li].w, pyr[li].h, cpt.sigmaPx / pyr[li].ds);
                AccP ap{pyr[li].w, pyr[li].h, k.aw, k.ah, (float)k.ds0 / pyr[li].ds, cpt.weight, 0, 0};
                for (int y = 0; y < k.ah; ++y) for (int x = 0; x < k.aw; ++x) accumG(b.data(), acc.data(), ap, x, y);
            }
            if (k.maskOn) halo.assign((size_t)w * h * 3, 0.0f);
            std::vector<float> dummy(3);
            for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x)
                halApplyG(lin.data(), acc.data(), k.maskOn ? halo.data() : dummy.data() - (size_t)0, k, x, y);
        }
        if (fp.bloomOn) {
            std::vector<float> b((size_t)k.bloomW * k.bloomH * 3);
            DownP dp{w, h, k.bloomDs, k.bloomW, k.bloomH, 0, 0, 0, 0.0f, 0, 0, 0};
            for (int y = 0; y < k.bloomH; ++y) for (int x = 0; x < k.bloomW; ++x) downG(lin.data(), b.data(), dp, x, y);
            cpuBlur(b, k.bloomW, k.bloomH, fp.bloomSigma / k.bloomDs);
            for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) bloomMixG(lin.data(), b.data(), k, x, y);
        }
    }
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x) {
            float Lb[3], hp[3] = {0, 0, 0}, out[4];
            if (k.needFrame) { for (int c = 0; c < 3; ++c) Lb[c] = lin[((size_t)y * w + x) * 3 + c]; }
            else stage1G(src, T, k, x, y, Lb);
            if (k.maskOn) for (int c = 0; c < 3; ++c) hp[c] = halo[((size_t)y * w + x) * 3 + c];
            finalG(src, T, k, x, y, Lb, hp, out);
            for (int c = 0; c < 4; ++c) dst[(size_t)y * dstRowFloats + x * 4 + c] = out[c];
        }
}

}  // namespace svitfilm
