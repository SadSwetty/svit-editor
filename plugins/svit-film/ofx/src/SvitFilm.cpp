// Svit Film — OpenFX-плагін для DaVinci Resolve (Effects → OpenFX → Svit → Svit Film).
// Обгортка над svitfilm_core.h: опис ефекту, повзунки й обробка кадру.
#include <cstring>
#include <string>
#include <vector>

#if !defined(_WIN32)
#include <dlfcn.h>
#include <spawn.h>
#include <sys/wait.h>
extern char** environ;
#endif

#include "ofxCore.h"
#include "ofxImageEffect.h"
#include "ofxParam.h"
#include "ofxProperty.h"
#include "svitfilm_core.h"
#include "svit_looks.h"

#ifndef SVIT_VERSION
#define SVIT_VERSION "dev"
#endif

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
                         "Film emulation by SadSvit: negative -> print density pipeline, 20 camera stocks, 3 print stocks, "
                         "halation, bloom, density grain. Stock data are experimental estimates, not measurements.");
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
                  const char* parent, const char* hint, double incr = 0.01, int digits = 2) {
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
    gProp->propSetDouble(pp, kOfxParamPropIncrement, 0, incr);
    gProp->propSetInt(pp, kOfxParamPropDigits, 0, digits);
    gProp->propSetInt(pp, kOfxParamPropAnimates, 0, 1);
    if (parent) gProp->propSetString(pp, kOfxParamPropParent, 0, parent);
}

void defineLabel(OfxParamSetHandle ps, const char* name, const char* label, const char* def, const char* parent) {
    OfxPropertySetHandle pp;
    gParam->paramDefine(ps, kOfxParamTypeString, name, &pp);
    gProp->propSetString(pp, kOfxPropLabel, 0, label);
    gProp->propSetString(pp, kOfxParamPropStringMode, 0, kOfxParamStringIsLabel);
    gProp->propSetString(pp, kOfxParamPropDefault, 0, def);
    gProp->propSetInt(pp, kOfxParamPropAnimates, 0, 0);
    gProp->propSetInt(pp, kOfxParamPropEvaluateOnChange, 0, 0);
    gProp->propSetInt(pp, kOfxParamPropPersistant, 0, 0);
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

void defineButton(OfxParamSetHandle ps, const char* name, const char* label, const char* parent,
                  const char* hint) {
    OfxPropertySetHandle pp;
    gParam->paramDefine(ps, kOfxParamTypePushButton, name, &pp);
    gProp->propSetString(pp, kOfxPropLabel, 0, label);
    gProp->propSetString(pp, kOfxParamPropHint, 0, hint);
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
    std::vector<const char*> stockNames, printNames;
    for (int k = 0; k < kNumStocks; ++k) stockNames.push_back(kStocks[k].name);
    for (int k = 0; k < kNumPrints; ++k) printNames.push_back(kPrints[k].name);
    printNames.push_back("Film Scan (no print)");

    std::vector<std::string> lookNameStore = {"None (manual)"};
    for (auto& l : looks()) lookNameStore.push_back(l.name);
    std::vector<const char*> lookNames;
    for (auto& n : lookNameStore) lookNames.push_back(n.c_str());
    defineGroup(ps, "gLook", "Svit Look");
    defineChoice(ps, "look", "Look", lookNames.data(), (int)lookNames.size(), 0, "gLook",
                 "30 ready looks. Picking one sets the controls below; then tweak anything.");
    defineLabel(ps, "lookInfo", "About", "Pick a look or set everything by hand.", "gLook");

    defineGroup(ps, "gInput", "Input");
    defineChoice(ps, "input", "Source", kInputNames, kNumInputs, IN_REC709, "gInput",
                 "Colour space and gamma of what comes into this node.");

    defineGroup(ps, "gExposure", "Exposure");
    defineDouble(ps, "exposure", "Exposure", 0.0, -4.0, 4.0, "gExposure", "Exposure in stops, before the film.");
    defineDouble(ps, "blacks", "Blacks", 0.0, -1.0, 1.0, "gExposure", "Lift (+) or crush (-) the shadows before the film.");
    defineDouble(ps, "whites", "Whites", 0.0, -1.0, 1.0, "gExposure", "Brighter (+) or darker (-) highlights before the film.");
    defineDouble(ps, "temp", "Temperature", 0.0, -1.0, 1.0, "gExposure", "Warmer / cooler light on the film.");
    defineDouble(ps, "tint", "Tint", 0.0, -1.0, 1.0, "gExposure", "Greener / more magenta light on the film.");

    defineGroup(ps, "gFilm", "Film");
    defineChoice(ps, "stock", "Profile", stockNames.data(), kNumStocks, 1, "gFilm", "Camera film stock.");
    defineDouble(ps, "pushPull", "Push/Pull (Ev)", 0.0, -2.0, 3.0, "gFilm",
                 "Push (+) / pull (-) processing: contrast, fog and grain change; the print is re-timed.", 0.1, 3);
    defineBool(ps, "filmOn", "Enabled", 1, "gFilm", "Off = neutral reference negative.");
    defineLabel(ps, "status", "Profile Status", kStocks[1].status, "gFilm");

    defineGroup(ps, "gDev", "Film Developer", false);
    defineDouble(ps, "contrastBoost", "Contrast Boost", 0.0, -100.0, 100.0, "gDev", "Development contrast (negative gamma).", 1, 1);
    defineDouble(ps, "gammaCorr", "Gamma Correction", 0.0, -100.0, 100.0, "gDev", "Midtone density.", 1, 1);
    defineDouble(ps, "colorSep", "Color Separation", 100.0, 0.0, 200.0, "gDev", "Interlayer (DIR) colour separation of the stock.", 1, 1);
    defineDouble(ps, "colorBoost", "Color Boost", 0.0, -100.0, 100.0, "gDev", "Dye density saturation.", 1, 1);
    defineBool(ps, "devOn", "Enabled", 0, "gDev", "Turn the developer controls on.");

    defineGroup(ps, "gComp", "Film Compression", false);
    defineDouble(ps, "impact", "Impact", 60.0, 0.0, 100.0, "gComp", "Highlight compression strength.", 1, 1);
    defineDouble(ps, "compWhite", "White Point", 100.0, 0.0, 100.0, "gComp", "Where compression starts.", 1, 1);
    defineDouble(ps, "tonalRange", "Tonal Range", 30.0, 0.0, 100.0, "gComp", "How soft the compression is.", 1, 1);
    defineDouble(ps, "colorDensity", "Color Density", 50.0, 0.0, 100.0, "gComp", "Subtractive density: saturated colours get deeper.", 1, 1);
    defineBool(ps, "compOn", "Enabled", 0, "gComp", "Turn film compression on.");

    defineGroup(ps, "gPrint", "Print");
    defineChoice(ps, "print", "Print Film", printNames.data(), (int)printNames.size(), 0, "gPrint",
                 "Print stock the negative is printed on, or a flat film scan.");
    defineDouble(ps, "printExposure", "Print Exposure", 0.0, -2.0, 2.0, "gPrint", "Brighter (+) / darker (-) print.", 0.01, 2);
    defineDouble(ps, "lightR", "Printer Light R", 0.0, -12.0, 12.0, "gPrint", "Printer points: + = more red light = less red.", 0.5, 1);
    defineDouble(ps, "lightG", "Printer Light G", 0.0, -12.0, 12.0, "gPrint", "Printer points: + = more green light = less green.", 0.5, 1);
    defineDouble(ps, "lightB", "Printer Light B", 0.0, -12.0, 12.0, "gPrint", "Printer points: + = more blue light = less blue.", 0.5, 1);
    defineBool(ps, "printOn", "Enabled", 1, "gPrint", "Off = neutral reference print.");

    defineGroup(ps, "gHal", "Halation");
    defineChoice(ps, "halProfile", "Profile", kHalProfileNames, kNumHalProfiles, 0, "gHal",
                 "Film format and anti-halation backing. Custom = 35 mm and the backing of the chosen stock.");
    defineDouble(ps, "srcLimiter", "Source Limiter", 15.0, 0.0, 100.0, "gHal", "How bright a source must be to halate.", 1, 1);
    defineDouble(ps, "bgGain", "Background Gain", 80.0, 0.0, 100.0, "gHal", "Lower = halos only over darker backgrounds.", 1, 1);
    defineDouble(ps, "smoothness", "Smoothness", 50.0, 0.0, 100.0, "gHal", "Scattering in the emulsion: softer halos.", 1, 1);
    defineDouble(ps, "localDiff", "Local Diffusion", 15.0, 0.0, 100.0, "gHal", "Halo radius (effective base thickness).", 1, 1);
    defineDouble(ps, "globalDiff", "Global Diffusion", 25.0, 0.0, 100.0, "gHal", "Wide secondary red glare.", 1, 1);
    defineDouble(ps, "amplify", "Amplify", 70.0, 0.0, 100.0, "gHal", "Re-exposure strength of the red/green layers.", 1, 1);
    defineDouble(ps, "hue", "Hue", 50.0, 0.0, 100.0, "gHal", "0 = pure red, 100 = orange (green layer).", 1, 1);
    defineDouble(ps, "blueComp", "Blue Comp.", 100.0, 0.0, 100.0, "gHal", "Keeps halos visible over blue backgrounds.", 1, 1);
    defineDouble(ps, "halImpact", "Impact", 70.0, 0.0, 100.0, "gHal", "Opacity of the effect.", 1, 1);
    defineBool(ps, "maskMode", "Mask Mode", 0, "gHal", "Show the halation alone.");
    defineBool(ps, "halOn", "Enabled", 1, "gHal", "Turn halation on.");

    defineGroup(ps, "gBloom", "Bloom", false);
    defineDouble(ps, "bloom", "Bloom", 0.0, 0.0, 2.0, "gBloom", "Lens diffusion of bright areas.");

    defineGroup(ps, "gGrain", "Film Grain");
    defineChoice(ps, "grainProfile", "Profile", kGrainProfileNames, kNumGrainProfiles, 0, "gGrain",
                 "Format and speed. Custom = 35 mm, grain of the chosen stock, Size in micrometres.");
    defineDouble(ps, "grainSize", "Size", 12.0, 1.0, 40.0, "gGrain", "Dye cloud size, micrometres (presets: relative to 12).", 0.1, 2);
    defineDouble(ps, "grainAmount", "Amount", 35.0, 0.0, 100.0, "gGrain", "RMS granularity (35 = stock / preset value).", 1, 1);
    defineDouble(ps, "filmRes", "Film Resolution", 75.0, 0.0, 100.0, "gGrain", "Emulsion sharpness (MTF).", 1, 1);
    defineDouble(ps, "gShadows", "Shadows", 30.0, 0.0, 100.0, "gGrain", "Grain in the shadows.", 1, 1);
    defineDouble(ps, "gMid", "Midtones", 55.0, 0.0, 100.0, "gGrain", "Grain in the midtones.", 1, 1);
    defineDouble(ps, "gHigh", "Highlights", 65.0, 0.0, 100.0, "gGrain", "Grain in the highlights.", 1, 1);
    defineDouble(ps, "chroma", "Chroma", 65.0, 0.0, 100.0, "gGrain", "How independent the grain is in each colour layer.", 1, 1);
    defineChoice(ps, "filmType", "Film Type", kFilmTypeNames, 2, 0, "gGrain", "Grain in the negative (printed) or in the positive.");
    defineChoice(ps, "grainMode", "Mode", kGrainModeNames, 2, 0, "gGrain", "Analogue = clumped grain, Digital = clean noise.");
    defineBool(ps, "freezeGrain", "Freeze Grain", 0, "gGrain", "Keep the same grain on every frame.");
    defineBool(ps, "grainOn", "Enabled", 1, "gGrain", "Turn grain on.");

    defineGroup(ps, "gExpired", "Expired Film", false);
    defineDouble(ps, "age", "Age (years)", 0.0, 0.0, 30.0, "gExpired", "How long past its date: fog, colour shift, lost contrast, more grain.", 0.5, 1);
    defineChoice(ps, "storage", "Storage", kStorageNames, 3, 1, "gExpired", "Where the roll was kept.");

    defineGroup(ps, "gLeak", "Light Leak", false);
    defineDouble(ps, "leak", "Amount", 0.0, 0.0, 2.0, "gLeak", "Light leaking onto the film from the edge (exposes before development).");
    defineDouble(ps, "leakHue", "Hue", 40.0, 0.0, 100.0, "gLeak", "Red -> orange -> yellow.", 1, 1);
    defineDouble(ps, "leakSpeed", "Drift", 0.3, 0.0, 1.0, "gLeak", "How fast the leak moves.");
    defineChoice(ps, "leakPos", "Edge", kLeakPosNames, 5, 4, "gLeak", "Where the leak comes from. Random changes every ~2 s.");

    defineGroup(ps, "gLab", "Lab", false);
    defineDouble(ps, "cross", "Cross Process", 0.0, 0.0, 100.0, "gLab", "Slide film in negative chemistry: cyan shadows, yellow highlights.", 1, 1);
    defineDouble(ps, "flicker", "Flicker", 0.0, 0.0, 1.0, "gLab", "Exposure flicker from frame to frame.");

    defineGroup(ps, "gCamera", "Camera", false);
    defineDouble(ps, "vignette", "Vignette", 0.0, 0.0, 1.0, "gCamera", "Darker corners.");
    defineDouble(ps, "weave", "Gate Weave", 0.0, 0.0, 1.0, "gCamera", "Subtle frame jitter like a projector.");

    defineGroup(ps, "gExpand", "Expand");
    defineDouble(ps, "blackPoint", "Black Point", 0.0, -10.0, 20.0, "gExpand", "Output black point.");
    defineDouble(ps, "whitePoint", "White Point", 100.0, 50.0, 150.0, "gExpand", "Output white point.", 0.1, 1);
    defineChoice(ps, "colorMode", "Color Mode", kColorModeNames, kNumColorModes, 0, "gExpand", "Expand RGB or luminance only.");
    defineBool(ps, "expandOn", "Enabled", 1, "gExpand", "Turn expand on.");

    defineGroup(ps, "gOutput", "Output");
    defineChoice(ps, "output", "Output", kOutputNames, kNumOutputs, OUT_REC709, "gOutput", "Display colour space of the result.");
    defineDouble(ps, "mix", "Mix", 100.0, 0.0, 100.0, "gOutput", "Blend with the neutral (no film) rendering.", 1, 1);

    defineGroup(ps, "gAbout", "Svit Film v" SVIT_VERSION, false);
    defineButton(ps, "update", "Update Svit Film", "gAbout", "Check GitHub for a new Svit Film version and install it.");
    return kOfxStatOK;
}

// ---- оновлення: кнопка запускає Contents/Resources/update.sh окремим процесом (DaVinci не чекає)
void launchUpdate() {
#if defined(__APPLE__)
    Dl_info info;
    if (!dladdr((const void*)&launchUpdate, &info) || !info.dli_fname) return;
    std::string bin = info.dli_fname;                       // .../Contents/MacOS/SvitFilm.ofx
    std::string::size_type k = bin.rfind("/MacOS/");
    if (k == std::string::npos) return;
    std::string script = bin.substr(0, k) + "/Resources/update.sh";
    std::string cmd = "/bin/bash '" + script + "' '" SVIT_VERSION "' >/dev/null 2>&1 &";
    char* argv[] = {(char*)"/bin/sh", (char*)"-c", (char*)cmd.c_str(), nullptr};
    pid_t pid;
    if (posix_spawn(&pid, "/bin/sh", nullptr, nullptr, argv, environ) == 0) {
        int st; waitpid(pid, &st, 0);                      // sh одразу виходить, скрипт живе у фоні
    }
#endif
}

int getI(OfxImageEffectHandle inst, const char* name, OfxTime t);

// поле «Profile Status»: показує, що профіль — оцінка, а не виміряні дані
void updateStatus(OfxImageEffectHandle inst) {
    OfxParamSetHandle ps; OfxParamHandle h;
    gEffect->getParamSet(inst, &ps);
    if (gParam->paramGetHandle(ps, "status", &h, nullptr) != kOfxStatOK) return;
    svitfilm::Params p;
    p.stock = getI(inst, "stock", 0); p.filmOn = getI(inst, "filmOn", 0) != 0;
    if (gParam->paramSetValue) gParam->paramSetValue(h, svitfilm::statusText(p));
}

// вибір образу: виставити всі його параметри (спершу типові значення, потім образ)
void applyLookParams(OfxImageEffectHandle inst) {
    if (!gParam->paramSetValue) return;
    int i = getI(inst, "look", 0);
    svitfilm::Params P;
    if (!svitfilm::applyLook(P, i)) return;
    OfxParamSetHandle ps; OfxParamHandle h;
    gEffect->getParamSet(inst, &ps);
    for (auto& f : svitfilm::lookFields()) {
        if (gParam->paramGetHandle(ps, f.name, &h, nullptr) != kOfxStatOK) continue;
        double v = svitfilm::getField(P, f);
        if (f.d) gParam->paramSetValue(h, v); else gParam->paramSetValue(h, (int)v);
    }
    if (gParam->paramGetHandle(ps, "lookInfo", &h, nullptr) == kOfxStatOK)
        gParam->paramSetValue(h, svitfilm::looks()[i - 1].info);
    updateStatus(inst);
}

OfxStatus instanceChanged(OfxImageEffectHandle inst, OfxPropertySetHandle inArgs) {
    char* type = nullptr; char* name = nullptr; char* reason = nullptr;
    gProp->propGetString(inArgs, kOfxPropType, 0, &type);
    gProp->propGetString(inArgs, kOfxPropName, 0, &name);
    gProp->propGetString(inArgs, kOfxPropChangeReason, 0, &reason);
    if (!type || !name || std::strcmp(type, kOfxTypeParameter)) return kOfxStatReplyDefault;
    if (!std::strcmp(name, "update") && (!reason || !std::strcmp(reason, kOfxChangeUserEdited))) launchUpdate();
    if (!std::strcmp(name, "stock") || !std::strcmp(name, "filmOn")) updateStatus(inst);
    if (!std::strcmp(name, "look") && (!reason || !std::strcmp(reason, kOfxChangeUserEdited))) applyLookParams(inst);
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
    p.input = getI(inst, "input", t); p.output = getI(inst, "output", t);
    p.exposure = getD(inst, "exposure", t); p.blacks = getD(inst, "blacks", t); p.whites = getD(inst, "whites", t);
    p.temp = getD(inst, "temp", t); p.tint = getD(inst, "tint", t);
    p.stock = getI(inst, "stock", t); p.pushPull = getD(inst, "pushPull", t); p.filmOn = getI(inst, "filmOn", t) != 0;
    p.contrastBoost = getD(inst, "contrastBoost", t); p.gammaCorr = getD(inst, "gammaCorr", t);
    p.colorSep = getD(inst, "colorSep", t); p.colorBoost = getD(inst, "colorBoost", t); p.devOn = getI(inst, "devOn", t) != 0;
    p.impact = getD(inst, "impact", t); p.compWhite = getD(inst, "compWhite", t); p.tonalRange = getD(inst, "tonalRange", t);
    p.colorDensity = getD(inst, "colorDensity", t); p.compOn = getI(inst, "compOn", t) != 0;
    p.print = getI(inst, "print", t); p.printExposure = getD(inst, "printExposure", t);
    p.lightR = getD(inst, "lightR", t); p.lightG = getD(inst, "lightG", t); p.lightB = getD(inst, "lightB", t);
    p.printOn = getI(inst, "printOn", t) != 0;
    p.halProfile = getI(inst, "halProfile", t); p.srcLimiter = getD(inst, "srcLimiter", t); p.bgGain = getD(inst, "bgGain", t);
    p.smoothness = getD(inst, "smoothness", t); p.localDiff = getD(inst, "localDiff", t); p.globalDiff = getD(inst, "globalDiff", t);
    p.amplify = getD(inst, "amplify", t); p.hue = getD(inst, "hue", t); p.blueComp = getD(inst, "blueComp", t);
    p.halImpact = getD(inst, "halImpact", t); p.maskMode = getI(inst, "maskMode", t) != 0; p.halOn = getI(inst, "halOn", t) != 0;
    p.bloom = getD(inst, "bloom", t);
    p.grainProfile = getI(inst, "grainProfile", t); p.grainSize = getD(inst, "grainSize", t);
    p.grainAmount = getD(inst, "grainAmount", t); p.filmRes = getD(inst, "filmRes", t);
    p.gShadows = getD(inst, "gShadows", t); p.gMid = getD(inst, "gMid", t); p.gHigh = getD(inst, "gHigh", t);
    p.chroma = getD(inst, "chroma", t); p.filmType = getI(inst, "filmType", t); p.grainMode = getI(inst, "grainMode", t);
    p.freezeGrain = getI(inst, "freezeGrain", t) != 0; p.grainOn = getI(inst, "grainOn", t) != 0;
    p.vignette = getD(inst, "vignette", t); p.weave = getD(inst, "weave", t);
    p.blackPoint = getD(inst, "blackPoint", t); p.whitePoint = getD(inst, "whitePoint", t);
    p.colorMode = getI(inst, "colorMode", t); p.expandOn = getI(inst, "expandOn", t) != 0;
    p.age = getD(inst, "age", t); p.storage = getI(inst, "storage", t);
    p.leak = getD(inst, "leak", t); p.leakHue = getD(inst, "leakHue", t); p.leakSpeed = getD(inst, "leakSpeed", t);
    p.leakPos = getI(inst, "leakPos", t); p.cross = getD(inst, "cross", t); p.flicker = getD(inst, "flicker", t);
    p.mix = getD(inst, "mix", t);
    p.frame = t; p.originX = dst.b.x1; p.originY = dst.b.y1;

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
        if (!std::strcmp(action, kOfxActionInstanceChanged)) return instanceChanged(eff, inArgs);
        if (!std::strcmp(action, kOfxActionCreateInstance)) { updateStatus(eff); return kOfxStatOK; }
        if (!std::strcmp(action, kOfxActionUnload) || !std::strcmp(action, kOfxActionDestroyInstance))
            return kOfxStatOK;
    } catch (...) {
        return kOfxStatFailed;
    }
    return kOfxStatReplyDefault;
}

OfxPlugin gPlugin = {kOfxImageEffectPluginApi, 1, "com.sadsvit.SvitFilm", 2, 0, setHost, mainEntry};

}  // namespace

SVIT_EXPORT int OfxGetNumberOfPlugins(void) { return 1; }
SVIT_EXPORT OfxPlugin* OfxGetPlugin(int nth) { return nth == 0 ? &gPlugin : nullptr; }
