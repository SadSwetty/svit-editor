// Згенеровано tools/gen_profiles.py з profiles/*.json. Не редагувати вручну.
// УВАГА: усі числа тут — experimental_seeds (оцінки), а не виміряні дані плівок.
#pragma once
namespace svitfilm {

struct StockDef { const char* id; const char* name; const char* status; int cls;
  float gamma[3], toe, shoulder, toeW, shW, dmin[3], dmax, colorSep, balance[3], grain, halation, mono[3]; };
struct PrintDef { const char* id; const char* name; const char* status;
  float gamma[3], dmin[3], dmax, toeW, shW; };

static const StockDef kStocks[] = {
  {"kodak_vision3_500t", "Kodak VISION3 500T", "Experimental - estimated curves, not measured (0/12 fields)", 0, {0.478f, 0.558f, 0.553f}, -1.8f, 2.1f, 0.22f, 0.45f, {0.2f, 0.6f, 0.85f}, 0.0f, 0.15f, {0.0f, 0.0f, 0.0f}, 1.0f, 0.25f, {0.0f, 0.0f, 0.0f}},
  {"kodak_vision3_250d", "Kodak VISION3 250D", "Experimental - estimated curves, not measured (0/12 fields)", 0, {0.475f, 0.557f, 0.547f}, -1.8f, 2.1f, 0.22f, 0.45f, {0.2f, 0.6f, 0.85f}, 0.0f, 0.15f, {0.0f, 0.0f, 0.0f}, 0.7f, 0.25f, {0.0f, 0.0f, 0.0f}},
  {"kodak_vision3_200t", "Kodak VISION3 200T", "Experimental - estimated curves, not measured (0/12 fields)", 0, {0.484f, 0.568f, 0.54f}, -1.8f, 2.1f, 0.22f, 0.45f, {0.2f, 0.6f, 0.85f}, 0.0f, 0.15f, {0.0f, 0.0f, 0.0f}, 0.6f, 0.25f, {0.0f, 0.0f, 0.0f}},
  {"kodak_vision3_50d", "Kodak VISION3 50D", "Experimental - estimated curves, not measured (0/12 fields)", 0, {0.502f, 0.587f, 0.574f}, -1.8f, 2.1f, 0.22f, 0.45f, {0.2f, 0.6f, 0.85f}, 0.0f, 0.15f, {0.0f, 0.0f, 0.0f}, 0.35f, 0.25f, {0.0f, 0.0f, 0.0f}},
  {"fuji_eterna_500t", "Fujifilm ETERNA 500T", "Experimental - estimated curves, not measured (0/12 fields)", 0, {0.52f, 0.55f, 0.55f}, -1.8f, 2.1f, 0.22f, 0.45f, {0.2f, 0.6f, 0.85f}, 0.0f, 0.05f, {-0.01f, 0.0f, 0.01f}, 0.9f, 0.25f, {0.0f, 0.0f, 0.0f}},
  {"kodak_portra_400", "Kodak Portra 400", "Experimental - estimated curves, not measured (0/12 fields)", 0, {0.56f, 0.58f, 0.58f}, -1.8f, 2.1f, 0.22f, 0.45f, {0.2f, 0.6f, 0.85f}, 0.0f, 0.08f, {0.015f, 0.0f, -0.01f}, 0.65f, 0.5f, {0.0f, 0.0f, 0.0f}},
  {"kodak_portra_800", "Kodak Portra 800", "Experimental - estimated curves, not measured (0/12 fields)", 0, {0.58f, 0.6f, 0.6f}, -1.8f, 2.1f, 0.22f, 0.45f, {0.2f, 0.6f, 0.85f}, 0.0f, 0.08f, {0.015f, 0.0f, -0.01f}, 0.95f, 0.5f, {0.0f, 0.0f, 0.0f}},
  {"kodak_portra_160", "Kodak Portra 160", "Experimental - estimated curves, not measured (0/12 fields)", 0, {0.55f, 0.57f, 0.57f}, -1.8f, 2.1f, 0.22f, 0.45f, {0.2f, 0.6f, 0.85f}, 0.0f, 0.06f, {0.01f, 0.0f, -0.005f}, 0.4f, 0.5f, {0.0f, 0.0f, 0.0f}},
  {"kodak_gold_200", "Kodak Gold 200", "Experimental - estimated curves, not measured (0/12 fields)", 0, {0.66f, 0.64f, 0.62f}, -1.8f, 2.1f, 0.22f, 0.45f, {0.2f, 0.6f, 0.85f}, 0.0f, 0.2f, {0.03f, 0.01f, -0.03f}, 0.7f, 0.55f, {0.0f, 0.0f, 0.0f}},
  {"kodak_ektar_100", "Kodak Ektar 100", "Experimental - estimated curves, not measured (0/12 fields)", 0, {0.57f, 0.57f, 0.56f}, -1.8f, 2.1f, 0.22f, 0.45f, {0.2f, 0.6f, 0.85f}, 0.0f, 0.3f, {0.005f, 0.0f, -0.005f}, 0.3f, 0.5f, {0.0f, 0.0f, 0.0f}},
  {"kodak_colorplus_200", "Kodak ColorPlus 200", "Experimental - estimated curves, not measured (0/12 fields)", 0, {0.66f, 0.64f, 0.62f}, -1.8f, 2.1f, 0.22f, 0.45f, {0.2f, 0.6f, 0.85f}, 0.0f, 0.15f, {0.025f, 0.01f, -0.02f}, 0.8f, 0.55f, {0.0f, 0.0f, 0.0f}},
  {"fuji_pro_400h", "Fujicolor Pro 400H", "Experimental - estimated curves, not measured (0/12 fields)", 0, {0.52f, 0.55f, 0.56f}, -1.8f, 2.1f, 0.22f, 0.45f, {0.2f, 0.6f, 0.85f}, 0.0f, 0.05f, {-0.01f, 0.01f, 0.01f}, 0.6f, 0.5f, {0.0f, 0.0f, 0.0f}},
  {"fuji_superia_xtra_400", "Fujicolor Superia X-TRA 400", "Experimental - estimated curves, not measured (0/12 fields)", 0, {0.68f, 0.68f, 0.67f}, -1.8f, 2.1f, 0.22f, 0.45f, {0.2f, 0.6f, 0.85f}, 0.0f, 0.18f, {-0.01f, 0.015f, 0.0f}, 0.85f, 0.5f, {0.0f, 0.0f, 0.0f}},
  {"cinestill_800t", "CineStill 800T", "Experimental - estimated curves, not measured (0/12 fields)", 0, {0.48f, 0.56f, 0.55f}, -1.8f, 2.1f, 0.22f, 0.45f, {0.2f, 0.6f, 0.85f}, 0.0f, 0.12f, {0.0f, 0.0f, 0.0f}, 1.1f, 1.6f, {0.0f, 0.0f, 0.0f}},
  {"kodak_ektachrome_e100", "Kodak Ektachrome E100", "Experimental - estimated curves, not measured (0/12 fields)", 1, {1.8f, 1.8f, 1.85f}, -0.9f, 0.6f, 0.18f, 0.2f, {0.15f, 0.15f, 0.18f}, 3.4f, 0.25f, {0.0f, 0.0f, 0.005f}, 0.25f, 0.3f, {0.0f, 0.0f, 0.0f}},
  {"kodak_kodachrome_64", "Kodak Kodachrome 64", "Experimental - estimated curves, not measured (0/12 fields)", 1, {1.75f, 1.7f, 1.7f}, -0.9f, 0.6f, 0.18f, 0.2f, {0.15f, 0.15f, 0.18f}, 3.4f, 0.35f, {0.02f, 0.0f, -0.02f}, 0.3f, 0.3f, {0.0f, 0.0f, 0.0f}},
  {"fuji_velvia_50", "Fujichrome Velvia 50", "Experimental - estimated curves, not measured (0/12 fields)", 1, {2.0f, 2.05f, 2.0f}, -0.9f, 0.6f, 0.18f, 0.2f, {0.15f, 0.15f, 0.18f}, 3.4f, 0.5f, {0.0f, 0.005f, 0.0f}, 0.2f, 0.3f, {0.0f, 0.0f, 0.0f}},
  {"fuji_provia_100f", "Fujichrome Provia 100F", "Experimental - estimated curves, not measured (0/12 fields)", 1, {1.8f, 1.8f, 1.8f}, -0.9f, 0.6f, 0.18f, 0.2f, {0.15f, 0.15f, 0.18f}, 3.4f, 0.2f, {0.0f, 0.0f, 0.0f}, 0.22f, 0.3f, {0.0f, 0.0f, 0.0f}},
  {"kodak_trix_400", "Kodak Tri-X 400", "Experimental - estimated curves, not measured (0/12 fields)", 2, {0.65f, 0.65f, 0.65f}, -1.7f, 2.0f, 0.22f, 0.45f, {0.25f, 0.25f, 0.25f}, 0.0f, 0.0f, {0.0f, 0.0f, 0.0f}, 1.0f, 0.3f, {0.32f, 0.52f, 0.16f}},
  {"ilford_hp5_plus_400", "Ilford HP5 Plus 400", "Experimental - estimated curves, not measured (0/12 fields)", 2, {0.62f, 0.62f, 0.62f}, -1.7f, 2.0f, 0.22f, 0.45f, {0.25f, 0.25f, 0.25f}, 0.0f, 0.0f, {0.0f, 0.0f, 0.0f}, 1.05f, 0.3f, {0.3f, 0.55f, 0.15f}},
};
static const int kNumStocks = 20;
static const StockDef kReferenceStock = {"svit_neutral", "Svit Neutral (reference)", "Reference - estimated curves, not measured (0/12 fields)", 0, {0.6f, 0.6f, 0.6f}, -1.8f, 2.1f, 0.22f, 0.45f, {0.2f, 0.6f, 0.85f}, 0.0f, 0.0f, {0.0f, 0.0f, 0.0f}, 0.5f, 0.3f, {0.0f, 0.0f, 0.0f}};

static const PrintDef kPrints[] = {
  {"kodak_2383", "Kodak VISION Color Print 2383", "Experimental - estimated curves, not measured (0/6 fields)", {2.75f, 2.7f, 2.6f}, {0.06f, 0.06f, 0.08f}, 4.0f, 0.2f, 0.25f},
  {"kodak_2393", "Kodak VISION Premier Color Print 2393", "Experimental - estimated curves, not measured (0/6 fields)", {2.95f, 2.9f, 2.8f}, {0.06f, 0.06f, 0.08f}, 4.2f, 0.2f, 0.25f},
  {"fuji_3513di", "Fujifilm ETERNA CP 3513DI", "Experimental - estimated curves, not measured (0/6 fields)", {2.6f, 2.6f, 2.6f}, {0.06f, 0.07f, 0.08f}, 3.9f, 0.2f, 0.25f},
};
static const int kNumPrints = 3;
static const PrintDef kReferencePrint = {"svit_neutral_print", "Svit Neutral Print (reference)", "Reference - estimated curves, not measured (0/6 fields)", {2.7f, 2.7f, 2.7f}, {0.06f, 0.06f, 0.06f}, 4.0f, 0.2f, 0.25f};

}  // namespace svitfilm
