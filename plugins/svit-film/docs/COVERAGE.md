# Svit Film — покриття даних профілів

Згенеровано `tools/gen_profiles.py`. «—» = даних немає. Усі плівки зараз працюють на `experimental_seeds` (оцінки, **не виміряні дані**), і плагін показує це в полі *Profile Status*.

## Плівки зйомки (20)

| Плівка | Статус | Curves | Spectral | Dyes | Base+fog | Latitude | RMS gran. | Grain PSD | MTF | Halation | Interlayer | Push/pull | Reciprocity | Джерел |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Kodak VISION3 500T | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Kodak VISION3 250D | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Kodak VISION3 200T | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Kodak VISION3 50D | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Fujifilm ETERNA 500T | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Kodak Portra 400 | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Kodak Portra 800 | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Kodak Portra 160 | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Kodak Gold 200 | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Kodak Ektar 100 | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Kodak ColorPlus 200 | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Fujicolor Pro 400H | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Fujicolor Superia X-TRA 400 | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| CineStill 800T | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Kodak Ektachrome E100 | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Kodak Kodachrome 64 | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Fujichrome Velvia 50 | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Fujichrome Provia 100F | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Kodak Tri-X 400 | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |
| Ilford HP5 Plus 400 | experimental | — | — | — | — | — | — | — | — | — | — | — | — | 0 |

## Плівки друку

| Плівка | Статус | Curves | Spectral | Dyes | Base+fog | RMS gran. | MTF | Джерел |
|---|---|---|---|---|---|---|---|---|
| Kodak VISION Color Print 2383 | experimental | — | — | — | — | — | — | 0 |
| Kodak VISION Premier Color Print 2393 | experimental | — | — | — | — | — | — | 0 |
| Fujifilm ETERNA CP 3513DI | experimental | — | — | — | — | — | — | 0 |

## Що потрібно, щоб профіль став verified

Для кожної плівки — з офіційного технічного листа виробника (з номером ревізії, сторінкою й рисунком):
1. характеристичні криві (log H → density, R/G/B, Status M для негативу / Status A для друку);
2. спектральна чутливість шарів (log sensitivity vs nm);
3. спектральна щільність барвників (cyan/magenta/yellow + base);
4. base+fog / Dmin; 5. RMS granularity з апертурою; 6. MTF.
Першими потрібні **Kodak VISION3 500T 5219/7219** і **Kodak VISION 2383**.
