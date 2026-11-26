// Svit Film — OpenFX-плагін для DaVinci Resolve (Effects → OpenFX → Svit → Svit Film).
// Обгортка над svitfilm_core.h: опис ефекту, повзунки й обробка кадру.
#include <cstring>
#include <string>
#include <vector>

#include "ofxCore.h"
#include "ofxImageEffect.h"
#include "ofxParam.h"
#include "ofxProperty.h"
#include "svitfilm_core.h"

#if defined(_WIN32)
#define SVIT_EXPORT extern "C" __declspec(dllexport)
#else
#define SVIT_EXPORT extern "C" __attribute__((visibility("default")))
#endif

namespace {

OfxHost* gHost = nullptr;
const OfxImageEffectSuiteV1* gEffect = nullptr;
const OfxPropertySuiteV1* gProp = nullptr;
const OfxParameterSuiteV1* gParam = nullptr;

void setHost(OfxHost* h) { gHost = h; }

OfxStatus onLoad() {
    if (!gHost) return kOfxStatErrMissingHostFeature;
    gEffect = (const OfxImageEffectSuiteV1*)gHost->fetchSuite(gHost->host, kOfxImageEffectSuite, 1);
    gProp = (const OfxPropertySuiteV1*)gHost->fetchSuite(gHost->host, kOfxPropertySuite, 1);
    gParam = (const OfxParameterSuiteV1*)gHost->fetchSuite(gHost->host, kOfxParameterSuite, 1);
    return (gEffect && gProp && gParam) ? kOfxStatOK : kOfxStatErrMissingHostFeature;
}

OfxStatus describe(OfxImageEffectHandle effect) {
    OfxPropertySetHandle p;
    gEffect->getPropertySet(effect, &p);
    gProp->propSetString(p, kOfxPropLabel, 0, "Svit Film");
    gProp->propSetString(p, kOfxPropShortLabel, 0, "Svit Film");
    gProp->propSetString(p, kOfxPropLongLabel, 0, "Svit Film — film emulation");
    gProp->propSetString(p, kOfxPropPluginDescription, 0,
                         "Film emulation by SadSvit / Svit Editor: film looks, exposure, halation, bloom, grain, "
                         "vignette and gate weave.");
    gProp->propSetString(p, kOfxImageEffectPluginPropGrouping, 0, "Svit");
    gProp->propSetString(p, kOfxImageEffectPropSupportedContexts, 0, kOfxImageEffectContextFilter);
    gProp->propSetString(p, kOfxImageEffectPropSupportedContexts, 1, kOfxImageEffectContextGeneral);
    gProp->propSetString(p, kOfxImageEffectPropSupportedPixelDepths, 0, kOfxBitDepthFloat);
    gProp->propSetInt(p, kOfxImageEffectPropSupportsTiles, 0, 0);
    gProp->propSetInt(p, kOfxImageEffectPropSupportsMultiResolution, 0, 0);
    gProp->propSetInt(p, kOfxImageEffectPropTemporalClipAccess, 0, 0);
    gProp->propSetInt(p, kOfxImageEffectPluginPropHostFrameThreading, 0, 0);   // потоки — наші
    gProp->propSetString(p, kOfxImageEffectPluginRenderThreadSafety, 0, kOfxImageEffectRenderFullySafe);
    return kOfxStatOK;
}

// ---- параметри
OfxPropertySetHandle defineGroup(OfxParamSetHandle ps, const char* name, const char* label, bool open = true) {
    OfxPropertySetHandle pp;
    gParam->paramDefine(ps, kOfxParamTypeGroup, name, &pp);
    gProp->propSetString(pp, kOfxPropLabel, 0, label);
    gProp->propSetInt(pp, kOfxParamPropGroupOpen, 0, open ? 1 : 0);
    return pp;
}

void defineDouble(OfxParamSetHandle ps, const char* name, const char* label, double def, double mn, double mx,
                  const char* parent, const char* hint) {
    OfxPropertySetHandle pp;
    gParam->paramDefine(ps, kOfxParamTypeDouble, name, &pp);
    gProp->propSetString(pp, kOfxPropLabel, 0, label);
    gProp->propSetString(pp, kOfxParamPropHint, 0, hint);
    gProp->propSetString(pp, kOfxParamPropDoubleType, 0, kOfxParamDoubleTypeScale);
    gProp->propSetDouble(pp, kOfxParamPropDefault, 0, def);
    gProp->propSetDouble(pp, kOfxParamPropMin, 0, mn);
    gProp->propSetDouble(pp, kOfxParamPropMax, 0, mx);
    gProp->propSetDouble(pp, kOfxParamPropDisplayMin, 0, mn);
    gProp->propSetDouble(pp, kOfxParamPropDisplayMax, 0, mx);
    gProp->propSetDouble(pp, kOfxParamPropIncrement, 0, 0.01);
    gProp->propSetInt(pp, kOfxParamPropDigits, 0, 2);
    gProp->propSetInt(pp, kOfxParamPropAnimates, 0, 1);
    if (parent) gProp->propSetString(pp, kOfxParamPropParent, 0, parent);
}

void defineChoice(OfxParamSetHandle ps, const char* name, const char* label, const char* const* opts, int n,
                  int def, const char* parent, const char* hint) {
    OfxPropertySetHandle pp;
    gParam->paramDefine(ps, kOfxParamTypeChoice, name, &pp);
    gProp->propSetString(pp, kOfxPropLabel, 0, label);
    gProp->propSetString(pp, kOfxParamPropHint, 0, hint);
    for (int i = 0; i < n; ++i) gProp->propSetString(pp, kOfxParamPropChoiceOption, i, opts[i]);
    gProp->propSetInt(pp, kOfxParamPropDefault, 0, def);
    gProp->propSetInt(pp, kOfxParamPropAnimates, 0, 0);
    if (parent) gProp->propSetString(pp, kOfxParamPropParent, 0, parent);
}

void defineBool(OfxParamSetHandle ps, const char* name, const char* label, int def, const char* parent,
                const char* hint) {
    OfxPropertySetHandle pp;
    gParam->paramDefine(ps, kOfxParamTypeBoolean, name, &pp);
    gProp->propSetString(pp, kOfxPropLabel, 0, label);
    gProp->propSetString(pp, kOfxParamPropHint, 0, hint);
    gProp->propSetInt(pp, kOfxParamPropDefault, 0, def);
    gProp->propSetInt(pp, kOfxParamPropAnimates, 0, 0);
    if (parent) gProp->propSetString(pp, kOfxParamPropParent, 0, parent);
}

OfxStatus describeInContext(OfxImageEffectHandle effect, OfxPropertySetHandle /*inArgs*/) {
    OfxPropertySetHandle cp;
    gEffect->clipDefine(effect, kOfxImageEffectSimpleSourceClipName, &cp);
    gProp->propSetString(cp, kOfxImageEffectPropSupportedComponents, 0, kOfxImageComponentRGBA);
    gProp->propSetInt(cp, kOfxImageClipPropIsMask, 0, 0);
    gProp->propSetInt(cp, kOfxImageEffectPropSupportsTiles, 0, 0);
    gEffect->clipDefine(effect, kOfxImageEffectOutputClipName, &cp);
    gProp->propSetString(cp, kOfxImageEffectPropSupportedComponents, 0, kOfxImageComponentRGBA);
    gProp->propSetInt(cp, kOfxImageEffectPropSupportsTiles, 0, 0);

    OfxParamSetHandle ps;
    gEffect->getParamSet(effect, &ps);

    using namespace svitfilm;
    defineChoice(ps, "input", "Input", kInputNames, kNumInputs, IN_REC709, nullptr,
                 "What comes into this node: normal video (Rec709) or camera log.");
    defineChoice(ps, "look", "Film", kLookNames, kNumLooks, L_WARM, nullptr, "Film stock look.");

    defineGroup(ps, "gExposure", "Exposure & Colour");
    defineDouble(ps, "exposure", "Exposure", 0.0, -4.0, 4.0, "gExposure", "Exposure in stops, before the film.");
    defineDouble(ps, "contrast", "Film Contrast", 1.0, 0.5, 1.6, "gExposure", "Film contrast.");
    defineDouble(ps, "saturation", "Saturation", 1.0, 0.0, 2.0, "gExposure", "Colour saturation.");
    defineDouble(ps, "temp", "Temperature", 0.0, -1.0, 1.0, "gExposure", "Warmer / cooler.");
    defineDouble(ps, "tint", "Tint", 0.0, -1.0, 1.0, "gExposure", "Greener / more magenta.");
    defineDouble(ps, "fade", "Fade", 0.0, 0.0, 1.0, "gExposure", "Faded print: lifted blacks.");

    defineGroup(ps, "gLight", "Halation & Bloom");
    defineDouble(ps, "halation", "Halation", 0.5, 0.0, 2.0, "gLight", "Red glow around bright lights.");
    defineDouble(ps, "halSize", "Halation Size", 1.0, 0.3, 3.0, "gLight", "Width of the halation glow.");
    defineDouble(ps, "bloom", "Bloom", 0.2, 0.0, 2.0, "gLight", "Soft glow of bright areas.");

    defineGroup(ps, "gGrain", "Grain");
    defineDouble(ps, "grain", "Grain", 0.5, 0.0, 2.0, "gGrain", "Film grain, strongest in midtones.");
    defineDouble(ps, "grainSize", "Grain Size", 1.0, 0.5, 3.0, "gGrain", "Size of the grain.");
    defineDouble(ps, "grainColour", "Grain Colour", 0.3, 0.0, 1.0, "gGrain", "0 = luminance grain only.");
    defineBool(ps, "freezeGrain", "Freeze Grain", 0, "gGrain", "Keep the same grain on every frame.");

    defineGroup(ps, "gCamera", "Camera");
    defineDouble(ps, "vignette", "Vignette", 0.25, 0.0, 1.0, "gCamera", "Darker corners.");
    defineDouble(ps, "weave", "Gate Weave", 0.0, 0.0, 1.0, "gCamera", "Subtle frame jitter like a projector.");
    return kOfxStatOK;
}

// ---- обробка
double getD(OfxImageEffectHandle inst, const char* name, OfxTime t) {
    OfxParamSetHandle ps; OfxParamHandle h; double v = 0;
    gEffect->getParamSet(inst, &ps);
    if (gParam->paramGetHandle(ps, name, &h, nullptr) == kOfxStatOK) gParam->paramGetValueAtTime(h, t, &v);
    return v;
}
int getI(OfxImageEffectHandle inst, const char* name, OfxTime t) {
    OfxParamSetHandle ps; OfxParamHandle h; int v = 0;
    gEffect->getParamSet(inst, &ps);
    if (gParam->paramGetHandle(ps, name, &h, nullptr) == kOfxStatOK) gParam->paramGetValueAtTime(h, t, &v);
    return v;
}

struct Img {
    OfxPropertySetHandle h = nullptr;
    void* data = nullptr; int rowBytes = 0; OfxRectI b{0, 0, 0, 0};
    std::string depth, comps;
    bool fetch(OfxImageClipHandle clip, OfxTime t) {
        if (gEffect->clipGetImage(clip, t, nullptr, &h) != kOfxStatOK || !h) return false;
        gProp->propGetPointer(h, kOfxImagePropData, 0, &data);
        gProp->propGetInt(h, kOfxImagePropRowBytes, 0, &rowBytes);
        gProp->propGetIntN(h, kOfxImagePropBounds, 4, &b.x1);
        char* s = nullptr;
        gProp->propGetString(h, kOfxImageEffectPropPixelDepth, 0, &s); depth = s ? s : "";
        gProp->propGetString(h, kOfxImageEffectPropComponents, 0, &s); comps = s ? s : "";
        return data != nullptr;
    }
    ~Img() { if (h) gEffect->clipReleaseImage(h); }
    const float* px(int x, int y) const { return (const float*)((const char*)data + (std::ptrdiff_t)(y - b.y1) * rowBytes) + (x - b.x1) * 4; }
    float* pxw(int x, int y) { return (float*)((char*)data + (std::ptrdiff_t)(y - b.y1) * rowBytes) + (x - b.x1) * 4; }
};

OfxStatus render(OfxImageEffectHandle inst, OfxPropertySetHandle inArgs) {
    OfxTime t = 0;
    gProp->propGetDouble(inArgs, kOfxPropTime, 0, &t);
    OfxImageClipHandle srcClip, dstClip;
    gEffect->clipGetHandle(inst, kOfxImageEffectSimpleSourceClipName, &srcClip, nullptr);
    gEffect->clipGetHandle(inst, kOfxImageEffectOutputClipName, &dstClip, nullptr);
    Img dst, src;
    if (!dst.fetch(dstClip, t)) return kOfxStatFailed;
    if (!src.fetch(srcClip, t)) return kOfxStatFailed;
    if (dst.depth != kOfxBitDepthFloat || src.depth != kOfxBitDepthFloat ||
        dst.comps != kOfxImageComponentRGBA || src.comps != kOfxImageComponentRGBA)
        return kOfxStatErrImageFormat;

    svitfilm::Params p;
    p.input = getI(inst, "input", t);
    p.look = getI(inst, "look", t);
    p.exposure = getD(inst, "exposure", t);
    p.contrast = getD(inst, "contrast", t);
    p.saturation = getD(inst, "saturation", t);
    p.temp = getD(inst, "temp", t);
    p.tint = getD(inst, "tint", t);
    p.fade = getD(inst, "fade", t);
    p.halation = getD(inst, "halation", t);
    p.halSize = getD(inst, "halSize", t);
    p.bloom = getD(inst, "bloom", t);
    p.grain = getD(inst, "grain", t);
    p.grainSize = getD(inst, "grainSize", t);
    p.grainColour = getD(inst, "grainColour", t);
    p.freezeGrain = getI(inst, "freezeGrain", t) != 0;
    p.vignette = getD(inst, "vignette", t);
    p.weave = getD(inst, "weave", t);
    p.frame = t;

    const int w = dst.b.x2 - dst.b.x1, h = dst.b.y2 - dst.b.y1;
    if (w <= 0 || h <= 0) return kOfxStatOK;

    // джерело в розмір кадру результату (якщо межі однакові — без копії)
    std::vector<float> tmp;
    const float* sp; std::ptrdiff_t sstride;
    bool same = src.b.x1 == dst.b.x1 && src.b.y1 == dst.b.y1 && src.b.x2 == dst.b.x2 && src.b.y2 == dst.b.y2 &&
                src.rowBytes % 4 == 0;
    if (same) {
        sp = (const float*)src.data; sstride = src.rowBytes / 4;
    } else {
        tmp.assign((size_t)w * h * 4, 0.0f);
        for (int y = 0; y < h; ++y)
            for (int x = 0; x < w; ++x) {
                int sx = std::clamp(dst.b.x1 + x, src.b.x1, src.b.x2 - 1), sy = std::clamp(dst.b.y1 + y, src.b.y1, src.b.y2 - 1);
                std::memcpy(&tmp[((size_t)y * w + x) * 4], src.px(sx, sy), 4 * sizeof(float));
            }
        sp = tmp.data(); sstride = (std::ptrdiff_t)w * 4;
    }
    if (dst.rowBytes % 4 != 0) return kOfxStatErrImageFormat;
    svitfilm::render(sp, sstride, (float*)dst.data, dst.rowBytes / 4, w, h, p);
    return kOfxStatOK;
}

OfxStatus mainEntry(const char* action, const void* handle, OfxPropertySetHandle inArgs, OfxPropertySetHandle) {
    auto eff = (OfxImageEffectHandle)handle;
    try {
        if (!std::strcmp(action, kOfxActionLoad)) return onLoad();
        if (!std::strcmp(action, kOfxActionDescribe)) return describe(eff);
        if (!std::strcmp(action, kOfxImageEffectActionDescribeInContext)) return describeInContext(eff, inArgs);
        if (!std::strcmp(action, kOfxImageEffectActionRender)) return render(eff, inArgs);
        if (!std::strcmp(action, kOfxActionUnload) || !std::strcmp(action, kOfxActionCreateInstance) ||
            !std::strcmp(action, kOfxActionDestroyInstance))
            return kOfxStatOK;
    } catch (...) {
        return kOfxStatFailed;
    }
    return kOfxStatReplyDefault;
}

OfxPlugin gPlugin = {kOfxImageEffectPluginApi, 1, "com.sadsvit.SvitFilm", 1, 0, setHost, mainEntry};

}  // namespace

SVIT_EXPORT int OfxGetNumberOfPlugins(void) { return 1; }
SVIT_EXPORT OfxPlugin* OfxGetPlugin(int nth) { return nth == 0 ? &gPlugin : nullptr; }
