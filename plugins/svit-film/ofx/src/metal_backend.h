// Svit Film — рендер на відеокарті Мака через Metal.
// Без заголовків Apple: рантайм Objective-C і Metal підтягуються через dlopen/dlsym, повідомлення
// надсилаються через objc_msgSend з точними типами. Шейдери компілюються з тексту під час роботи
// (newLibraryWithSource), тому для збірки не потрібен Xcode.
#pragma once
#if defined(__APPLE__) || defined(SVIT_METAL_CHECK)
#include <dlfcn.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <map>
#include <mutex>
#include <string>
#include <vector>

#include "gpu_plan.h"

namespace svitmetal {

static const char* kMetalSource =
#include "metal_src.inc"
    ;

inline void log(const std::string& s) {
    const char* home = std::getenv("HOME");
    if (!home) return;
    std::string path = std::string(home) + "/Library/Logs/Svit Film.log";
    if (FILE* f = std::fopen(path.c_str(), "a")) {
        std::time_t tt = std::time(nullptr); char ts[32];
        std::strftime(ts, sizeof ts, "%Y-%m-%d %H:%M:%S", std::localtime(&tt));
        std::fprintf(f, "%s [metal] %s\n", ts, s.c_str());
        std::fclose(f);
    }
}

// ---- рантайм Objective-C
struct ObjC {
    bool ok = false;
    void* (*getClass)(const char*) = nullptr;
    void* (*sel)(const char*) = nullptr;
    void* msg = nullptr;
    void* (*createDevice)() = nullptr;
    void* (*poolPush)() = nullptr;
    void (*poolPop)(void*) = nullptr;
#ifdef SVIT_METAL_MOCK
    ObjC();   // тест підставляє підроблений рантайм, що виконує ядра на процесорі
#else
    ObjC() {
        void* objc = dlopen("/usr/lib/libobjc.A.dylib", RTLD_NOW | RTLD_GLOBAL);
        void* metal = dlopen("/System/Library/Frameworks/Metal.framework/Metal", RTLD_NOW | RTLD_GLOBAL);
        dlopen("/System/Library/Frameworks/Foundation.framework/Foundation", RTLD_NOW | RTLD_GLOBAL);
        if (!objc || !metal) return;
        getClass = (void* (*)(const char*))dlsym(objc, "objc_getClass");
        sel = (void* (*)(const char*))dlsym(objc, "sel_registerName");
        msg = dlsym(objc, "objc_msgSend");
        createDevice = (void* (*)())dlsym(metal, "MTLCreateSystemDefaultDevice");
        poolPush = (void* (*)())dlsym(objc, "objc_autoreleasePoolPush");
        poolPop = (void (*)(void*))dlsym(objc, "objc_autoreleasePoolPop");
        ok = getClass && sel && msg && createDevice && poolPush && poolPop;
    }
#endif
};
inline ObjC& rt() { static ObjC r; return r; }

template <class R = void*, class... A> R send(void* obj, const char* s, A... a) {
    using F = R (*)(void*, void*, A...);
    return ((F)rt().msg)(obj, rt().sel(s), a...);
}
inline void release(void* o) { if (o) send<void>(o, "release"); }
inline void* nsString(const char* c) { return send(send(rt().getClass("NSString"), "alloc"), "initWithUTF8String:", c); }
inline std::string errText(void* err) {
    if (!err) return "unknown error";
    void* d = send(err, "localizedDescription");
    const char* c = d ? send<const char*>(d, "UTF8String") : nullptr;
    return c ? c : "unknown error";
}
struct MTLSize { unsigned long w, h, d; };
struct Pool {   // autorelease pool: командні буфери й помилки Metal — autoreleased-об'єкти
    void* p;
    Pool() : p(rt().ok ? rt().poolPush() : nullptr) {}
    ~Pool() { if (p) rt().poolPop(p); }
};

// ---- скомпільовані ядра для одного пристрою
enum { K_STAGE1, K_FINAL, K_BLURH, K_BLURV, K_DOWN, K_DOWN2, K_ZERO, K_ACCUM, K_HALAPPLY, K_BLOOMMIX, K_N };
static const char* kKernelNames[K_N] = {"k_stage1", "k_final", "k_blurH", "k_blurV", "k_down", "k_down2",
                                        "k_zero", "k_accum", "k_halApply", "k_bloomMix"};
struct Pipelines {
    bool ok = false; std::string error;
    void* pso[K_N] = {};
    unsigned long tgW[K_N] = {}, tgH[K_N] = {};
};

inline Pipelines compile(void* device) {
    Pipelines P;
    void* opts = send(send(rt().getClass("MTLCompileOptions"), "alloc"), "init");
    if (send<bool>(opts, "respondsToSelector:", rt().sel("setFastMathEnabled:")))
        send<void>(opts, "setFastMathEnabled:", (bool)false);   // потрібні точні isfinite/NaN
    void* src = nsString(kMetalSource);
    void* err = nullptr;
    void* lib = send(device, "newLibraryWithSource:options:error:", src, opts, &err);
    release(src); release(opts);
    if (!lib) { P.error = "shader compile: " + errText(err); return P; }
    for (int i = 0; i < K_N; ++i) {
        void* name = nsString(kKernelNames[i]);
        void* fn = send(lib, "newFunctionWithName:", name);
        release(name);
        if (!fn) { P.error = std::string("no function ") + kKernelNames[i]; release(lib); return P; }
        err = nullptr;
        P.pso[i] = send(device, "newComputePipelineStateWithFunction:error:", fn, &err);
        release(fn);
        if (!P.pso[i]) { P.error = std::string("pipeline ") + kKernelNames[i] + ": " + errText(err); release(lib); return P; }
        unsigned long mx = send<unsigned long>(P.pso[i], "maxTotalThreadsPerThreadgroup");
        unsigned long ew = send<unsigned long>(P.pso[i], "threadExecutionWidth");
        if (ew == 0) ew = 32;
        P.tgW[i] = ew; P.tgH[i] = mx / ew > 0 ? std::min<unsigned long>(mx / ew, 16) : 1;
    }
    release(lib);
    P.ok = true;
    return P;
}

inline std::mutex& mtx() { static std::mutex m; return m; }
inline std::map<void*, Pipelines>& cache() { static std::map<void*, Pipelines> c; return c; }
inline const Pipelines& pipelinesFor(void* device) {
    auto& c = cache();
    auto it = c.find(device);
    if (it != c.end()) return it->second;
    Pipelines p = compile(device);
    if (!p.ok) log(p.error);
    return c.emplace(device, p).first->second;
}

// Перевірка при завантаженні плагіна: чи компілюються ядра на системній відеокарті.
inline bool available() {
    static int state = -1;
    std::lock_guard<std::mutex> lk(mtx());
    if (state >= 0) return state == 1;
    state = 0;
    if (!rt().ok) { log("Objective-C / Metal runtime not found"); return false; }
    Pool pool;
    void* dev = rt().createDevice();
    if (!dev) { log("no Metal device"); return false; }
    void* nm = send(dev, "name");
    std::string name = nm ? send<const char*>(nm, "UTF8String") : "?";
    const Pipelines& p = pipelinesFor(dev);
    state = p.ok ? 1 : 0;
    log(p.ok ? "ready on " + name : "disabled on " + name + ": " + p.error);
    return p.ok;
}

// ---- кадр
struct Frame {
    void* dev; void* enc; const Pipelines* P;
    std::vector<void*> owned;
    void* buf(size_t bytes) {
        void* b = send(dev, "newBufferWithLength:options:", (unsigned long)std::max<size_t>(bytes, 16), (unsigned long)32);   // private
        owned.push_back(b); return b;
    }
    void* bytes(const void* p, size_t n) {
        void* b = send(dev, "newBufferWithBytes:length:options:", p, (unsigned long)std::max<size_t>(n, 4), (unsigned long)0);   // shared
        owned.push_back(b); return b;
    }
    void setBuf(void* b, int idx) { send<void>(enc, "setBuffer:offset:atIndex:", b, (unsigned long)0, (unsigned long)idx); }
    void setBytes(const void* p, size_t n, int idx) { send<void>(enc, "setBytes:length:atIndex:", p, (unsigned long)n, (unsigned long)idx); }
    void run(int kid, int w, int h) {
        send<void>(enc, "setComputePipelineState:", P->pso[kid]);
        MTLSize tg{P->tgW[kid], P->tgH[kid], 1};
        MTLSize grid{((unsigned long)w + tg.w - 1) / tg.w, ((unsigned long)h + tg.h - 1) / tg.h, 1};
        send<void>(enc, "dispatchThreadgroups:threadsPerThreadgroup:", grid, tg);
    }
    void blur(void* b, int w, int h, float sigma, void* tmp) {   // результат знову в b
        if (sigma < 0.3f || w < 2 || h < 2) return;
        int r; auto wt = svitfilm::blurWeights(sigma, r);
        void* wb = bytes(wt.data(), wt.size() * 4);
        BlurP p{w, h, r, 0};
        setBuf(b, 0); setBuf(tmp, 1); setBuf(wb, 2); setBytes(&p, sizeof p, 3); run(K_BLURH, w, h);
        setBuf(tmp, 0); setBuf(b, 1); setBuf(wb, 2); setBytes(&p, sizeof p, 3); run(K_BLURV, w, h);
    }
};

// Рендер кадру. srcBuf/dstBuf — id<MTLBuffer> від DaVinci. Повертає false, якщо Metal недоступний.
inline bool render(void* queue, void* srcBuf, void* dstBuf, svitfilm::FramePlan fp, int srcRowFloats, int dstRowFloats,
                   int offX, int offY, int srcW, int srcH, bool measure, double* gpuMs) {
    std::lock_guard<std::mutex> lk(mtx());
    if (!rt().ok || !queue) return false;
    Pool pool;
    void* dev = send(queue, "device");
    const Pipelines& PL = pipelinesFor(dev);
    if (!PL.ok) return false;
    KParams& k = fp.k;
    k.srcRow = srcRowFloats; k.dstRow = dstRowFloats; k.offX = offX; k.offY = offY; k.srcW = srcW; k.srcH = srcH;
    const int w = k.w, h = k.h;

    void* cb = send(queue, "commandBuffer");
    if (!cb) return false;
    send<void>(cb, "retain");
    void* enc = send(cb, "computeCommandEncoder");
    Frame F{dev, enc, &PL, {}};
    void* luts = F.bytes(fp.luts.data(), fp.luts.size() * 4);
    void* dummy = F.buf(16);
    void* lin = dummy; void* halo = dummy;
    if (k.needFrame) {
        lin = F.buf((size_t)w * h * 12);
        F.setBuf(srcBuf, 0); F.setBuf(lin, 1); F.setBuf(luts, 2); F.setBytes(&k, sizeof k, 3); F.run(K_STAGE1, w, h);
        if (fp.filmResPx >= 0.3f) { void* tmp = F.buf((size_t)w * h * 12); F.blur(lin, w, h, fp.filmResPx, tmp); }
        if (fp.halOn) {
            struct Lv { int ds, w, h; void* b; };
            std::vector<Lv> pyr;
            Lv l0{k.ds0, k.aw, k.ah, F.buf((size_t)k.aw * k.ah * 12)};
            DownP dp{w, h, k.ds0, k.aw, k.ah, 1, 0, 0, fp.halT, 0, 0, 0};
            F.setBuf(lin, 0); F.setBuf(l0.b, 1); F.setBytes(&dp, sizeof dp, 2); F.run(K_DOWN, l0.w, l0.h);
            pyr.push_back(l0);
            while (pyr.back().w > 8 && pyr.back().h > 8 && pyr.back().ds < 64) {
                Lv p = pyr.back();
                Lv q{p.ds * 2, (p.w + 1) / 2, (p.h + 1) / 2, nullptr};
                q.b = F.buf((size_t)q.w * q.h * 12);
                Down2P d2{p.w, p.h, q.w, q.h};
                F.setBuf(p.b, 0); F.setBuf(q.b, 1); F.setBytes(&d2, sizeof d2, 2); F.run(K_DOWN2, q.w, q.h);
                pyr.push_back(q);
            }
            void* acc = F.buf((size_t)k.aw * k.ah * 12);
            Down2P zp{0, 0, k.aw, k.ah};
            F.setBuf(acc, 0); F.setBytes(&zp, sizeof zp, 1); F.run(K_ZERO, k.aw, k.ah);
            void* t1 = F.buf((size_t)k.aw * k.ah * 12);
            void* t2 = F.buf((size_t)k.aw * k.ah * 12);
            for (auto& cpt : fp.halComps) {
                size_t li = 0;
                while (li + 1 < pyr.size() && cpt.sigmaPx / pyr[li + 1].ds >= 1.6f) ++li;
                const Lv& L = pyr[li];
                // розмиття копії рівня: рівень → t2 (по рядках) → t1 (по стовпцях)
                float sg = cpt.sigmaPx / L.ds;
                int r = 0; std::vector<float> wt(1, 1.0f);   // σ < 0.3 — без розмиття (як на процесорі)
                if (sg >= 0.3f) wt = svitfilm::blurWeights(sg, r);
                void* wb = F.bytes(wt.data(), wt.size() * 4);
                BlurP bp{L.w, L.h, r, 0};
                F.setBuf(L.b, 0); F.setBuf(t2, 1); F.setBuf(wb, 2); F.setBytes(&bp, sizeof bp, 3); F.run(K_BLURH, L.w, L.h);
                F.setBuf(t2, 0); F.setBuf(t1, 1); F.setBuf(wb, 2); F.setBytes(&bp, sizeof bp, 3); F.run(K_BLURV, L.w, L.h);
                AccP ap{L.w, L.h, k.aw, k.ah, (float)k.ds0 / L.ds, cpt.weight, 0, 0};
                F.setBuf(t1, 0); F.setBuf(acc, 1); F.setBytes(&ap, sizeof ap, 2); F.run(K_ACCUM, k.aw, k.ah);
            }
            if (k.maskOn) halo = F.buf((size_t)w * h * 12);
            F.setBuf(lin, 0); F.setBuf(acc, 1); F.setBuf(halo, 2); F.setBytes(&k, sizeof k, 3); F.run(K_HALAPPLY, w, h);
        }
        if (fp.bloomOn) {
            void* b = F.buf((size_t)k.bloomW * k.bloomH * 12);
            void* tmp = F.buf((size_t)k.bloomW * k.bloomH * 12);
            DownP dp{w, h, k.bloomDs, k.bloomW, k.bloomH, 0, 0, 0, 0.0f, 0, 0, 0};
            F.setBuf(lin, 0); F.setBuf(b, 1); F.setBytes(&dp, sizeof dp, 2); F.run(K_DOWN, k.bloomW, k.bloomH);
            F.blur(b, k.bloomW, k.bloomH, fp.bloomSigma / k.bloomDs, tmp);
            F.setBuf(lin, 0); F.setBuf(b, 1); F.setBytes(&k, sizeof k, 2); F.run(K_BLOOMMIX, w, h);
        }
    }
    F.setBuf(srcBuf, 0); F.setBuf(dstBuf, 1); F.setBuf(lin, 2); F.setBuf(luts, 3); F.setBytes(&k, sizeof k, 4);
    F.setBuf(halo, 5); F.run(K_FINAL, w, h);
    send<void>(enc, "endEncoding");
    send<void>(cb, "commit");
    if (measure && gpuMs) {   // зрідка чекаємо на завершення, щоб записати справжній час кадру
        auto t0 = std::chrono::steady_clock::now();
        send<void>(cb, "waitUntilCompleted");
        *gpuMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        long st = send<long>(cb, "status");
        if (st == 5) { void* e = send(cb, "error"); log("command buffer error: " + errText(e)); }
    }
    for (void* b : F.owned) release(b);
    release(cb);
    return true;
}

}  // namespace svitmetal
#endif
