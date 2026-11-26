# FILM EMULATION ENGINE — MASTER SPECIFICATION

## 0. Instructions for Claude / coding agent

You are working on an existing film-emulation plugin. Read this entire document before modifying code. Inspect the existing repository, host API, rendering pipeline, color management, GPU backend, tests and licensing. Preserve working functionality and existing UI conventions. Do not blindly rewrite the project or assume OFX, Metal, CUDA, Resolve, or any particular language. Produce an implementation plan based on the actual repository, then implement incrementally with tests. Prioritize a physically plausible, reproducible, scene-referred engine over cosmetic LUTs. Target Dehancer-like functionality, not a clone of proprietary code, assets, measurements or branding.

**Critical:** This document is a research and engineering specification, not a complete measured film database. Never treat approximate values as manufacturer measurements. Never silently substitute generic defaults for missing stock-specific data. A profile may be experimental, incomplete or verified; expose that status. Keep the source, processing assumptions, units and uncertainty of every numerical dataset. Do not claim identical results to real film without validation. Do not make up curves or cite sources you have not inspected. Existing profiles should not be replaced with less reliable data.

## 1. Product goal

Implement a universal film physics engine with independent camera film, development, optical effects, grain, print film / scanning and output transform. A film profile is data, not a separate shader. Adding new stocks should normally require only new validated profile data. Aim for interactive GPU preview, deterministic render/export, reasonable memory use, and stable color across exposure, resolution and host color spaces.

Initial milestone: Kodak VISION3 500T 5219 + Kodak VISION Color Print 2383, with a bypassable negative-to-print pipeline. Validate this before expanding the library. Start with a calibrated RGB density model if spectral reconstruction is not feasible; implement a spectral reference path for research and calibration, then bake validated approximations for GPU use. Do not present an RGB approximation as full spectral reconstruction.

## 2. Target stock catalog (20)

This is a curated set of popular / influential emulation targets, not an audited sales ranking. Looks below are artistic shorthand, not measured constraints; output also depends on exposure, development, scanning and printing. Gamma ranges are *unverified engineering seeds* from the preceding discussion, not certified film specifications. For reversal films, the seed refers only to absolute slope magnitude; density decreases with exposure. For monochrome, slope depends strongly on developer, time and agitation. All seeds should be replaced by sourced curves.

| ID | Stock | ISO/EI nominal | Process | Class | Approximate slope seed (unverified) | Artistic shorthand |
|---|---|---:|---|---|---|---|
| kodak_vision3_500t | Kodak VISION3 500T 5219/7219 | 500 | ECN-2 | color negative | 0.53 | tungsten, night scenes, latitude |
| kodak_vision3_250d | Kodak VISION3 250D 5207/7207 | 250 | ECN-2 | color negative | 0.53 | daylight, balanced |
| kodak_vision3_200t | Kodak VISION3 200T 5213/7213 | 200 | ECN-2 | color negative | 0.53 | tungsten, finer grain |
| kodak_vision3_50d | Kodak VISION3 50D 5203/7203 | 50 | ECN-2 | color negative | 0.55 | daylight, fine grain |
| fuji_eterna_500t | Fujifilm ETERNA 500T 8573 | 500 | ECN-2 compatible | color negative | 0.45–0.65 | restrained cinematic color |
| kodak_portra_400 | Kodak Portra 400 | 400 | C-41 | color negative | 0.58 | portrait, soft color |
| kodak_portra_800 | Kodak Portra 800 | 800 | C-41 | color negative | 0.50–0.70 | low light, portrait |
| kodak_portra_160 | Kodak Portra 160 | 160 | C-41 | color negative | 0.50–0.65 | portrait, fine grain |
| kodak_gold_200 | Kodak Gold 200 | 200 | C-41 | color negative | 0.55–0.75 | warm snapshot |
| kodak_ektar_100 | Kodak Ektar 100 | 100 | C-41 | color negative | 0.54–0.59 | saturated, fine grain |
| kodak_colorplus_200 | Kodak ColorPlus 200 | 200 | C-41 | color negative | 0.55–0.75 | consumer snapshot |
| fuji_pro_400h | Fujicolor Pro 400H | 400 | C-41 | color negative | 0.45–0.65 | soft portrait palette |
| fuji_superia_xtra_400 | Fujicolor Superia X-TRA 400 | 400 | C-41 | color negative | 0.66–0.70 | consumer daylight |
| cinestill_800t | CineStill 800T | 800 | C-41 recommended | color negative | 0.45–0.70 | tungsten, prominent halation |
| kodak_ektachrome_e100 | Kodak Ektachrome E100 | 100 | E-6 | color reversal | 1.5–2.2 | clean, contrasty slide |
| kodak_kodachrome_64 | Kodak Kodachrome 64 | 64 | K-14 | color reversal | 1.5–2.0 | historical slide |
| fuji_velvia_50 | Fujichrome Velvia 50 | 50 | E-6 | color reversal | 1.5–2.5 | saturated landscape |
| fuji_provia_100f | Fujichrome Provia 100F | 100 | E-6 | color reversal | 1.5–2.2 | balanced slide |
| kodak_trix_400 | Kodak Tri-X 400 | 400 | B&W | monochrome negative | 0.50–0.80 | classic documentary |
| ilford_hp5_plus_400 | Ilford HP5 Plus 400 | 400 | B&W | monochrome negative | 0.50–0.80 | reportage, flexible development |

Independent print profiles: Kodak VISION Color Print 2383, Kodak VISION Premier Color Print 2393, Fujifilm ETERNA CP 3513DI. Print stock is not a camera film; do not assign arbitrary camera ISO. Confirm exact stock versions and process documentation. Discontinued stocks require archived sheets and historical samples; do not assume modern equivalents. CineStill 800T is not numerically identical to standard 5219 processed in ECN-2. Kodachrome requires its own reversal/process assumptions, not an E-6 clone.

## 3. Required data per stock

| Field | Units / representation | Acquisition / derivation |
|---|---|---|
| Spectral sensitivity | wavelength nm; linear relative sensitivity or log10 sensitivity with explicit convention | manufacturer curves; digitize separately for each recording layer |
| Characteristic curves | log10 exposure vs optical density; channels and density standard explicitly identified | digitize sensitometric curves, retain toe, linear section, shoulder |
| Dye density | optical density vs wavelength for cyan, magenta, yellow and base; reference dye amount | manufacturer spectral dye curves; distinguish normalized and absolute measurements |
| Base + fog | optical density per measurement channel or spectral baseline | unexposed developed film, or documented curve minima for negatives; do not confuse with reversal Dmin |
| Exposure latitude | stops relative to calibrated reference exposure; threshold definition required | derive usable interval from curves and explicit density/slope or output criteria |
| RMS granularity | RMS density fluctuation vs density, aperture diameter and measurement standard | manufacturer granularity curves; retain aperture and density convention |
| Grain distribution | spatial PSD, correlation lengths in micrometers, cross-channel covariance, distribution | controlled high-resolution scans, account for scanner MTF/noise |
| MTF | cycles/mm (lp/mm), response ratio, channel | manufacturer frequency curves; note that response can exceed 1 due to adjacency effects |
| Halation | spatial PSF per channel; radius in micrometers; strength in defined exposure units | point/edge exposure tests, spectral dependence, backing and format |
| Interlayer effects | coupling model or measured exposure-to-density cross-talk | colored patch exposures / calibrated fitting; not identifiable from neutral curves alone |
| Push/pull | separate exposure-to-density datasets per processing variant | documented processing tests; not just exposure compensation |
| Reciprocity failure | exposure time vs compensation stops and color correction | manufacturer long/short exposure tables; missing if unavailable |
| Additional metadata | reference illuminant, process, lot/era, format, density measurement geometry, scan settings | manufacturer datasheet and experiment metadata |

Spectral arrays: use a configurable 380–780 nm grid at 5 nm steps (81 samples) as a working representation, not a claim that all stocks are measured over that range. Preserve raw source wavelength samples, mask unsupported intervals, and do not silently extrapolate. Preserve units and log/linear encoding. Use monotone interpolation where physically appropriate, not arbitrary smoothing that erases toe/shoulder or invents spectral tails.

## 4. Previous numeric examples: quarantine until verified

The earlier discussion included the following approximate RGB density slopes from purported secondary digitization. They are **not independently verified here**, and must not be promoted to measured data. The channel labels refer to densitometric readings and are not necessarily pure emulsion-layer responses.

| Stock | R | G | B |
|---|---:|---:|---:|
| 500T | 0.478 | 0.558 | 0.553 |
| 250D | 0.475 | 0.557 | 0.547 |
| 200T | 0.484 | 0.568 | 0.540 |
| 50D | 0.502 | 0.587 | 0.574 |

The earlier example base/fog RGB [0.18, 0.58, 0.85] for 500T was illustrative, not verified. Do not use as a real measurement. Earlier sparse spectral readings at 400–675 nm were also approximate and lacked confirmed scale/normalization; do not use them for production. Retrieve the actual manufacturer graphs and digitize anew. A single gamma value never replaces complete characteristic curves.

## 5. Physical / mathematical pipeline

1. Input transform: decode host input (camera Log, scene-linear, ACES, etc.) to a documented scene-linear working space. Respect metadata; avoid double transforms and implicit clipping. Preserve HDR headroom. Define policy for negative RGB values and out-of-gamut input.
2. Exposure and white balance: exposure multiplier `2^EV`; calibrate film exposure reference using known test patches. 18% gray is a convenient anchor, not automatically a known lux-second film exposure. 500T/200T nominal tungsten balance 3200 K; daylight stocks nominal 5500 K, confirm source. ISO alone does not establish absolute exposure from arbitrary RGB.
3. Spectral reconstruction (optional reference path): RGB does not uniquely determine spectra. Choose a documented reconstruction method and illuminant assumptions; distinguish scene radiance from reflectance. Reconstruct plausible nonnegative spectra or use a fitted RGB-to-layer exposure transform. For spectral model, layer exposure `H_i = k_i * sum(L(lambda) * S_i(lambda) * delta_lambda)`; sensitivity linearized from log data only with correct convention.
4. Optical scattering / halation: apply in exposure space before nonlinear development. Use energy-controlled, channel-dependent PSFs, broad weak tails and physically calibrated radius. Avoid arbitrary red outline, hard thresholds and resolution-dependent look. Separate optical bloom / lens diffusion from internal film halation. Remjet / anti-halation backing differs by stock; no universal strength. Use calibrated mixture of kernels or measured PSF; prevent unintentional energy gain.
5. Development: `x_i = log10(max(H_i, epsilon) / H_ref_i)`; `D_i = f_i(x_i)` where f is a stock/process-specific measured curve. One stop = log10(2) ≈ 0.30103 log exposure. For negative, density generally increases with exposure; reversal generally decreases. For B&W use developer-specific monochrome curves. Model interlayer effects only when fitted/validated. Density curves measured with status filters are not necessarily direct dye concentrations; fit a measurement model or use an explicitly empirical density-space path.
6. Grain: generate density-domain stochastic fluctuations conditioned on exposure/density, layer and physical format. Calibrate RMS and spatial power spectrum separately. Use cross-channel covariance, multi-scale fields or a validated grain model, not independent RGB white noise or a fixed overlay. RMS granularity often reported as 1000 × standard deviation of density at a specified aperture; verify each source. Do not interpret RMS number as particle diameter. Grain particle size cannot be inferred uniquely from RMS or MTF. Apply grain before print/scanner rendering. Convert physical size to image pixels using active film aperture/crop, not resolution alone. Deterministic seed from frame index + user seed, tile invariant coordinates, controlled temporal variation; no random flicker during scrubbing or rerendering same frame.
7. Spectral density/transmission: `D(lambda) = D_base(lambda) + sum(c_i * d_i(lambda))` where c_i and dye basis normalization are calibrated; `T(lambda) = 10^(-D(lambda))`. Do not double-count base/fog. Fit dye amounts from densitometric data where feasible; keep measurement filters separate from dye basis.
8. Print film (optional): simulate printer illuminant and exposure through negative transmission; `H_print_i = sum(E_printer(lambda) * T_negative(lambda) * S_print_i(lambda) * delta_lambda)`. Apply print characteristic curves, print dyes, optional print grain, and projection/viewing illuminant. Printer-light controls alter print exposure/color before print development. Avoid double inversion: a negative-to-positive print chain is different from a direct scanner rendering. Reversal film can be viewed directly or routed through an explicitly appropriate duplication pipeline.
9. Scanner / direct positive rendering: virtual scanner illuminant/sensor, negative inversion and calibration, or direct slide transmission as appropriate. For transmitted positive use observer XYZ integration with documented illuminant/normalization. Scanner look is a separate profile, not intrinsic to negative stock. Offer distinct print and scan paths.
10. Output: map to target Rec.709, P3, HDR or host-managed output using explicit transform and gamut handling. Avoid applying display tone map twice; neutral bypass and host color management must be tested.
11. Optional presentation artifacts: gate weave, exposure flicker, dust, scratches, film damage. Separate from stock physics; deterministic temporal effects, disabled by default. Film gauge (8/16/35/65 mm) controls geometry and grain scaling separately from stock chemistry.

MTF: model optical/spatial response where supported. A measured system MTF may include development adjacency and measurement aperture, so do not blindly convolve with separate kernels that double-count blur. Fit PSF or frequency-domain transfer; nonnegative blur kernels cannot reproduce all MTF curves with overshoot. Validate against edge/line-pair test patterns.

## 6. Profile schema (example; intentionally incomplete)

```json
{
  "schema_version": 1,
  "id": "kodak_vision3_500t",
  "name": "Kodak VISION3 500T",
  "stock_codes": ["5219", "7219"],
  "class": "color_negative",
  "process": "ECN-2",
  "exposure_index": 500,
  "nominal_balance_kelvin": 3200,
  "status": "incomplete",
  "characteristic_curves": null,
  "spectral_sensitivity": null,
  "dye_density": null,
  "base_fog": null,
  "exposure_latitude": null,
  "rms_granularity": null,
  "grain_distribution": null,
  "mtf": null,
  "halation": null,
  "interlayer_effects": null,
  "push_pull_response": null,
  "reciprocity_failure": null,
  "sources": [],
  "experimental_seeds": {
    "gamma_rgb": [0.478, 0.558, 0.553],
    "status": "unverified_secondary_estimate",
    "production_enabled": false
  }
}
```

Each non-null physical field should contain values or an asset path, axes, units, encoding, channel order, conditions, valid domain, source ID, page/figure, extraction method, uncertainty (null if unknown), and classification `measured_published`, `digitized`, `derived`, `fitted`, or `estimated`. Separate raw and processed data. Use JSON metadata and CSV/NPZ or project-native binary textures for numeric arrays. Example CSV axes: `wavelength_nm,r,g,b`; `log10_relative_exposure,density_r,density_g,density_b`; `frequency_lp_mm,mtf_r,mtf_g,mtf_b`. Record missing values explicitly; never silently convert missing samples to zero. Different fields may use different native axes. For B&W, allow one channel; do not invent color layers. For a missing essential field, prevent verified mode or provide a visibly labeled approximation. Validate schema on load.

## 7. Research sources / acquisition plan

The following links are leads from the preceding conversation, **not newly verified in this document**. Confirm accessibility, license, version, stock, and actual content before relying on any of them. Prefer primary manufacturer documents.

- Kodak motion camera stocks: https://www.kodak.com/en/motion/products/camera-films/
- Kodak 500T technical data lead: https://www.kodak.com/content/products-brochures/Film/VISION3-500T-Color-Negative-Film-7219-TECHNICAL-DATA.pdf
- Fujifilm film data guide lead: https://asset.fujifilm.com/www/us/files/2020-03/d52487c5c6f84e7f935c299491c5c1ff/ProfessionalFilmDataGuide.pdf
- Kodak photographic films and Ilford manufacturer technical sheets (search by exact stock and version).
- Dehancer methodology lead: https://www.dehancer.com/learn/articles/how-we-build-film-profiles — methodology only, not access to proprietary profile data.
- Spektrafilm: https://github.com/andreavolpato/spektrafilm
- Darktable Spektrafilm: https://github.com/darktable-org/darktable-spektrafilm
- Film scan calibration data leads: https://github.com/OwlMightyCh/film-scan-calibration/blob/main/DATASHEETS.md
- OpenFilm experimental plugin lead: https://github.com/xanderlzy/OpenFilm
- Spektrafilm medium editor lead: https://github.com/alchemy-color/spektrafilm-medium-editor
- Datasheet archive lead: https://www.theopticslab.com/datasheets

Open-source projects can be studied for methodology, data conventions and reference testing. Do not copy code or datasets into a closed commercial plugin without checking exact licenses and obligations for each asset and version. Previous discussion mentioned GPLv3 for code and CC BY-SA 4.0 for some profile data; verify rather than assume. Public availability of a PDF is not a blanket redistribution license. Keep source manifests, license notices and original data separate. Do not reverse engineer proprietary Dehancer profiles or extract its LUTs.

Data ingestion workflow: download authoritative datasheet; record URL, revision, date, checksum, figure and measurement conditions; inspect figure visually; prefer vector paths or original numeric tables; otherwise use calibrated plot digitization (e.g. WebPlotDigitizer), correctly handle log axes; independently check points against the graph; resample only after raw extraction; fit curves with residuals and uncertainty; compare against real film tests; mark profile completeness. Record all 12 fields for each of the 20 stocks in a coverage matrix with source/status, even if missing. Do not fabricate missing curves when retrieval is unavailable. Use local file uploads or ask the project owner for missing datasheets if necessary.

## 8. Implementation plan and acceptance criteria

Phase A: audit existing repo, identify input/output transforms, plugin host, GPU backend and threading; preserve project conventions. Add profile schema, registry, validation, source manifest and fallback policy. Add CPU reference implementation with unit tests.

Phase B: acquire and digitize 500T and 2383 data; implement exposure-to-density, transmission, negative-to-print and scanner paths; compare CPU reference vs GPU approximation. Implement verified mode and experimental mode separately. If data unavailable, ship only labeled experimental profile, not invented authenticity.

Phase C: add halation/bloom with exposure-domain kernels, grain with density-conditioned statistics, gauge scaling, deterministic frame seeds. Add MTF where validated. Use separable/multi-resolution kernels where appropriate; test boundaries, tiled rendering, proxy vs final, no NaN/Inf.

Phase D: add remaining stocks progressively with data coverage and per-stock tests. Implement reversal and B&W as distinct branches. Add print 2393 and 3513DI if data is available. Add development variants only with evidence.

Phase E: polish UX, performance and validation. Recommended user controls: input color space, stock, exposure EV, temperature/tint if compatible with pipeline, print/scan path, printer lights, grain amount/size/gauge, halation amount/radius, bloom, optional presentation artifacts, output space, reset and bypass. Stock defaults should be calibrated and overrides should be clearly creative. A bypassed module should be identity in its declared domain. Do not duplicate host color management.

Validation suite:
- Exposure ramp and step wedge across shadows, mids and highlights; verify characteristic curves against digitized points and report residuals in density units.
- Neutral gray and color chart under daylight/tungsten; compare reference scans/prints with matched illuminant and scanner calibration; report Delta E where reference supports it, not invented tolerances.
- Negative and reversal curve direction, correct base treatment, print exposure response and no double inversion.
- Grain RMS vs density and aperture, spatial PSD, channel covariance, temporal stability and format scaling.
- Halation point/edge spread and energy behavior; MTF chart; avoid visible tiling seams.
- Same seed/frame yields same result; scrub order independent; proxy/full resolution consistent in physical scale.
- HDR extremes, black, negative channels, out-of-gamut colors, alpha handling according to host; finite output; CPU/GPU comparison with documented tolerance.
- Benchmark 1080p/4K on actual supported hardware; record frame time and memory, do not claim real-time performance without measurements.

Suggested repository layout (adapt to actual project): `profiles/`, `profiles/sources/`, `profiles/raw/`, `profiles/processed/`, `tools/digitize/`, `engine/reference/`, `engine/gpu/`, `tests/`, `docs/`. Add a profile coverage report listing all 20 stocks × 12 physical fields and print stocks, including missing data. Keep tests and documentation updated with each implementation.

## 9. First action requested from Claude

Inspect the codebase and return a short audit of what already exists versus this specification. Then implement the highest-value missing foundation in the current codebase, starting with profile schema and the 500T → 2383 reference path, without breaking existing functionality. If source data is missing, implement ingestion and explicitly labeled experimental fallback rather than falsely claiming measured accuracy. Run available tests, summarize changed files, remaining blockers, and what exact primary data is still needed. Continue incrementally when instructed. This file is the project's technical reference, not a mandate to invent unsupported numbers or discard working code.
