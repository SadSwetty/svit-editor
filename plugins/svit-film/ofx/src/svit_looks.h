// Svit Looks — 30 готових образів. Кожен образ: спершу всі «образні» параметри скидаються до
// значень за замовчуванням, потім застосовуються його власні. Після вибору все можна докрутити вручну.
#pragma once
#include <algorithm>
#include <cstring>
#include <vector>

#include "svitfilm_core.h"

namespace svitfilm {

// таблиця полів: ім'я параметра OFX → поле Params (для образів і тестів)
struct Field { const char* name; double Params::*d; int Params::*i; bool Params::*b; };
// межі повзунків (як в OFX) — щоб «Look Amount» не виводив значення за них
inline void fieldRange(const char* n, double& lo, double& hi) {
    struct R { const char* n; double lo, hi; };
    static const R r[] = {
        {"exposure", -4, 4}, {"blacks", -1, 1}, {"whites", -1, 1}, {"temp", -1, 1}, {"tint", -1, 1}, {"pushPull", -2, 3},
        {"contrastBoost", -100, 100}, {"gammaCorr", -100, 100}, {"colorSep", 0, 200}, {"colorBoost", -100, 100},
        {"impact", 0, 100}, {"compWhite", 0, 100}, {"tonalRange", 0, 100}, {"colorDensity", 0, 100},
        {"printExposure", -2, 2}, {"lightR", -12, 12}, {"lightG", -12, 12}, {"lightB", -12, 12},
        {"srcLimiter", 0, 100}, {"bgGain", 0, 100}, {"smoothness", 0, 100}, {"localDiff", 0, 100}, {"globalDiff", 0, 100},
        {"amplify", 0, 100}, {"hue", 0, 100}, {"halImpact", 0, 100}, {"bloom", 0, 2},
        {"grainSize", 1, 40}, {"grainAmount", 0, 100}, {"filmRes", 0, 100}, {"gShadows", 0, 100}, {"gMid", 0, 100},
        {"gHigh", 0, 100}, {"chroma", 0, 100}, {"vignette", 0, 1}, {"weave", 0, 1}, {"flicker", 0, 1}, {"age", 0, 30},
        {"leak", 0, 2}, {"leakHue", 0, 100}, {"leakSpeed", 0, 1}, {"cross", 0, 100}, {"blackPoint", -10, 20},
        {"whitePoint", 50, 150}, {"mix", 0, 100}};
    lo = -1e9; hi = 1e9;
    for (auto& x : r) if (!std::strcmp(x.n, n)) { lo = x.lo; hi = x.hi; return; }
}
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
        {"mix", &Params::mix, nullptr, nullptr},
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
        // ---- 2.6: насичені
        {"Ivana Kupala Fire", "Velvia by the bonfire: burning reds, glowing sparks.",
         {{"stock", 16}, {"devOn", 1}, {"colorBoost", 22}, {"temp", 0.2}, {"bloom", 0.5}, {"halProfile", 6}, {"amplify", 75}, {"grainProfile", 8}}},
        {"Odesa Sunburn '03", "Ektar on the beach at noon: hot, saturated, bright.",
         {{"stock", 9}, {"temp", 0.3}, {"lightB", 3}, {"devOn", 1}, {"colorBoost", 26}, {"compOn", 1}, {"impact", 50}, {"grainProfile", 8}}},
        {"Lviv Candy Shop", "Ektar on 2393: sweets-shop colour, glossy and dense.",
         {{"stock", 9}, {"print", 1}, {"devOn", 1}, {"colorBoost", 30}, {"gammaCorr", 15}, {"compOn", 1}, {"colorDensity", 55}}},
        {"Disco Polo '97", "Superia cross-processed under coloured lights.",
         {{"stock", 12}, {"cross", 40}, {"devOn", 1}, {"colorBoost", 22}, {"bloom", 0.5}, {"leak", 0.2}, {"grainProfile", 9}}},
        {"Hutsul Embroidery", "Kodachrome with extra layer separation: reds and blacks like vyshyvanka thread.",
         {{"stock", 15}, {"devOn", 1}, {"colorSep", 140}, {"colorBoost", 22}, {"contrastBoost", 12}, {"grainProfile", 7}}},
        {"Kyiv Neon '04", "CineStill at night: teal shadows, red halos on signs.",
         {{"stock", 13}, {"devOn", 1}, {"colorBoost", 26}, {"lightR", 3}, {"lightB", -3}, {"amplify", 85}, {"grainProfile", 9}}},
        {"Black Sea Pop", "Velvia blues: deep sea, bright skin of summer.",
         {{"stock", 16}, {"temp", -0.1}, {"devOn", 1}, {"colorBoost", 28}, {"whites", 0.2}, {"grainProfile", 7}}},
        {"Cherry Garden", "Portra 800 pushed toward cherry and magenta.",
         {{"stock", 6}, {"devOn", 1}, {"colorBoost", 24}, {"gammaCorr", 10}, {"tint", 0.15}, {"grainProfile", 8}}},
        {"Acid Summer Fest", "Provia fully cross-processed: festival chaos.",
         {{"stock", 17}, {"cross", 80}, {"devOn", 1}, {"colorBoost", 25}, {"flicker", 0.2}, {"grainProfile", 8}}},
        {"Technicolor Babusya", "Ektar on 2393 with three-strip-like separation.",
         {{"stock", 9}, {"print", 1}, {"devOn", 1}, {"colorSep", 150}, {"colorBoost", 20}, {"contrastBoost", 15}, {"lightG", 1.5}}},
        // ---- мрійливі
        {"Polonyna Dream", "Pro 400H in mountain haze: soft highlights, airy shadows.",
         {{"stock", 11}, {"blacks", 0.4}, {"compOn", 1}, {"impact", 70}, {"bloom", 0.8}, {"devOn", 1}, {"colorBoost", -15}, {"temp", 0.1}}},
        {"Cotton Candy Sky", "Portra 160 in pink and powder blue.",
         {{"stock", 7}, {"tint", 0.2}, {"blacks", 0.3}, {"bloom", 0.6}, {"devOn", 1}, {"gammaCorr", 25}}},
        {"Lullaby Super 8", "Super 8 memory: soft glow, gentle weave, honey leak.",
         {{"stock", 1}, {"grainProfile", 2}, {"halProfile", 1}, {"weave", 0.4}, {"bloom", 0.7}, {"blacks", 0.3}, {"leak", 0.3}, {"leakHue", 70}}},
        {"Lilac Hour", "Pro 400H at dusk: lilac shadows, quiet colour.",
         {{"stock", 11}, {"tint", 0.25}, {"temp", -0.05}, {"bloom", 0.5}, {"devOn", 1}, {"colorBoost", -10}}},
        {"Grandma's Slides", "Ektachrome from a shoebox, twelve years later.",
         {{"stock", 14}, {"age", 12}, {"storage", 1}, {"blacks", 0.25}, {"vignette", 0.4}}},
        {"Honey Haze", "Gold 200 dipped in honey: warm bloom everywhere.",
         {{"stock", 8}, {"temp", 0.35}, {"bloom", 1.0}, {"blacks", 0.3}, {"halProfile", 6}, {"amplify", 60}}},
        {"Sleepy Tram 5am", "Eterna before sunrise: cool, faded, half-asleep.",
         {{"stock", 4}, {"temp", -0.2}, {"blacks", 0.3}, {"devOn", 1}, {"colorBoost", -30}, {"bloom", 0.4}}},
        {"Snow in Vorokhta", "50D in fresh snow: bright, cool, soft.",
         {{"stock", 3}, {"whites", 0.3}, {"temp", -0.15}, {"bloom", 0.6}, {"devOn", 1}, {"colorBoost", -20}, {"blacks", 0.2}}},
        // ---- чорно-білі
        {"Silver Frankivsk", "Tri-X with snap: classic street black and white.",
         {{"stock", 18}, {"devOn", 1}, {"contrastBoost", 20}, {"grainProfile", 9}, {"grainAmount", 45}}},
        {"Kyiv Noir", "HP5 pushed two stops: deep blacks, night streets.",
         {{"stock", 19}, {"pushPull", 2}, {"devOn", 1}, {"contrastBoost", 40}, {"vignette", 0.5}, {"bloom", 0.3}, {"grainProfile", 9}}},
        {"Soft Silver Portrait", "HP5 for faces: gentle midtones, fine glow.",
         {{"stock", 19}, {"devOn", 1}, {"gammaCorr", 15}, {"blacks", 0.2}, {"grainProfile", 8}, {"bloom", 0.4}}},
        {"Carpathian Charcoal", "Tri-X on 16 mm, pushed: heavy, graphic mountains.",
         {{"stock", 18}, {"pushPull", 1}, {"devOn", 1}, {"contrastBoost", 30}, {"grainProfile", 6}, {"halProfile", 3}}},
        {"Old Newsreel '41", "Worn 16 mm newsreel: flicker, weave, dark corners.",
         {{"stock", 18}, {"grainProfile", 6}, {"weave", 0.6}, {"flicker", 0.5}, {"vignette", 0.6}, {"age", 15}}},
        {"Pearl Fog", "HP5 in milky light: lifted blacks, soft whites.",
         {{"stock", 19}, {"blacks", 0.4}, {"whites", -0.2}, {"bloom", 0.8}, {"devOn", 1}, {"contrastBoost", -20}}},
        {"Super 8 B&W Diary", "Tri-X on Super 8: a home diary in grain.",
         {{"stock", 18}, {"grainProfile", 3}, {"halProfile", 1}, {"weave", 0.5}, {"flicker", 0.35}, {"vignette", 0.4}}},
        {"Hard Light Steel", "Tri-X at full contrast: graphic, steel-like.",
         {{"stock", 18}, {"devOn", 1}, {"contrastBoost", 60}, {"blackPoint", 4}, {"grainProfile", 7}}},
        // ---- настрій
        {"Karpaty '98 Roll", "A forgotten Gold roll from a 1998 hike: warm leak, faded, alive.",
         {{"stock", 8}, {"age", 9}, {"leak", 0.35}, {"leakHue", 30}, {"grainProfile", 8}, {"vignette", 0.25}, {"temp", 0.1}, {"weave", 0.2}}},
        {"Marshrutka Window", "Expired Superia through a dirty bus window.",
         {{"stock", 12}, {"age", 6}, {"storage", 2}, {"cross", 20}, {"flicker", 0.15}, {"grainProfile", 6}}},
        {"Wedding Tape '95", "ColorPlus scanned at a mini-lab: soft, slightly sleepy.",
         {{"stock", 10}, {"print", 3}, {"age", 8}, {"devOn", 1}, {"colorBoost", -10}, {"blacks", 0.25}, {"bloom", 0.4}, {"weave", 0.3}}},
        {"Last Roll of Summer", "Portra 400 with the end-of-roll leak and warm glow.",
         {{"stock", 5}, {"leak", 0.5}, {"leakHue", 50}, {"age", 3}, {"bloom", 0.4}, {"temp", 0.15}, {"grainProfile", 8}}},
    };
    return L;
}

// застосувати образ i (0 — нічого) з силою amount (1 = як задумано, 0 = без образу, 2 = подвійно):
// плавні повзунки рухаються від типових значень до значень образу пропорційно amount; сила ефектів
// (зерно, halation) росте від нуля; при amount < 1 результат ще й змішується з нейтральним (Mix).
// Перемикачі й вибори (плівка, друк, формат) не мають «половини» — вони вмикаються, щойно amount > 0.
inline bool applyLook(Params& P, int i, double amount = 1.0) {
    if (i <= 0 || i > (int)looks().size()) return false;
    Params D;
    for (auto& f : lookFields()) setField(P, f, getField(D, f));
    if (amount <= 0) return true;
    P.halOn = true; P.grainOn = true;   // образи — це повна плівка: зерно і halation увімкнені
    Params L = P;
    for (auto& kv : looks()[i - 1].kv) {
        const Field* f = findField(kv.k);
        if (!f) return false;
        setField(L, *f, kv.v);
    }
    static const char* fromZero[] = {"grainAmount", "halImpact"};
    for (auto& f : lookFields()) {
        double d = getField(D, f), v = getField(L, f);
        if (!f.d) { setField(P, f, v); continue; }
        for (auto z : fromZero) if (!std::strcmp(z, f.name)) d = 0;
        double lo, hi; fieldRange(f.name, lo, hi);
        setField(P, f, std::clamp(d + (v - d) * amount, lo, hi));
    }
    if (amount < 1.0) P.mix = 100.0 * amount;
    return true;
}

// «Чистий» стан плагіна: усе вимкнено/на нулі (це типові значення в DaVinci). Образи ж задумані на базі
// Params() — плівка і друк увімкнені.
inline Params neutralParams() {
    Params N; N.filmOn = false; N.printOn = false; return N;
}

// Режим «Apply All Settings» вимкнено: образ працює «під капотом», а повзунки показують лише ВАШІ поправки
// поверх нього (на нулі = рівно образ). Числа додаються до значень образу, перемикачі/вибори, змінені
// з чистого стану, перекривають образ, Mix множиться.
inline Params lookPlusOffsets(const Params& user, int look, double amount) {
    Params R = user;
    Params L;
    if (!applyLook(L, look, amount)) return user;
    const Params N = neutralParams();
    for (auto& f : lookFields()) {
        double u = getField(user, f), n = getField(N, f), l = getField(L, f);
        if (!std::strcmp(f.name, "mix")) { setField(R, f, l * u / 100.0); continue; }
        if (f.d) {
            double lo, hi; fieldRange(f.name, lo, hi);
            setField(R, f, std::clamp(l + (u - n), lo, hi));
        } else {
            setField(R, f, u != n ? u : l);
        }
    }
    return R;
}

// Чи нічого не змінюється (тоді DaVinci просто пропускає кадр — без жодного перерахунку і без втрат)
// ---- Об'єктиви: готові набори для секції Lens (0 — Custom, повзунки як є)
struct LensPreset { const char* name; const char* info; double dist, zoom, ca, blur, swirl, tilt, vig; int frame; double fsize, fsoft, glow; };
inline const std::vector<LensPreset>& lensPresets() {
    static const std::vector<LensPreset> L = {
        {"Helios 44-2 58/2 (swirl)", "Soviet classic wide open: swirly edges, soft glow, gentle falloff.", -4, 100, 25, 55, 85, 0, 40, 0, 100, 20, 30},
        {"Jupiter-9 85/2", "Soft, glowy portrait lens with mild swirl.", 0, 100, 15, 35, 25, 0, 30, 0, 100, 20, 40},
        {"Petzval 85 (strong swirl)", "Sharp centre, wild spinning edges.", 2, 100, 20, 85, 100, 0, 55, 0, 100, 20, 25},
        {"Disposable Camera 30mm", "Plastic lens: barrel bend, colour fringes, dark soft corners.", 22, 100, 55, 60, 10, 0, 60, 0, 100, 20, 15},
        {"Lomo LC-A 32mm", "Famous tunnel vignette and punchy centre.", 12, 100, 20, 35, 10, 0, 85, 0, 100, 20, 10},
        {"Super 8 Zoom", "Home movie camera: soft edges, fringes, rounded gate.", 10, 103, 35, 40, 15, 0, 45, 2, 100, 45, 20},
        {"VX1000 Fisheye (MK1)", "90s skate/rap video fisheye in a 4:3 frame.", 70, 100, 40, 35, 10, 0, 40, 3, 100, 12, 5},
        {"Circular Fisheye 8mm", "Full circle fisheye with black around it.", 55, 100, 35, 30, 10, 0, 30, 1, 100, 4, 5},
        {"Tilt-Shift Miniature", "Sharp band in the middle, blur top and bottom.", 0, 100, 0, 0, 0, 80, 20, 0, 100, 20, 0},
        {"Old Cine Prime", "Vintage cinema glass: slight pincushion, soft corners, rounded gate.", -20, 102, 15, 30, 20, 0, 35, 2, 104, 60, 25},
    };
    return L;
}

inline bool isIdentity(const Params& P) {
    if (lensActive(P)) return false;
    const Params N = neutralParams();
    bool sameSpace = (P.input == IN_REC709 && (P.output == OUT_REC709)) ||
                     (P.input == IN_REC2020 && P.output == OUT_REC2020) ||
                     (P.input == IN_APPLE20 && P.output == OUT_APPLE20);
    if (P.mix <= 0.0 && sameSpace) return true;
    if (!sameSpace) return false;
    for (auto& f : lookFields()) {
        if (!std::strcmp(f.name, "mix")) continue;
        // параметри, які нічого не роблять, поки їхній модуль вимкнений
        if (!P.filmOn && (!std::strcmp(f.name, "stock") || !std::strcmp(f.name, "pushPull"))) continue;
        if (!P.printOn && (!std::strcmp(f.name, "print") || !std::strcmp(f.name, "printExposure") ||
                           !std::strcmp(f.name, "lightR") || !std::strcmp(f.name, "lightG") || !std::strcmp(f.name, "lightB"))) continue;
        if (getField(P, f) != getField(N, f)) {
            // окремі модулі вимкнені — їхні повзунки байдужі
            static const char* dev[] = {"contrastBoost", "gammaCorr", "colorSep", "colorBoost"};
            static const char* comp[] = {"impact", "compWhite", "tonalRange", "colorDensity"};
            static const char* hal[] = {"halProfile", "srcLimiter", "bgGain", "smoothness", "localDiff", "globalDiff", "amplify", "hue", "halImpact"};
            static const char* grain[] = {"grainProfile", "grainSize", "grainAmount", "filmRes", "gShadows", "gMid", "gHigh", "chroma", "filmType", "grainMode"};
            static const char* exp[] = {"blackPoint", "whitePoint"};
            static const char* leak[] = {"leakHue", "leakSpeed", "leakPos"};
            static const char* age[] = {"storage"};
            auto in = [&](const char* const* a, int n) { for (int k = 0; k < n; ++k) if (!std::strcmp(a[k], f.name)) return true; return false; };
            if (!P.devOn && in(dev, 4)) continue;
            if (!P.compOn && in(comp, 4)) continue;
            if (!P.halOn && in(hal, 9)) continue;
            if (!P.grainOn && in(grain, 10)) continue;
            if (!P.expandOn && in(exp, 2)) continue;
            if (P.leak <= 0 && in(leak, 3)) continue;
            if (P.age <= 0 && in(age, 1)) continue;
            if (!std::strcmp(f.name, "expandOn")) continue;   // без плівки/друку розтягувати нічого
            return false;
        }
    }
    return true;
}

}  // namespace svitfilm
