// Перевіряє metal_backend.h без Мака: підроблений рантайм Objective-C/Metal виконує ті самі ядра
// (metal_kernels.metal, скомпільовані як C++) на процесорі. Порівнюємо з renderFull.
// Лише x86_64 Linux: виклик через типізований вказівник у варіадичну функцію там сумісний.
#include <cstdarg>
#include <cstring>
#include <map>
#include <string>
#include <vector>
#define SVIT_METAL_CHECK 1
#define SVIT_METAL_MOCK 1
#include "gpu_plan.h"
#include "svit_looks.h"
#define kernel
#define device
#define constant const
struct uint2 { unsigned x, y; };
#include "metal_kernels.metal"
#undef kernel
#undef device
#undef constant
#include "metal_backend.h"

using namespace svitmetal;
struct Obj { std::string type; std::vector<unsigned char> data; int kid = -1; void* p = nullptr; };
static std::map<std::string, std::string> gSel;
static void* selName(const char* s) { auto& v = gSel[s]; v = s; return (void*)gSel.find(s)->first.c_str(); }
static void* getClassM(const char* n) { static std::map<std::string, Obj*> m; auto& o = m[n]; if (!o) { o = new Obj; o->type = std::string("class:") + n; } return o; }
static Obj* mk(const char* t) { Obj* o = new Obj; o->type = t; return o; }
struct Enc { int kid = -1; std::map<int, Obj*> bufs; std::map<int, std::vector<unsigned char>> bytes; };
static Enc gEnc;
static int dispatches = 0;
static float* B(int i) {
    if (gEnc.bytes.count(i)) return (float*)gEnc.bytes[i].data();
    return (float*)gEnc.bufs.at(i)->data.data();
}
static void runKernel(int kid, unsigned gx, unsigned gy) {
    ++dispatches;
    for (unsigned y = 0; y < gy; ++y)
        for (unsigned x = 0; x < gx; ++x) {
            uint2 g{x, y};
            switch (kid) {
            case K_STAGE1: k_stage1(B(0), B(1), B(2), *(KParams*)B(3), g); break;
            case K_FINAL: k_final(B(0), B(1), B(2), B(3), *(KParams*)B(4), B(5), g); break;
            case K_BLURH: k_blurH(B(0), B(1), B(2), *(BlurP*)B(3), g); break;
            case K_BLURV: k_blurV(B(0), B(1), B(2), *(BlurP*)B(3), g); break;
            case K_DOWN: k_down(B(0), B(1), *(DownP*)B(2), g); break;
            case K_DOWN2: k_down2(B(0), B(1), *(Down2P*)B(2), g); break;
            case K_ZERO: k_zero(B(0), *(Down2P*)B(1), g); break;
            case K_ACCUM: k_accum(B(0), B(1), *(AccP*)B(2), g); break;
            case K_HALAPPLY: k_halApply(B(0), B(1), B(2), *(KParams*)B(3), g); break;
            case K_BLOOMMIX: k_bloomMix(B(0), B(1), *(KParams*)B(2), g); break;
            }
        }
}
extern "C" void* mockMsg(void* self, void* sel, ...) {
    const char* s = (const char*)sel; Obj* o = (Obj*)self;
    va_list ap; va_start(ap, sel);
    void* r = nullptr;
    if (!strcmp(s, "alloc")) r = mk(o->type.c_str() + 6);
    else if (!strcmp(s, "init") || !strcmp(s, "retain")) r = self;
    else if (!strcmp(s, "release")) {}
    else if (!strcmp(s, "initWithUTF8String:")) { const char* c = va_arg(ap, const char*); o->data.assign(c, c + strlen(c) + 1); r = o; }
    else if (!strcmp(s, "UTF8String")) r = o->data.data();
    else if (!strcmp(s, "setFastMathEnabled:")) {}
    else if (!strcmp(s, "respondsToSelector:")) r = (void*)(uintptr_t)1;
    else if (!strcmp(s, "newLibraryWithSource:options:error:")) r = mk("library");
    else if (!strcmp(s, "newFunctionWithName:")) {
        Obj* n = va_arg(ap, Obj*); Obj* f = mk("function");
        for (int i = 0; i < K_N; ++i) if (!strcmp((const char*)n->data.data(), kKernelNames[i])) f->kid = i;
        r = f->kid >= 0 ? f : nullptr;
    }
    else if (!strcmp(s, "newComputePipelineStateWithFunction:error:")) { Obj* f = va_arg(ap, Obj*); Obj* p = mk("pso"); p->kid = f->kid; r = p; }
    else if (!strcmp(s, "maxTotalThreadsPerThreadgroup")) r = (void*)(uintptr_t)1024;
    else if (!strcmp(s, "threadExecutionWidth")) r = (void*)(uintptr_t)32;
    else if (!strcmp(s, "name")) { Obj* n = mk("str"); const char* c = "Mock GPU"; n->data.assign(c, c + 9); r = n; }
    else if (!strcmp(s, "device")) r = o->p;
    else if (!strcmp(s, "commandBuffer")) r = mk("cb");
    else if (!strcmp(s, "computeCommandEncoder")) { gEnc = Enc(); r = mk("enc"); }
    else if (!strcmp(s, "newBufferWithLength:options:")) { unsigned long n = va_arg(ap, unsigned long); Obj* b = mk("buf"); b->data.assign(n, 0xAB); r = b; }   // сміття: перевіряємо, що ядра не читають неініціалізоване
    else if (!strcmp(s, "newBufferWithBytes:length:options:")) { const unsigned char* p = va_arg(ap, const unsigned char*); unsigned long n = va_arg(ap, unsigned long); Obj* b = mk("buf"); b->data.assign(p, p + n); r = b; }
    else if (!strcmp(s, "setComputePipelineState:")) { Obj* p = va_arg(ap, Obj*); gEnc.kid = p->kid; }
    else if (!strcmp(s, "setBuffer:offset:atIndex:")) { Obj* b = va_arg(ap, Obj*); va_arg(ap, unsigned long); unsigned long i = va_arg(ap, unsigned long); gEnc.bufs[(int)i] = b; gEnc.bytes.erase((int)i); }
    else if (!strcmp(s, "setBytes:length:atIndex:")) { const unsigned char* p = va_arg(ap, const unsigned char*); unsigned long n = va_arg(ap, unsigned long); unsigned long i = va_arg(ap, unsigned long); gEnc.bytes[(int)i].assign(p, p + n); }
    else if (!strcmp(s, "dispatchThreadgroups:threadsPerThreadgroup:")) {
        MTLSize grid = va_arg(ap, MTLSize), tg = va_arg(ap, MTLSize);
        runKernel(gEnc.kid, (unsigned)(grid.w * tg.w), (unsigned)(grid.h * tg.h));
    }
    else if (!strcmp(s, "endEncoding") || !strcmp(s, "commit") || !strcmp(s, "waitUntilCompleted")) {}
    else if (!strcmp(s, "status")) r = (void*)(uintptr_t)4;
    else { fprintf(stderr, "unhandled selector %s\n", s); abort(); }
    va_end(ap);
    return r;
}
static Obj* gDevice;
static void* createDeviceM() { return gDevice; }
static void* pushM() { return (void*)1; }
static void popM(void*) {}
svitmetal::ObjC::ObjC() {
    getClass = getClassM; sel = (void* (*)(const char*))selName; msg = (void*)&mockMsg; createDevice = createDeviceM;
    poolPush = pushM; poolPop = popM; ok = true;
}

static int fails = 0;
static void cmp(const char* name, svitfilm::Params P, int w = 200, int h = 112) {
    std::vector<float> s((size_t)w * h * 4);
    for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) {
        float* p = &s[((size_t)y * w + x) * 4];
        p[0] = (float)x / w; p[1] = (float)y / h; p[2] = 0.5f + 0.5f * std::sin(x * 0.07f + y * 0.05f); p[3] = 0.7f;
        if ((x - w / 3) * (x - w / 3) + (y - h / 2) * (y - h / 2) < 40) p[0] = p[1] = p[2] = 1.0f;
    }
    std::vector<float> a(s.size());
    svitfilm::render(s.data(), w * 4, a.data(), w * 4, w, h, P);
    Obj* srcB = mk("buf"); srcB->data.assign((unsigned char*)s.data(), (unsigned char*)(s.data() + s.size()));
    Obj* dstB = mk("buf"); dstB->data.assign(s.size() * 4, 0);
    Obj* queue = mk("queue"); queue->p = gDevice;
    double ms = 0;
    bool ok = svitmetal::render(queue, srcB, dstB, svitfilm::buildPlan(P, w, h), w * 4, w * 4, 0, 0, w, h, true, &ms);
    const float* b = (const float*)dstB->data.data();
    float mx = 0; for (size_t i = 0; i < a.size(); ++i) mx = std::max(mx, std::fabs(a[i] - b[i]));
    bool good = ok && mx < 0.004f;
    if (!good) ++fails;
    printf("%s %-26s max %.5f\n", good ? "ok  " : "FAIL", name, mx);
}
int main() {
    gDevice = mk("device");
    printf("available: %d\n", (int)svitmetal::available());
    svitfilm::Params P; cmp("default", P);
    P = svitfilm::Params(); P.input = svitfilm::IN_LOGC3; P.grainOn = true; cmp("logc3 grain", P);
    P = svitfilm::Params(); P.grainOn = true; P.grainProfile = 3; P.filmRes = 20; cmp("8mm grain + filmres", P);
    P = svitfilm::Params(); P.halOn = true; P.stock = 13; cmp("halation", P);
    P = svitfilm::Params(); P.lensOn = true; P.distortion = 55; P.chromAb = 40; P.edgeBlur = 50; P.swirl = 80; P.frameMode = 1; cmp("lens fisheye", P);
    P = svitfilm::Params(); P.halOn = true; P.maskMode = true; P.globalDiff = 90; cmp("halation mask", P);
    P = svitfilm::Params(); P.bloom = 1.5; cmp("bloom", P);
    P = svitfilm::Params(); P.mix = 30; P.leak = 1; P.frame = 9; cmp("mix leak", P);
    for (int i = 1; i <= (int)svitfilm::looks().size(); ++i) { svitfilm::Params Q; Q.frame = 4; svitfilm::applyLook(Q, i); cmp(svitfilm::looks()[i - 1].name, Q); }
    printf("dispatches: %d\n%s\n", dispatches, fails ? "FAILED" : "ALL OK");
    return fails ? 1 : 0;
}
