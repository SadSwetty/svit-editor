// Перевіряє, що план кадру + спільний код ядер (gpu_shared.h) дає той самий результат, що й renderFull.
// Так Metal-шлях тестується без Мака: ядра Metal викликають ті самі функції.
#include <cmath>
#include <cstdio>
#include "gpu_plan.h"
#include "svit_looks.h"
using namespace svitfilm;
static int fails = 0;
static std::vector<float> img(int w, int h) {
    std::vector<float> s((size_t)w * h * 4);
    for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) {
        float* p = &s[((size_t)y * w + x) * 4];
        p[0] = (float)x / w; p[1] = (float)y / h; p[2] = 0.5f + 0.5f * std::sin(x * 0.07f + y * 0.05f); p[3] = 0.8f;
        if ((x - w / 3) * (x - w / 3) + (y - h / 2) * (y - h / 2) < 30) p[0] = p[1] = p[2] = 1.0f;   // яскрава точка
    }
    return s;
}
static void cmp(const char* name, Params P, int w = 160, int h = 96) {
    auto s = img(w, h);
    std::vector<float> a(s.size()), b(s.size());
    render(s.data(), w * 4, a.data(), w * 4, w, h, P);
    FramePlan fp = buildPlan(P, w, h);
    runPlanCPU(s.data(), w * 4, b.data(), w * 4, w, h, fp);
    float mx = 0; double mean = 0;
    for (size_t i = 0; i < a.size(); ++i) { float d = std::fabs(a[i] - b[i]); mx = std::max(mx, d); mean += d; }
    mean /= a.size();
    bool ok = mx < 0.004f && mean < 0.0005;
    if (!ok) ++fails;
    printf("%s %-28s max %.5f mean %.6f\n", ok ? "ok  " : "FAIL", name, mx, mean);
}
int main() {
    Params P; cmp("default", P);
    P = Params(); P.input = IN_ACESCCT; cmp("acescct", P);
    P = Params(); P.input = IN_LOGC3; P.output = OUT_P3; cmp("logc3->p3", P);
    P = Params(); P.grainOn = true; cmp("grain", P);
    P = Params(); P.grainOn = true; P.grainProfile = 3; cmp("grain 8mm (lattice)", P);
    P = Params(); P.grainOn = true; P.grainMode = 1; P.filmType = 1; cmp("grain digital positive", P);
    P = Params(); P.halOn = true; P.stock = 13; cmp("halation cinestill", P);
    P = Params(); P.halOn = true; P.halProfile = 2; P.globalDiff = 80; cmp("halation super8", P);
    P = Params(); P.halOn = true; P.maskMode = true; cmp("halation mask", P);
    P = Params(); P.bloom = 1; cmp("bloom", P);
    P = Params(); P.stock = 18; P.grainOn = true; cmp("tri-x", P);
    P = Params(); P.stock = 14; cmp("e100 slide", P);
    P = Params(); P.print = 3; cmp("film scan", P);
    P = Params(); P.compOn = true; P.colorDensity = 80; P.devOn = true; P.colorBoost = 30; cmp("compression+colordensity", P);
    P = Params(); P.mix = 40; cmp("mix 40", P);
    P = Params(); P.mix = 40; P.input = IN_SLOG3; cmp("mix 40 slog3", P);
    P = Params(); P.blackPoint = 5; P.whitePoint = 90; P.colorMode = 1; cmp("expand lum", P);
    P = Params(); P.leak = 1; P.frame = 7; P.vignette = 0.5; P.weave = 1; cmp("leak vignette weave", P);
    P = Params(); P.age = 15; P.storage = 2; P.cross = 70; cmp("expired cross", P);
    P = Params(); P.grainOn = true; P.originX = 37; P.originY = 11; cmp("grain origin", P);
    for (int i = 0; i < (int)lensPresets().size(); ++i) {
        const auto& L = lensPresets()[i]; Params Q; Q.lensOn = true; Q.distortion = L.dist; Q.lensZoom = L.zoom; Q.chromAb = L.ca;
        Q.edgeBlur = L.blur; Q.swirl = L.swirl; Q.tiltShift = L.tilt; Q.lensVig = L.vig; Q.frameMode = L.frame; Q.frameSize = L.fsize;
        Q.frameSoft = L.fsoft; Q.weave = 0.5; Q.frame = 3; cmp(L.name, Q);
    }
    { Params Q; Q.lensOn = true; Q.distortion = 60; Q.halOn = true; Q.bloom = 0.5; Q.grainOn = true; cmp("lens + spatial", Q); }
    for (int i = 1; i <= (int)looks().size(); ++i) { Params Q; Q.frame = 5; applyLook(Q, i); cmp(looks()[i - 1].name, Q); }
    Params Q; applyLook(Q, 3); cmp("Neon Rain 1280x720", Q, 1280, 720);
    printf(fails ? "\n%d FAILED\n" : "\nALL OK\n", fails);
    return fails ? 1 : 0;
}
