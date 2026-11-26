// Svit Looks — 30 готових образів. Кожен образ: спершу всі «образні» параметри скидаються до
// значень за замовчуванням, потім застосовуються його власні. Після вибору все можна докрутити вручну.
#pragma once
#include <cstring>
#include <vector>

#include "svitfilm_core.h"

namespace svitfilm {

// таблиця полів: ім'я параметра OFX → поле Params (для образів і тестів)
struct Field { const char* name; double Params::*d; int Params::*i; bool Params::*b; };
inline const std::vector<Field>& lookFields() {
    static const std::vector<Field> f = {
        {"exposure", &Params::exposure, nullptr, nullptr}, {"blacks", &Params::blacks, nullptr, nullptr},
        {"whites", &Params::whites, nullptr, nullptr}, {"temp", &Params::temp, nullptr, nullptr},
        {"tint", &Params::tint, nullptr, nullptr},
        {"stock", nullptr, &Params::stock, nullptr}, {"pushPull", &Params::pushPull, nullptr, nullptr},
        {"filmOn", nullptr, nullptr, &Params::filmOn},
        {"devOn", nullptr, nullptr, &Params::devOn}, {"contrastBoost", &Params::contrastBoost, nullptr, nullptr},
        {"gammaCorr", &Params::gammaCorr, nullptr, nullptr}, {"colorSep", &Params::colorSep, nullptr, nullptr},
        {"colorBoost", &Params::colorBoost, nullptr, nullptr},
        {"compOn", nullptr, nullptr, &Params::compOn}, {"impact", &Params::impact, nullptr, nullptr},
        {"compWhite", &Params::compWhite, nullptr, nullptr}, {"tonalRange", &Params::tonalRange, nullptr, nullptr},
        {"colorDensity", &Params::colorDensity, nullptr, nullptr},
        {"printOn", nullptr, nullptr, &Params::printOn}, {"print", nullptr, &Params::print, nullptr},
        {"printExposure", &Params::printExposure, nullptr, nullptr}, {"lightR", &Params::lightR, nullptr, nullptr},
        {"lightG", &Params::lightG, nullptr, nullptr}, {"lightB", &Params::lightB, nullptr, nullptr},
        {"halOn", nullptr, nullptr, &Params::halOn}, {"halProfile", nullptr, &Params::halProfile, nullptr},
        {"srcLimiter", &Params::srcLimiter, nullptr, nullptr}, {"bgGain", &Params::bgGain, nullptr, nullptr},
        {"smoothness", &Params::smoothness, nullptr, nullptr}, {"localDiff", &Params::localDiff, nullptr, nullptr},
        {"globalDiff", &Params::globalDiff, nullptr, nullptr}, {"amplify", &Params::amplify, nullptr, nullptr},
        {"hue", &Params::hue, nullptr, nullptr}, {"halImpact", &Params::halImpact, nullptr, nullptr},
        {"bloom", &Params::bloom, nullptr, nullptr},
        {"grainOn", nullptr, nullptr, &Params::grainOn}, {"grainProfile", nullptr, &Params::grainProfile, nullptr},
        {"grainSize", &Params::grainSize, nullptr, nullptr}, {"grainAmount", &Params::grainAmount, nullptr, nullptr},
        {"filmRes", &Params::filmRes, nullptr, nullptr}, {"gShadows", &Params::gShadows, nullptr, nullptr},
        {"gMid", &Params::gMid, nullptr, nullptr}, {"gHigh", &Params::gHigh, nullptr, nullptr},
        {"chroma", &Params::chroma, nullptr, nullptr}, {"filmType", nullptr, &Params::filmType, nullptr},
        {"grainMode", nullptr, &Params::grainMode, nullptr},
        {"vignette", &Params::vignette, nullptr, nullptr}, {"weave", &Params::weave, nullptr, nullptr},
        {"flicker", &Params::flicker, nullptr, nullptr},
        {"age", &Params::age, nullptr, nullptr}, {"storage", nullptr, &Params::storage, nullptr},
        {"leak", &Params::leak, nullptr, nullptr}, {"leakHue", &Params::leakHue, nullptr, nullptr},
        {"leakSpeed", &Params::leakSpeed, nullptr, nullptr}, {"leakPos", nullptr, &Params::leakPos, nullptr},
        {"cross", &Params::cross, nullptr, nullptr},
        {"expandOn", nullptr, nullptr, &Params::expandOn}, {"blackPoint", &Params::blackPoint, nullptr, nullptr},
        {"whitePoint", &Params::whitePoint, nullptr, nullptr},
    };
    return f;
}
inline const Field* findField(const char* n) {
    for (auto& f : lookFields()) if (!std::strcmp(f.name, n)) return &f;
    return nullptr;
}
inline double getField(const Params& P, const Field& f) {
    return f.d ? P.*(f.d) : f.i ? (double)(P.*(f.i)) : (P.*(f.b) ? 1.0 : 0.0);
}
inline void setField(Params& P, const Field& f, double v) {
    if (f.d) P.*(f.d) = v; else if (f.i) P.*(f.i) = (int)v; else P.*(f.b) = v != 0;
}

struct LookKV { const char* k; double v; };
struct Look { const char* name; const char* info; std::vector<LookKV> kv; };

// Індекси плівок (порядок у profiles_gen.h): 0 500T, 1 250D, 2 200T, 3 50D, 4 Eterna 500T, 5 Portra 400,
// 6 Portra 800, 7 Portra 160, 8 Gold 200, 9 Ektar 100, 10 ColorPlus 200, 11 Pro 400H, 12 Superia 400,
// 13 CineStill 800T, 14 E100, 15 Kodachrome 64, 16 Velvia 50, 17 Provia 100F, 18 Tri-X, 19 HP5.
// Друк: 0 2383, 1 2393, 2 3513DI, 3 Film Scan. Grain: 1+3·формат+ISO (формат 0..3 = 8/16/35/65, ISO 0..2 = 50/250/500).
// Halation: 0 Custom, 1/2 8mm, 3/4 16mm, 5/6 35mm, 7/8 65mm (парні — No Remjet).
inline const std::vector<Look>& looks() {
    static const std::vector<Look> L = {
        {"Svit Classic", "VISION3 250D on 2383: the honest cinema print.", {{"stock", 1}}},
        {"Night Tram", "500T pushed one stop, cool night, 35 mm ISO 500 grain.",
         {{"stock", 0}, {"pushPull", 1}, {"temp", -0.15}, {"grainProfile", 9}, {"halProfile", 5}, {"amplify", 80}}},
        {"Neon Rain", "CineStill 800T: red rings around every sign.",
         {{"stock", 13}, {"grainProfile", 9}, {"amplify", 85}, {"hue", 40}, {"bloom", 0.3}}},
        {"Frankivsk '98", "Expired Gold 200 from a drawer, a soft leak, snapshot vignette.",
         {{"stock", 8}, {"age", 7}, {"storage", 1}, {"grainProfile", 8}, {"vignette", 0.3}, {"leak", 0.25}, {"leakPos", 4}, {"printExposure", 0.1}}},
        {"Karpaty Fog", "Portra 160, compressed highlights, quiet colour, lifted shadows.",
         {{"stock", 7}, {"compOn", 1}, {"impact", 50}, {"blacks", 0.3}, {"devOn", 1}, {"colorBoost", -20}, {"temp", 0.05}, {"bloom", 0.3}}},
        {"Super 8 Summer", "Super 8 250D in the sun: weave, flicker, warm leak.",
         {{"stock", 1}, {"grainProfile", 2}, {"halProfile", 1}, {"weave", 0.5}, {"vignette", 0.45}, {"flicker", 0.3}, {"leak", 0.4}, {"leakHue", 55}, {"temp", 0.15}}},
        {"Home Movie '74", "Kodachrome on Super 8, slightly aged.",
         {{"stock", 15}, {"grainProfile", 1}, {"halProfile", 1}, {"weave", 0.6}, {"vignette", 0.5}, {"flicker", 0.4}, {"age", 4}}},
        {"16mm Doc", "500T on 16 mm, pushed, flat developer: run-and-gun documentary.",
         {{"stock", 0}, {"grainProfile", 6}, {"halProfile", 3}, {"pushPull", 1}, {"devOn", 1}, {"contrastBoost", -10}}},
        {"16mm Indie Day", "250D on 16 mm with a touch more colour.",
         {{"stock", 1}, {"grainProfile", 5}, {"halProfile", 3}, {"devOn", 1}, {"colorBoost", 10}}},
        {"Portra Skin", "Portra 400 on 3513DI: soft skin, gentle midtones.",
         {{"stock", 5}, {"print", 2}, {"devOn", 1}, {"colorBoost", -10}, {"gammaCorr", 10}, {"grainProfile", 8}}},
        {"Ektar Punch", "Ektar 100 on 2393: dense saturated colour, fine grain.",
         {{"stock", 9}, {"print", 1}, {"devOn", 1}, {"colorBoost", 25}, {"contrastBoost", 10}, {"grainProfile", 7}}},
        {"Velvia Mountains", "Velvia 50 slide: deep blues and greens.",
         {{"stock", 16}, {"devOn", 1}, {"colorBoost", 15}, {"grainProfile", 7}}},
        {"Slide Show '72", "Aged Ektachrome projected on the wall.",
         {{"stock", 14}, {"age", 5}, {"vignette", 0.35}, {"blacks", 0.2}, {"weave", 0.3}}},
        {"Kodachrome Memory", "Kodachrome 64: warm reds, fine grain.",
         {{"stock", 15}, {"grainProfile", 7}, {"age", 2}}},
        {"Bleach Bypass", "500T with silver retained: desaturated, hard contrast.",
         {{"stock", 0}, {"devOn", 1}, {"colorBoost", -55}, {"contrastBoost", 40}, {"compOn", 1}, {"colorDensity", 80}, {"print", 1}}},
        {"Cross Process '99", "Provia slide processed as a negative.",
         {{"stock", 17}, {"cross", 85}, {"devOn", 1}, {"colorBoost", 15}, {"grainProfile", 8}}},
        {"Tri-X Street", "Tri-X pushed one stop, gritty grain.",
         {{"stock", 18}, {"pushPull", 1}, {"grainProfile", 9}, {"grainAmount", 50}, {"devOn", 1}, {"contrastBoost", 20}}},
        {"HP5 Concert", "HP5 pushed two stops for a dark stage.",
         {{"stock", 19}, {"pushPull", 2}, {"grainProfile", 9}, {"grainAmount", 60}, {"bloom", 0.4}}},
        {"Expired Superia", "Superia that spent a summer in a hot car.",
         {{"stock", 12}, {"age", 10}, {"storage", 2}, {"grainProfile", 9}}},
        {"Basement Gig", "CineStill pushed two stops on 16 mm: sweat, smoke, red lights.",
         {{"stock", 13}, {"pushPull", 2}, {"grainProfile", 6}, {"halProfile", 4}, {"amplify", 90}, {"bloom", 0.5}, {"temp", -0.1}}},
        {"Golden Hour", "Gold 200 warmed up, glowing highlights.",
         {{"stock", 8}, {"temp", 0.25}, {"halProfile", 6}, {"amplify", 60}, {"bloom", 0.4}, {"lightB", 2}}},
        {"Teal Night", "500T printed cool: teal shadows, warm skin.",
         {{"stock", 0}, {"lightR", 3}, {"lightB", -2}, {"compOn", 1}, {"grainProfile", 9}}},
        {"Pastel Dream", "Pro 400H overexposed look: airy pastels.",
         {{"stock", 11}, {"blacks", 0.35}, {"devOn", 1}, {"colorBoost", -25}, {"gammaCorr", 20}, {"compOn", 1}, {"impact", 40}}},
        {"Faded Print", "Eterna on an old faded print: lifted blacks, soft colour.",
         {{"stock", 4}, {"age", 6}, {"blackPoint", -6}, {"devOn", 1}, {"colorBoost", -20}}},
        {"Eterna Drama", "Eterna 500T on 3513DI: restrained, moody.",
         {{"stock", 4}, {"print", 2}, {"devOn", 1}, {"contrastBoost", 15}, {"colorBoost", -15}}},
        {"Music Video Flash", "50D on 2393: punchy, glowing, clean grain.",
         {{"stock", 3}, {"print", 1}, {"compOn", 1}, {"devOn", 1}, {"colorBoost", 20}, {"bloom", 0.6}, {"halProfile", 6}, {"amplify", 80}}},
        {"Light Leak Roll", "Portra 800 with leaks wandering across the frame.",
         {{"stock", 6}, {"leak", 0.8}, {"leakPos", 4}, {"leakSpeed", 0.6}, {"flicker", 0.2}, {"grainProfile", 9}}},
        {"65mm Epic", "50D on 65 mm and 2393: wide, clean, deep.",
         {{"stock", 3}, {"grainProfile", 10}, {"halProfile", 7}, {"print", 1}}},
        {"Snapshot ColorPlus", "ColorPlus scanned at a mini-lab.",
         {{"stock", 10}, {"print", 3}, {"grainProfile", 8}, {"vignette", 0.2}, {"age", 1}}},
        {"Flat Scan", "250D film scan: flat, for your own grade.",
         {{"stock", 1}, {"print", 3}, {"grainProfile", 8}}},
    };
    return L;
}

// застосувати образ i (0 — нічого) до Params: скинути образні поля до типових, потім значення образу
inline bool applyLook(Params& P, int i) {
    if (i <= 0 || i > (int)looks().size()) return false;
    Params D;
    for (auto& f : lookFields()) setField(P, f, getField(D, f));
    for (auto& kv : looks()[i - 1].kv) {
        const Field* f = findField(kv.k);
        if (!f) return false;
        setField(P, *f, kv.v);
    }
    return true;
}

}  // namespace svitfilm
