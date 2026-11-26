// Мінімальний OFX-хост для перевірки Svit Film без DaVinci:
// завантажує плагін, проходить load → describe → describeInContext → createInstance → render.
// minihost <plugin.so> <w> <h> <in.rgba32f> <out.rgba32f> [mode] [param=value ...]
//   mode: normal | flip (від'ємний rowBytes) | bigsrc (джерело більше за кадр результату)
#include <dlfcn.h>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "ofxCore.h"
#include "ofxImageEffect.h"
#include "ofxParam.h"
#include "ofxProperty.h"

struct Val { std::vector<std::string> s; std::vector<int> i; std::vector<double> d; std::vector<void*> p; };
struct PropSet { std::map<std::string, Val> m; };
static PropSet* P(OfxPropertySetHandle h) { return (PropSet*)h; }
static std::vector<std::unique_ptr<PropSet>> gAll;
static PropSet* newPS() { gAll.emplace_back(new PropSet); return gAll.back().get(); }
template <class T> static void put(std::vector<T>& v, int i, T x) { if ((int)v.size() <= i) v.resize(i + 1); v[i] = x; }

static OfxStatus setS(OfxPropertySetHandle h, const char* n, int i, const char* v) { put(P(h)->m[n].s, i, std::string(v)); return kOfxStatOK; }
static OfxStatus setI(OfxPropertySetHandle h, const char* n, int i, int v) { put(P(h)->m[n].i, i, v); return kOfxStatOK; }
static OfxStatus setD(OfxPropertySetHandle h, const char* n, int i, double v) { put(P(h)->m[n].d, i, v); return kOfxStatOK; }
static OfxStatus setP(OfxPropertySetHandle h, const char* n, int i, void* v) { put(P(h)->m[n].p, i, v); return kOfxStatOK; }
static OfxStatus setSN(OfxPropertySetHandle h, const char* n, int c, const char* const* v) { for (int i = 0; i < c; ++i) setS(h, n, i, v[i]); return kOfxStatOK; }
static OfxStatus setIN(OfxPropertySetHandle h, const char* n, int c, const int* v) { for (int i = 0; i < c; ++i) setI(h, n, i, v[i]); return kOfxStatOK; }
static OfxStatus setDN(OfxPropertySetHandle h, const char* n, int c, const double* v) { for (int i = 0; i < c; ++i) setD(h, n, i, v[i]); return kOfxStatOK; }
static OfxStatus setPN(OfxPropertySetHandle h, const char* n, int c, void* const* v) { for (int i = 0; i < c; ++i) setP(h, n, i, v[i]); return kOfxStatOK; }
static OfxStatus getS(OfxPropertySetHandle h, const char* n, int i, char** v) {
    auto it = P(h)->m.find(n); if (it == P(h)->m.end() || (int)it->second.s.size() <= i) return kOfxStatErrUnknown;
    *v = (char*)it->second.s[i].c_str(); return kOfxStatOK; }
static OfxStatus getI(OfxPropertySetHandle h, const char* n, int i, int* v) {
    auto it = P(h)->m.find(n); if (it == P(h)->m.end() || (int)it->second.i.size() <= i) return kOfxStatErrUnknown;
    *v = it->second.i[i]; return kOfxStatOK; }
static OfxStatus getD(OfxPropertySetHandle h, const char* n, int i, double* v) {
    auto it = P(h)->m.find(n); if (it == P(h)->m.end() || (int)it->second.d.size() <= i) return kOfxStatErrUnknown;
    *v = it->second.d[i]; return kOfxStatOK; }
static OfxStatus getP(OfxPropertySetHandle h, const char* n, int i, void** v) {
    auto it = P(h)->m.find(n); if (it == P(h)->m.end() || (int)it->second.p.size() <= i) return kOfxStatErrUnknown;
    *v = it->second.p[i]; return kOfxStatOK; }
static OfxStatus getSN(OfxPropertySetHandle h, const char* n, int c, char** v) { for (int i = 0; i < c; ++i) if (getS(h, n, i, v + i)) return kOfxStatErrUnknown; return kOfxStatOK; }
static OfxStatus getIN(OfxPropertySetHandle h, const char* n, int c, int* v) { for (int i = 0; i < c; ++i) if (getI(h, n, i, v + i)) return kOfxStatErrUnknown; return kOfxStatOK; }
static OfxStatus getDN(OfxPropertySetHandle h, const char* n, int c, double* v) { for (int i = 0; i < c; ++i) if (getD(h, n, i, v + i)) return kOfxStatErrUnknown; return kOfxStatOK; }
static OfxStatus getPN(OfxPropertySetHandle h, const char* n, int c, void** v) { for (int i = 0; i < c; ++i) if (getP(h, n, i, v + i)) return kOfxStatErrUnknown; return kOfxStatOK; }
static OfxStatus reset(OfxPropertySetHandle h, const char* n) { P(h)->m.erase(n); return kOfxStatOK; }
static OfxStatus dim(OfxPropertySetHandle h, const char* n, int* c) {
    auto& v = P(h)->m[n]; *c = (int)std::max({v.s.size(), v.i.size(), v.d.size(), v.p.size()}); return kOfxStatOK; }
static OfxPropertySuiteV1 gPropSuite = {setP, setS, setD, setI, setPN, setSN, setDN, setIN,
                                        getP, getS, getD, getI, getPN, getSN, getDN, getIN, reset, dim};

// ---- параметри
struct Param { std::string type, name; PropSet* props; };
struct ParamSet { std::map<std::string, Param> params; std::vector<std::string> order; };
static ParamSet gParamSet;
static std::map<std::string, double> gOverride;
static OfxStatus paramDefine(OfxParamSetHandle, const char* type, const char* name, OfxPropertySetHandle* props) {
    Param p{type, name, newPS()}; gParamSet.params[name] = p; gParamSet.order.push_back(name);
    if (props) *props = (OfxPropertySetHandle)p.props; return kOfxStatOK; }
static OfxStatus paramGetHandle(OfxParamSetHandle, const char* name, OfxParamHandle* h, OfxPropertySetHandle* props) {
    auto it = gParamSet.params.find(name); if (it == gParamSet.params.end()) return kOfxStatErrUnknown;
    *h = (OfxParamHandle)&it->second; if (props) *props = (OfxPropertySetHandle)it->second.props; return kOfxStatOK; }
static OfxStatus paramGetValueAtTime(OfxParamHandle h, OfxTime, ...) {
    Param* p = (Param*)h; va_list ap; va_start(ap, h);
    auto ov = gOverride.find(p->name);
    if (p->type == kOfxParamTypeDouble) {
        double d = 0; getD((OfxPropertySetHandle)p->props, kOfxParamPropDefault, 0, &d);
        if (ov != gOverride.end()) d = ov->second; *va_arg(ap, double*) = d;
    } else if (p->type == kOfxParamTypeChoice || p->type == kOfxParamTypeBoolean || p->type == kOfxParamTypeInteger) {
        int i = 0; getI((OfxPropertySetHandle)p->props, kOfxParamPropDefault, 0, &i);
        if (ov != gOverride.end()) i = (int)ov->second; *va_arg(ap, int*) = i;
    } else { va_end(ap); return kOfxStatErrBadHandle; }
    va_end(ap); return kOfxStatOK; }
static std::map<std::string, std::string> gStrings;
static OfxStatus paramSetValue(OfxParamHandle h, ...) {
    Param* p = (Param*)h; va_list ap; va_start(ap, h);
    if (p->type == kOfxParamTypeString) gStrings[p->name] = va_arg(ap, const char*);
    va_end(ap); return kOfxStatOK; }
static OfxParameterSuiteV1 gParamSuite;

// ---- ефект і кліпи
static PropSet gEffectProps, gInstProps;
struct Clip { std::string name; PropSet* props; };
static std::map<std::string, Clip> gClips;
static int W, H; static std::vector<float> gSrc, gDst; static std::string gMode;
static OfxStatus getPropertySet(OfxImageEffectHandle h, OfxPropertySetHandle* ps) { *ps = (OfxPropertySetHandle)h; return kOfxStatOK; }
static OfxStatus getParamSet(OfxImageEffectHandle, OfxParamSetHandle* ps) { *ps = (OfxParamSetHandle)&gParamSet; return kOfxStatOK; }
static OfxStatus clipDefine(OfxImageEffectHandle, const char* name, OfxPropertySetHandle* props) {
    Clip c{name, newPS()}; gClips[name] = c; *props = (OfxPropertySetHandle)c.props; return kOfxStatOK; }
static OfxStatus clipGetHandle(OfxImageEffectHandle, const char* name, OfxImageClipHandle* clip, OfxPropertySetHandle*) {
    auto it = gClips.find(name); if (it == gClips.end()) return kOfxStatErrUnknown; *clip = (OfxImageClipHandle)&it->second; return kOfxStatOK; }
static std::vector<float> gBig;
static OfxStatus clipGetImage(OfxImageClipHandle clip, OfxTime, const OfxRectD*, OfxPropertySetHandle* img) {
    Clip* c = (Clip*)clip; PropSet* ps = newPS(); auto h = (OfxPropertySetHandle)ps;
    bool out = c->name == kOfxImageEffectOutputClipName;
    std::vector<float>& buf = out ? gDst : gSrc;
    int bounds[4] = {0, 0, W, H}; void* data = buf.data(); int rb = W * 16;
    if (gMode == "flip") { data = buf.data() + (size_t)(H - 1) * W * 4; rb = -W * 16; }
    if (gMode == "bigsrc" && !out) {   // джерело з полями по 8 пікселів
        int M = 8, BW = W + 2 * M, BH = H + 2 * M; gBig.assign((size_t)BW * BH * 4, 0.5f);
        for (int y = 0; y < H; ++y) memcpy(&gBig[((size_t)(y + M) * BW + M) * 4], &gSrc[(size_t)y * W * 4], W * 16);
        bounds[0] = -M; bounds[1] = -M; bounds[2] = W + M; bounds[3] = H + M; data = gBig.data(); rb = BW * 16;
    }
    setP(h, kOfxImagePropData, 0, data); setI(h, kOfxImagePropRowBytes, 0, rb); setIN(h, kOfxImagePropBounds, 4, bounds);
    setS(h, kOfxImageEffectPropPixelDepth, 0, kOfxBitDepthFloat); setS(h, kOfxImageEffectPropComponents, 0, kOfxImageComponentRGBA);
    *img = h; return kOfxStatOK; }
static OfxStatus clipReleaseImage(OfxPropertySetHandle) { return kOfxStatOK; }
static OfxImageEffectSuiteV1 gEffSuite;

static const void* fetchSuite(OfxPropertySetHandle, const char* name, int ver) {
    if (!strcmp(name, kOfxPropertySuite) && ver == 1) return &gPropSuite;
    if (!strcmp(name, kOfxParameterSuite) && ver == 1) return &gParamSuite;
    if (!strcmp(name, kOfxImageEffectSuite) && ver == 1) return &gEffSuite;
    return nullptr; }

int main(int argc, char** argv) {
    if (argc < 6) { fprintf(stderr, "usage\n"); return 2; }
    W = atoi(argv[2]); H = atoi(argv[3]); gMode = argc > 6 ? argv[6] : "normal";
    for (int i = 7; i < argc; ++i) { const char* e = strchr(argv[i], '='); gOverride[std::string(argv[i], (size_t)(e - argv[i]))] = atof(e + 1); }
    gSrc.resize((size_t)W * H * 4); gDst.assign((size_t)W * H * 4, -1.0f);
    FILE* f = fopen(argv[4], "rb"); if (fread(gSrc.data(), 4, gSrc.size(), f) != gSrc.size()) return 3; fclose(f);
    memset(&gParamSuite, 0, sizeof gParamSuite); gParamSuite.paramDefine = paramDefine;
    gParamSuite.paramGetHandle = paramGetHandle; gParamSuite.paramGetValueAtTime = paramGetValueAtTime;
    gParamSuite.paramSetValue = paramSetValue;
    memset(&gEffSuite, 0, sizeof gEffSuite); gEffSuite.getPropertySet = getPropertySet; gEffSuite.getParamSet = getParamSet;
    gEffSuite.clipDefine = clipDefine; gEffSuite.clipGetHandle = clipGetHandle; gEffSuite.clipGetImage = clipGetImage;
    gEffSuite.clipReleaseImage = clipReleaseImage;

    void* lib = dlopen(argv[1], RTLD_NOW); if (!lib) { fprintf(stderr, "%s\n", dlerror()); return 4; }
    auto num = (int (*)())dlsym(lib, "OfxGetNumberOfPlugins"); auto get = (OfxPlugin * (*)(int)) dlsym(lib, "OfxGetPlugin");
    if (!num || !get || num() != 1) { fprintf(stderr, "bad exports\n"); return 5; }
    OfxPlugin* pl = get(0);
    printf("plugin: %s v%d.%d api=%s\n", pl->pluginIdentifier, pl->pluginVersionMajor, pl->pluginVersionMinor, pl->pluginApi);
    static PropSet hostProps; static OfxHost host{(OfxPropertySetHandle)&hostProps, fetchSuite};
    pl->setHost(&host);
    auto eff = (OfxImageEffectHandle)&gEffectProps;
    auto run = [&](const char* a, OfxImageEffectHandle hdl, OfxPropertySetHandle in) {
        OfxStatus st = pl->mainEntry(a, hdl, in, nullptr); printf("%-40s -> %d\n", a, st); return st; };
    if (run(kOfxActionLoad, nullptr, nullptr)) return 6;
    if (run(kOfxActionDescribe, eff, nullptr)) return 7;
    char* lab = nullptr; getS((OfxPropertySetHandle)&gEffectProps, kOfxPropLabel, 0, &lab);
    char* grp = nullptr; getS((OfxPropertySetHandle)&gEffectProps, kOfxImageEffectPluginPropGrouping, 0, &grp);
    printf("label=%s grouping=%s\n", lab, grp);
    PropSet ctx; setS((OfxPropertySetHandle)&ctx, kOfxImageEffectPropContext, 0, kOfxImageEffectContextFilter);
    if (run(kOfxImageEffectActionDescribeInContext, eff, (OfxPropertySetHandle)&ctx)) return 8;
    printf("clips:"); for (auto& c : gClips) printf(" %s", c.first.c_str()); printf("\nparams (%zu):", gParamSet.order.size());
    for (auto& n : gParamSet.order) { char* l = nullptr; getS((OfxPropertySetHandle)gParamSet.params[n].props, kOfxPropLabel, 0, &l); printf(" [%s|%s]", n.c_str(), l); }
    printf("\n");
    auto inst = (OfxImageEffectHandle)&gInstProps;
    if (run(kOfxActionCreateInstance, inst, nullptr)) return 9;
    PropSet ra; setD((OfxPropertySetHandle)&ra, kOfxPropTime, 0, 12.0);
    int win[4] = {0, 0, W, H}; setIN((OfxPropertySetHandle)&ra, kOfxImageEffectPropRenderWindow, 4, win);
    {
        PropSet ia, io; setD((OfxPropertySetHandle)&ia, kOfxPropTime, 0, 12.0);
        OfxStatus st = pl->mainEntry(kOfxImageEffectActionIsIdentity, inst, (OfxPropertySetHandle)&ia, (OfxPropertySetHandle)&io);
        char* nm = nullptr; getS((OfxPropertySetHandle)&io, kOfxPropName, 0, &nm);
        printf("isIdentity -> %d %s\n", st, st == kOfxStatOK && nm ? nm : "(render)");
    }
    if (run(kOfxImageEffectActionRender, inst, (OfxPropertySetHandle)&ra)) return 10;
    for (auto& kv : gStrings) printf("string %s = %s\n", kv.first.c_str(), kv.second.c_str());
    run(kOfxActionDestroyInstance, inst, nullptr); run(kOfxActionUnload, nullptr, nullptr);
    f = fopen(argv[5], "wb"); fwrite(gDst.data(), 4, gDst.size(), f); fclose(f);
    return 0;
}
