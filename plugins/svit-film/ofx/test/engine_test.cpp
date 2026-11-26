// Тести ядра Svit Film 2 (без DaVinci): g++ -std=c++17 -O2 -Isrc test/engine_test.cpp && ./a.out
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

#include "svitfilm_core.h"
#include "svit_looks.h"

using namespace svitfilm;
static int fails = 0;
#define CHECK(c, ...) do { if (!(c)) { ++fails; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static std::vector<float> run(const std::vector<float>& src, int w, int h, const Params& P) {
    std::vector<float> dst(src.size(), -1.0f);
    render(src.data(), w * 4, dst.data(), w * 4, w, h, P);
    return dst;
}
static std::vector<float> ramp(int w, int h, float lo = 0, float hi = 1) {   // по x — рівень, по y — колір
    std::vector<float> s((size_t)w * h * 4);
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x) {
            float v = lo + (hi - lo) * x / (w - 1);
            float* p = &s[((size_t)y * w + x) * 4];
            int k = y % 4;
            p[0] = k == 1 ? v * 0.3f : v; p[1] = k == 2 ? v * 0.4f : v; p[2] = k == 3 ? v * 0.5f : v; p[3] = 1;
        }
    return s;
}
static Params plain() {   // без ефектів, що додають просторові зміни
    Params P; P.grainOn = false; P.halOn = false; P.bloom = 0; P.vignette = 0; P.weave = 0; return P;
}

int main() {
    const int W = 256, H = 8;
    auto src = ramp(W, H);

    // 1) нейтральний обхід: дисплейний вхід, плівка і друк вимкнені → тотожність
    for (int in : {IN_REC709, IN_REC2020, IN_APPLE20}) {
        Params P = plain(); P.input = in; P.filmOn = false; P.printOn = false;
        P.output = in == IN_REC2020 ? OUT_REC2020 : in == IN_APPLE20 ? OUT_APPLE20 : OUT_REC709;
        auto d = run(src, W, H, P);
        float err = 0;
        for (size_t i = 0; i < d.size(); ++i) if (i % 4 != 3) err = std::max(err, std::fabs(d[i] - src[i]));
        CHECK(err < 0.01f, "identity input %d: max error %.4f", in, err);
        printf("identity %-16s max err %.5f\n", kInputNames[in], err);
    }

    // 2) монотонність сірої шкали для кожної плівки і кожного друку
    for (int s = 0; s < kNumStocks; ++s)
        for (int pr = 0; pr <= kNumPrints; ++pr) {
            Params P = plain(); P.input = IN_ACESCCT; P.stock = s; P.print = pr;
            auto g = ramp(W, 1, 0.0f, 1.0f);
            auto d = run(g, W, 1, P);
            float prev = -1; bool ok = true;
            for (int x = 0; x < W; ++x) {
                float Y = 0.2126f * d[x * 4] + 0.7152f * d[x * 4 + 1] + 0.0722f * d[x * 4 + 2];
                if (Y < prev - 1e-4f) ok = false;
                prev = Y;
            }
            CHECK(ok, "non-monotonic grey ramp: %s / print %d", kStocks[s].name, pr);
        }

    // 3) 18% сірий (ACEScct) → калібрований сірий для нейтральної плівки
    {
        float cct = (std::log2(0.18f) + 9.72f) / 17.52f;
        std::vector<float> g(16 * 4, cct); for (int i = 3; i < 64; i += 4) g[i] = 1;
        Params P = plain(); P.input = IN_ACESCCT; P.filmOn = false; P.printOn = false;
        auto d = run(g, 16, 1, P);
        float want = encodeTF(kTargetY, OUT_REC709);
        CHECK(std::fabs(d[0] - want) < 0.01f && std::fabs(d[1] - want) < 0.01f && std::fabs(d[2] - want) < 0.01f,
              "mid grey %.3f %.3f %.3f vs %.3f", d[0], d[1], d[2], want);
        for (int s = 0; s < 4; ++s) {   // VISION3 без балансу: сірий має лишатися майже нейтральним
            P.filmOn = true; P.printOn = true; P.stock = s; P.print = 0;
            auto e = run(g, 16, 1, P);
            float spread = std::max({e[0], e[1], e[2]}) - std::min({e[0], e[1], e[2]});
            CHECK(spread < 0.02f, "%s grey spread %.3f", kStocks[s].name, spread);
        }
    }

    // 4) скінченні значення на екстремальних входах з усіма ефектами
    {
        std::vector<float> x((size_t)64 * 32 * 4);
        const float vals[] = {NAN, INFINITY, -INFINITY, -1.0f, 0.0f, 1e6f, 2.0f, 0.5f};
        for (size_t i = 0; i < x.size(); ++i) x[i] = vals[(i * 7 + i / 13) % 8];
        for (int in = 0; in < kNumInputs; ++in)
            for (int s : {0, 13, 14, 18}) {
                Params P; P.input = in; P.stock = s; P.bloom = 1; P.amplify = 100; P.globalDiff = 100; P.vignette = 1; P.weave = 1; P.filmType = s % 2;
                P.devOn = P.compOn = true; P.contrastBoost = 100; P.colorBoost = 100; P.pushPull = 3;
                P.blacks = 1; P.whites = -1; P.blackPoint = 20; P.whitePoint = 50; P.colorMode = 1;
                auto d = run(x, 64, 32, P);
                bool ok = true;
                for (size_t i = 0; i < d.size(); ++i) if (i % 4 != 3 && !(d[i] >= 0 && d[i] <= 1)) ok = false;
                CHECK(ok, "non-finite output: input %d stock %d", in, s);
            }
    }

    // 5) детермінованість зерна
    {
        auto g = ramp(96, 64, 0.2f, 0.8f);
        Params P = plain(); P.grainOn = true; P.frame = 5;
        auto a = run(g, 96, 64, P), b = run(g, 96, 64, P);
        CHECK(a == b, "same frame gives different grain");
        P.frame = 6; auto c = run(g, 96, 64, P);
        CHECK(a != c, "grain does not change between frames");
        P.freezeGrain = true; P.frame = 5; auto e = run(g, 96, 64, P); P.frame = 9; auto f = run(g, 96, 64, P);
        CHECK(e == f, "frozen grain changes");
        // зерно не зсуває середнє
        Params Q = plain(); auto n = run(g, 96, 64, Q);
        double sa = 0, sn = 0; for (size_t i = 0; i < a.size(); i += 4) { sa += a[i + 1]; sn += n[i + 1]; }
        double diff = std::fabs(sa - sn) / (a.size() / 4);
        CHECK(diff < 0.01, "grain shifts mean by %.4f", diff);
        printf("grain mean shift %.5f\n", diff);
    }

    // 6) halation: рівне поле лишається рівним (лише трохи світлішим), біля джерела — червоне сяйво
    {
        std::vector<float> g((size_t)128 * 64 * 4, 0.45f);
        Params P = plain(); P.halOn = true; P.halProfile = 6; P.amplify = 100; P.bloom = 1; P.bgGain = 100;
        auto b = run(g, 128, 64, P);
        float mn = 1, mx = 0;
        for (int y = 16; y < 48; ++y) for (int x = 32; x < 96; ++x) { float v = b[((size_t)y * 128 + x) * 4]; mn = std::min(mn, v); mx = std::max(mx, v); }
        CHECK(mx - mn < 0.004f, "halation makes a flat field uneven by %.4f", mx - mn);
        const int W2 = 384, H2 = 128;
        std::vector<float> s((size_t)W2 * H2 * 4, 0.05f);
        float hot = (std::log2(40.0f) + 9.72f) / 17.52f;
        for (int y = 60; y < 68; ++y) for (int x = 188; x < 196; ++x) for (int c = 0; c < 3; ++c) s[((size_t)y * W2 + x) * 4 + c] = hot;
        Params Q = plain(); Q.input = IN_ACESCCT; Q.halOn = true; Q.halProfile = 0; Q.stock = 13;   // CineStill, без remjet
        Params Q0 = Q; Q0.halOn = false;
        auto h1 = run(s, W2, H2, Q), h2 = run(s, W2, H2, Q0);
        Params R = Q; R.stock = 0; auto h3 = run(s, W2, H2, R);   // VISION3 з remjet
        size_t at = ((size_t)64 * W2 + 196 + 4) * 4;
        float dR = h1[at] - h2[at], dB = h1[at + 2] - h2[at + 2], dRj = h3[at] - h2[at];
        printf("halation near source: CineStill dR %.3f dB %.3f, VISION3(remjet) dR %.3f\n", dR, dB, dRj);
        CHECK(dR > 0.02f && dR > 3 * std::max(dB, 0.0f), "no red halo (dR %.3f dB %.3f)", dR, dB);
        CHECK(dRj < dR * 0.6f, "remjet should reduce halation (%.3f vs %.3f)", dRj, dR);
        HalKernel k0 = halKernel(false), k1 = halKernel(true);
        printf("kernel energy: no remjet %.3f, remjet %.3f\n", k0.total, k1.total);
        CHECK(k0.total > 0.2f && k0.total < 0.6f && k1.total < 0.1f, "kernel energies off");
    }

    // 7) ч/б плівки дають R=G=B; оборотна плівка — щільність падає з експозицією
    {
        for (int s : {18, 19}) {
            Params P = plain(); P.stock = s;
            auto d = run(src, W, H, P);
            float e = 0; for (size_t i = 0; i < d.size(); i += 4) e = std::max({e, std::fabs(d[i] - d[i + 1]), std::fabs(d[i + 2] - d[i + 1])});
            CHECK(e < 1e-5f, "B&W stock %s not neutral (%.5f)", kStocks[s].name, e);
        }
        Params P = plain(); Film f = makeFilm(kStocks[14], P, false);
        CHECK(f.density(1, -0.5f) > f.density(1, 0.5f), "reversal density should fall with exposure");
        Film n = makeFilm(kStocks[0], P, false);
        CHECK(n.density(1, -0.5f) < n.density(1, 0.5f), "negative density should rise with exposure");
    }

    // 8) push: середній сірий після таймінгу друку майже на місці, контраст вищий
    {
        float cct0 = (std::log2(0.18f) + 9.72f) / 17.52f, cct1 = (std::log2(0.72f) + 9.72f) / 17.52f;
        std::vector<float> g = {cct0, cct0, cct0, 1, cct1, cct1, cct1, 1};
        Params P = plain(); P.input = IN_ACESCCT; P.stock = 0;
        auto a = run(g, 2, 1, P); P.pushPull = 2; auto b = run(g, 2, 1, P);
        CHECK(std::fabs(a[1] - b[1]) < 0.02f, "push moves mid grey %.3f -> %.3f", a[1], b[1]);
        CHECK((b[5] - b[1]) > (a[5] - a[1]), "push should raise contrast");
    }

    // 9) експозиція: + світліше; blacks/whites діють у своїх зонах
    {
        Params P = plain(); P.input = IN_ACESCCT;
        auto g = ramp(W, 1, 0.2f, 0.7f);
        auto a = run(g, W, 1, P); P.exposure = 1; auto b = run(g, W, 1, P);
        CHECK(b[(W / 2) * 4 + 1] > a[(W / 2) * 4 + 1], "exposure + should brighten");
        Params B = plain(); B.input = IN_ACESCCT; B.blacks = 1; auto c = run(g, W, 1, B);
        CHECK(c[4 * 4 + 1] > a[4 * 4 + 1] + 0.01f, "blacks + should lift shadows");
        Params Wt = plain(); Wt.input = IN_ACESCCT; Wt.whites = -1; auto d = run(g, W, 1, Wt);
        CHECK(d[(W - 2) * 4 + 1] < a[(W - 2) * 4 + 1] - 0.01f, "whites - should darken highlights");
    }

    // 10) 30 образів: усі ключі відомі, результат скінченний і відрізняється від нейтрального
    {
        CHECK(looks().size() == 60, "expected 60 looks, got %zu", looks().size());
        auto g = ramp(96, 48, 0.0f, 1.0f);
        Params N = plain(); N.filmOn = false; N.printOn = false; auto n = run(g, 96, 48, N);
        for (int i = 1; i <= (int)looks().size(); ++i) {
            Params P; P.frame = 3;
            CHECK(applyLook(P, i), "look %d has unknown keys", i);
            auto d = run(g, 96, 48, P);
            bool ok = true; double diff = 0;
            for (size_t k = 0; k < d.size(); ++k) { if (!(d[k] >= 0 && d[k] <= 1)) ok = false; diff += std::fabs(d[k] - n[k]); }
            CHECK(ok, "look %s: bad values", looks()[i - 1].name);
            CHECK(diff / d.size() > 0.005, "look %s looks neutral", looks()[i - 1].name);
        }
    }

    // 11) унікальні модулі: прострочена плівка, крос-процес, засвітка, Mix
    {
        auto g = ramp(64, 4, 0.0f, 1.0f);
        Params A = plain(); auto a = run(g, 64, 4, A);
        Params E = plain(); E.age = 20; E.storage = 2; auto e = run(g, 64, 4, E);
        CHECK(e[0] > a[0] + 0.01f || e[2] > a[2] + 0.01f, "expired film should fog the shadows");
        Params C = plain(); C.cross = 100; auto c = run(g, 64, 4, C);
        size_t hi = 56 * 4;
        CHECK(c[hi + 2] < c[hi] - 0.01f, "cross process: highlights should go yellow (B < R): %.3f %.3f", c[hi], c[hi + 2]);
        Params Lk = plain(); Lk.leak = 1; Lk.leakPos = 0; auto l = run(g, 64, 4, Lk);
        CHECK(l[0] > a[0] + 0.05f && std::fabs(l[60 * 4 + 1] - a[60 * 4 + 1]) < 0.02f, "leak should come from the left edge");
        Params M = plain(); M.stock = 13; M.mix = 0; auto m = run(g, 64, 4, M);
        Params Nn = plain(); Nn.filmOn = false; Nn.printOn = false; auto nn = run(g, 64, 4, Nn);
        float err = 0; for (size_t k = 0; k < m.size(); ++k) err = std::max(err, std::fabs(m[k] - nn[k]));
        CHECK(err < 0.01f, "mix 0 should equal neutral (%.4f)", err);
    }

    // 12) засвітка рухається плавно: між сусідніми кадрами немає стрибків
    {
        const int W3 = 64, H3 = 36;
        std::vector<float> g((size_t)W3 * H3 * 4, 0.2f);
        float worst = 0;
        std::vector<float> prev;
        for (int f = 0; f < 300; ++f) {
            Params L = plain(); L.leak = 1; L.leakPos = 4; L.leakSpeed = 0.3; L.frame = f;
            auto d = run(g, W3, H3, L);
            if (!prev.empty()) for (size_t i = 0; i < d.size(); ++i) worst = std::max(worst, std::fabs(d[i] - prev[i]));
            prev = d;
        }
        printf("leak max frame-to-frame change %.4f\n", worst);
        CHECK(worst < 0.06f, "light leak jumps between frames (%.3f)", worst);
    }

    // 13) Look Amount: 0 — без образу, 1 — образ, 2 — сильніше, у межах повзунків
    {
        Params A; applyLook(A, 33, 0.0); Params D;
        CHECK(A.stock == D.stock && !A.grainOn && !A.halOn && A.mix == 100, "amount 0 should be neutral");
        Params B; applyLook(B, 33, 1.0); Params C; applyLook(C, 33, 2.0); Params Hh; applyLook(Hh, 33, 0.5);
        CHECK(C.colorBoost > B.colorBoost && B.colorBoost > Hh.colorBoost && C.colorBoost <= 100, "amount scaling");
        CHECK(Hh.mix == 50 && Hh.grainAmount < B.grainAmount, "half look mixes and halves grain");
    }

    // Lens: увімкнений без змін = те саме; дисторсія не зсуває центр; коло fisheye чорнить кути
    {
        const int LW = 96, LH = 64;
        std::vector<float> img((size_t)LW * LH * 4);
        for (int y = 0; y < LH; ++y) for (int x = 0; x < LW; ++x) {
            float* q = &img[((size_t)y * LW + x) * 4];
            q[0] = (x % 8 < 4) ? 0.8f : 0.2f; q[1] = (y % 8 < 4) ? 0.7f : 0.3f; q[2] = 0.5f; q[3] = 1;
        }
        Params A = plain(); Params B = A; B.lensOn = true;
        auto a = run(img, LW, LH, A), b = run(img, LW, LH, B);
        float e = 0; for (size_t i = 0; i < a.size(); ++i) e = std::max(e, std::fabs(a[i] - b[i]));
        CHECK(e < 1e-6f, "lens on with zero sliders changes the image (%.5f)", e);
        Params D = B; D.distortion = 80;
        auto d = run(img, LW, LH, D);
        float diff = 0; for (size_t i = 0; i < a.size(); ++i) diff += std::fabs(d[i] - a[i]);
        CHECK(diff / a.size() > 0.01f, "distortion did nothing");
        Params R = B; R.frameMode = 1; R.frameSoft = 0;
        auto r = run(img, LW, LH, R);
        CHECK(r[0] < 0.03f && r[1] < 0.03f && r[2] < 0.03f, "round frame corner not black (%.3f)", r[0]);
        CHECK(!isIdentity([&] { Params N = neutralParams(); N.lensOn = true; N.edgeBlur = 30; return N; }()), "lens must not be identity");
        printf("lens ok\n");
    }

    // чистий стан: плагін нічого не робить (DaVinci пропускає кадр)
    {
        Params N = neutralParams();
        CHECK(isIdentity(N), "neutral params must be identity");
        Params L = N; applyLook(L, 5, 1.0);
        CHECK(!isIdentity(L), "a look must not be identity");
        Params E = N; E.exposure = 0.5; CHECK(!isIdentity(E), "exposure change is not identity");
        Params S = N; S.input = IN_SLOG3SG3; CHECK(!isIdentity(S), "log input is a conversion, not identity");
        // режим «поверх образу»: повзунки на нулі = рівно образ
        for (int i = 1; i <= (int)looks().size(); ++i) {
            Params A; applyLook(A, i, 0.7);
            Params B = lookPlusOffsets(N, i, 0.7);
            bool same = true;
            for (auto& f : lookFields()) if (std::fabs(getField(A, f) - getField(B, f)) > 1e-9) same = false;
            CHECK(same, "look %d: zero offsets must equal the look", i);
        }
        Params U = N; U.exposure = 0.5; U.mix = 50;
        Params B = lookPlusOffsets(U, 1, 1.0); Params A; applyLook(A, 1, 1.0);
        CHECK(std::fabs(B.exposure - (A.exposure + 0.5)) < 1e-9 && std::fabs(B.mix - A.mix * 0.5) < 1e-9, "offsets add on top of the look");
        printf("clean state / Apply All Settings ok\n");
    }

    printf(fails ? "\n%d FAILED\n" : "\nALL OK\n", fails);
    return fails ? 1 : 0;
}
