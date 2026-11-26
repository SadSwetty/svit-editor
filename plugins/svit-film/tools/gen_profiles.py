#!/usr/bin/env python3
"""Svit Film: перевіряє профілі плівок (profiles/**.json) і генерує з них
  - ofx/src/profiles_gen.h  — дані для плагіна;
  - docs/COVERAGE.md        — матриця покриття: 20 плівок × 12 фізичних полів + плівки друку.

  python3 tools/gen_profiles.py          # перевірити й перегенерувати
  python3 tools/gen_profiles.py --check  # лише перевірити, що згенеровані файли актуальні (для CI)

Правила (див. FILM_EMULATION_MASTER_SPEC.md §3, §6):
  * профіль має статус: reference | experimental | incomplete | verified;
  * verified можливий лише тоді, коли всі обов'язкові поля заповнені й мають джерела;
  * кожне ненульове фізичне поле мусить мати source_id, units, classification;
  * experimental_seeds — це оцінки, вони завжди позначені як estimated і не вважаються вимірами;
  * чорно-біла плівка має один канал, кольорових шарів не вигадуємо.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROF = os.path.join(ROOT, "profiles")
OUT_H = os.path.join(ROOT, "ofx", "src", "profiles_gen.h")
OUT_MD = os.path.join(ROOT, "docs", "COVERAGE.md")

ORDER = ["kodak_vision3_500t", "kodak_vision3_250d", "kodak_vision3_200t", "kodak_vision3_50d", "fuji_eterna_500t",
         "kodak_portra_400", "kodak_portra_800", "kodak_portra_160", "kodak_gold_200", "kodak_ektar_100",
         "kodak_colorplus_200", "fuji_pro_400h", "fuji_superia_xtra_400", "cinestill_800t",
         "kodak_ektachrome_e100", "kodak_kodachrome_64", "fuji_velvia_50", "fuji_provia_100f",
         "kodak_trix_400", "ilford_hp5_plus_400"]
PRINT_ORDER = ["kodak_2383", "kodak_2393", "fuji_3513di"]
REFERENCE = "svit_neutral"
REFERENCE_PRINT = "svit_neutral_print"

PHYS = ["characteristic_curves", "spectral_sensitivity", "dye_density", "base_fog", "exposure_latitude",
        "rms_granularity", "grain_distribution", "mtf", "halation", "interlayer_effects",
        "push_pull_response", "reciprocity_failure"]
PRINT_PHYS = ["characteristic_curves", "spectral_sensitivity", "dye_density", "base_fog", "rms_granularity", "mtf"]
ESSENTIAL = ["characteristic_curves", "spectral_sensitivity", "dye_density", "base_fog"]
STATUS = {"reference", "experimental", "incomplete", "verified"}
CLASSIFICATION = {"measured_published", "digitized", "derived", "fitted", "estimated"}
CLASSES = {"color_negative": 0, "color_reversal": 1, "monochrome_negative": 2}


class Bad(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise Bad(msg)


def check_field(pid, name, v):
    if v is None:
        return
    need(isinstance(v, dict), f"{pid}.{name}: має бути об'єкт або null")
    for k in ("source_id", "units", "classification"):
        need(v.get(k), f"{pid}.{name}: бракує '{k}'")
    need(v["classification"] in CLASSIFICATION, f"{pid}.{name}: невідома classification '{v['classification']}'")
    need("values" in v or "asset" in v, f"{pid}.{name}: потрібні 'values' або 'asset'")


def check(p, path):
    pid = p.get("id")
    need(pid and os.path.basename(path) == pid + ".json", f"{path}: id має збігатися з назвою файлу")
    need(p.get("schema_version") == 1, f"{pid}: schema_version має бути 1")
    need(p.get("status") in STATUS, f"{pid}: status має бути одним з {sorted(STATUS)}")
    need(isinstance(p.get("sources"), list), f"{pid}: sources має бути списком")
    fields = PHYS if p["kind"] == "camera_stock" else PRINT_PHYS
    for f in fields:
        need(f in p, f"{pid}: поле '{f}' має бути явно вказане (null, якщо даних немає)")
        check_field(pid, f, p[f])
    if p["status"] == "verified":
        for f in ESSENTIAL:
            need(p.get(f) is not None, f"{pid}: verified, але немає '{f}'")
        need(p["sources"], f"{pid}: verified без джерел")
    s = p.get("experimental_seeds")
    need(isinstance(s, dict), f"{pid}: немає experimental_seeds")
    need(s.get("classification") == "estimated", f"{pid}: seeds мають бути позначені classification=estimated")
    need(s.get("production_enabled") is False, f"{pid}: seeds не можуть бути production_enabled")
    g = s.get("gamma")
    if p["kind"] == "camera_stock":
        need(p.get("class") in CLASSES, f"{pid}: невідомий class")
        mono = p["class"] == "monochrome_negative"
        need(isinstance(g, list) and len(g) == (1 if mono else 3), f"{pid}: gamma має мати {1 if mono else 3} канал(и)")
        need(len(s["base_fog_density"]) == len(g), f"{pid}: base_fog_density не збігається з кількістю каналів")
        if mono:
            w = s.get("mono_weights")
            need(isinstance(w, list) and len(w) == 3 and abs(sum(w) - 1) < 1e-6, f"{pid}: mono_weights (3, сума 1)")
        else:
            need(len(s.get("balance_log_exposure", [])) == 3, f"{pid}: balance_log_exposure (3)")
        need(s["shoulder_log_exposure"] > s["toe_log_exposure"], f"{pid}: плече має бути вище за п'яту")
        if p["class"] == "color_reversal":
            need(s.get("dmax_density"), f"{pid}: оборотна плівка потребує dmax_density")
    else:
        need(isinstance(g, list) and len(g) == 3 and len(s["base_fog_density"]) == 3, f"{pid}: print gamma/base (3)")
        need(s.get("dmax_density"), f"{pid}: потрібна dmax_density")
    need(all(x > 0 for x in g), f"{pid}: gamma має бути > 0")


def load():
    out = {}
    for sub in ("stocks", "prints"):
        d = os.path.join(PROF, sub)
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".json"):
                path = os.path.join(d, fn)
                p = json.load(open(path, encoding="utf-8"))
                check(p, path)
                out[p["id"]] = p
    for i in ORDER + PRINT_ORDER + [REFERENCE, REFERENCE_PRINT]:
        need(i in out, f"бракує профілю {i}")
    return out


def cf(x):
    t = "%.6g" % x
    if "." not in t and "e" not in t:
        t += ".0"
    return t + "f"


def arr3(v):
    v = list(v) + [v[0]] * (3 - len(v))
    return "{" + ", ".join(cf(x) for x in v) + "}"


def status_text(p):
    s = p["status"]
    have = sum(1 for f in (PHYS if p["kind"] == "camera_stock" else PRINT_PHYS) if p.get(f) is not None)
    total = len(PHYS if p["kind"] == "camera_stock" else PRINT_PHYS)
    if s == "verified":
        return "Verified data (%d/%d fields)" % (have, total)
    return "%s - estimated curves, not measured (%d/%d fields)" % (s.capitalize(), have, total)


def gen_header(P):
    L = ["// Згенеровано tools/gen_profiles.py з profiles/*.json. Не редагувати вручну.",
         "// УВАГА: усі числа тут — experimental_seeds (оцінки), а не виміряні дані плівок.",
         "#pragma once", "namespace svitfilm {", "",
         "struct StockDef { const char* id; const char* name; const char* status; int cls;",
         "  float gamma[3], toe, shoulder, toeW, shW, dmin[3], dmax, colorSep, balance[3], grain, halation, mono[3]; };",
         "struct PrintDef { const char* id; const char* name; const char* status;",
         "  float gamma[3], dmin[3], dmax, toeW, shW; };", ""]

    def stock(p):
        s = p["experimental_seeds"]
        mono = s.get("mono_weights", [0, 0, 0])
        return ('  {"%s", "%s", "%s", %d, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s},' % (
            p["id"], p["name"], status_text(p), CLASSES[p["class"]], arr3(s["gamma"]), cf(s["toe_log_exposure"]),
            cf(s["shoulder_log_exposure"]), cf(s["toe_width"]), cf(s["shoulder_width"]), arr3(s["base_fog_density"]),
            cf(s.get("dmax_density", 0)), cf(s["color_separation"]), arr3(s.get("balance_log_exposure", [0, 0, 0])),
            cf(s["grain_rel"]), cf(s["halation_rel"]), arr3(mono)))

    def prt(p):
        s = p["experimental_seeds"]
        return '  {"%s", "%s", "%s", %s, %s, %s, %s, %s},' % (
            p["id"], p["name"], status_text(p), arr3(s["gamma"]), arr3(s["base_fog_density"]), cf(s["dmax_density"]),
            cf(s["toe_width"]), cf(s["shoulder_width"]))

    L.append("static const StockDef kStocks[] = {")
    L += [stock(P[i]) for i in ORDER]
    L.append("};")
    L.append("static const int kNumStocks = %d;" % len(ORDER))
    L.append("static const StockDef kReferenceStock = " + stock(P[REFERENCE]).strip()[:-1] + ";")
    L.append("")
    L.append("static const PrintDef kPrints[] = {")
    L += [prt(P[i]) for i in PRINT_ORDER]
    L.append("};")
    L.append("static const int kNumPrints = %d;" % len(PRINT_ORDER))
    L.append("static const PrintDef kReferencePrint = " + prt(P[REFERENCE_PRINT]).strip()[:-1] + ";")
    L += ["", "}  // namespace svitfilm", ""]
    return "\n".join(L)


def gen_md(P):
    short = {"characteristic_curves": "Curves", "spectral_sensitivity": "Spectral", "dye_density": "Dyes",
             "base_fog": "Base+fog", "exposure_latitude": "Latitude", "rms_granularity": "RMS gran.",
             "grain_distribution": "Grain PSD", "mtf": "MTF", "halation": "Halation", "interlayer_effects": "Interlayer",
             "push_pull_response": "Push/pull", "reciprocity_failure": "Reciprocity"}

    def cell(v):
        return "—" if v is None else v["classification"]

    L = ["# Svit Film — покриття даних профілів", "",
         "Згенеровано `tools/gen_profiles.py`. «—» = даних немає. Усі плівки зараз працюють на "
         "`experimental_seeds` (оцінки, **не виміряні дані**), і плагін показує це в полі *Profile Status*.", "",
         "## Плівки зйомки (20)", "",
         "| Плівка | Статус | " + " | ".join(short[f] for f in PHYS) + " | Джерел |",
         "|---|---|" + "---|" * len(PHYS) + "---|"]
    for i in ORDER:
        p = P[i]
        L.append("| %s | %s | %s | %d |" % (p["name"], p["status"], " | ".join(cell(p[f]) for f in PHYS), len(p["sources"])))
    L += ["", "## Плівки друку", "", "| Плівка | Статус | " + " | ".join(short[f] for f in PRINT_PHYS) + " | Джерел |",
          "|---|---|" + "---|" * len(PRINT_PHYS) + "---|"]
    for i in PRINT_ORDER:
        p = P[i]
        L.append("| %s | %s | %s | %d |" % (p["name"], p["status"], " | ".join(cell(p[f]) for f in PRINT_PHYS),
                                           len(p["sources"])))
    L += ["", "## Що потрібно, щоб профіль став verified", "",
          "Для кожної плівки — з офіційного технічного листа виробника (з номером ревізії, сторінкою й рисунком):",
          "1. характеристичні криві (log H → density, R/G/B, Status M для негативу / Status A для друку);",
          "2. спектральна чутливість шарів (log sensitivity vs nm);",
          "3. спектральна щільність барвників (cyan/magenta/yellow + base);",
          "4. base+fog / Dmin; 5. RMS granularity з апертурою; 6. MTF.",
          "Першими потрібні **Kodak VISION3 500T 5219/7219** і **Kodak VISION 2383**.", ""]
    return "\n".join(L)


def main():
    try:
        P = load()
    except Bad as e:
        print("ПОМИЛКА ПРОФІЛЮ:", e)
        sys.exit(1)
    h, md = gen_header(P), gen_md(P)
    if "--check" in sys.argv:
        stale = [p for p, t in ((OUT_H, h), (OUT_MD, md)) if not os.path.exists(p) or open(p, encoding="utf-8").read() != t]
        if stale:
            print("Застарілі згенеровані файли:", stale, "— запусти tools/gen_profiles.py")
            sys.exit(1)
        print("OK: профілі валідні, згенеровані файли актуальні")
        return
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    open(OUT_H, "w", encoding="utf-8").write(h)
    open(OUT_MD, "w", encoding="utf-8").write(md)
    print("OK:", len(ORDER), "плівок,", len(PRINT_ORDER), "друк ->", OUT_H, OUT_MD)


if __name__ == "__main__":
    main()
