# Phase 2 public daily-ET dataset

## Purpose and scope

This dataset supports the pre-registered Phase 2 question: whether OpenET adds
incremental value for **daily actual-ET** prediction at flux towers. It is a
public-data precursor to, not a validation of, the planned soil-moisture,
root-zone-deficit, or irrigation-timing system.

The frozen hypotheses, models, splits, and decision rule are in
[the Phase 2 pre-registration](../evaluation/PREREGISTRATION.md). Generated
performance and the decision are in
[the Phase 2 results](../results/phase2_openet_value.md).

## Sources and provenance

| Source | Role | Provenance | License |
|---|---|---|---|
| OpenET Phase II model ET | OpenET ensemble predictor and station metadata | Zenodo [record 10119477](https://doi.org/10.5281/zenodo.10119477), `OpenET_PhaseII_model_ET_dataset.zip`, MD5 `26b2af882c21dc56c634ac9f77a2ba6e` | CC-BY-4.0 |
| Flux-tower benchmark | `ET_corr` label, pre-extracted `gridMET_ETo`, and weather covariates | Zenodo [record 7636781](https://doi.org/10.5281/zenodo.7636781), `flux_ET_dataset.zip` (183,188,565 bytes), MD5 `99f6668ca439e9bae48c4e7e08b5405d` | CC-BY-4.0 |
| gridMET `pet` | Independent reference-ET QC and Phase 3 seam | [gridMET](https://www.northwestknowledge.net/metdata/), files `pet_2016.nc` through `pet_2021.nc` | Public data; cite Abatzoglou (2013) |

All source archives and NetCDF files are downloaded through
`scripts/fetch_data.py`, checksum-verified against `data/manifest.json`, and
kept out of Git.

## Join and labels

The builder joins OpenET and flux data on exact `(station_id, date)` keys. All
152 OpenET station IDs occur in the 161-station flux collection. The resulting
contract data contain 16,447 OpenET rows, of which **16,444** have a non-blank,
non-gap-filled `ET_corr` label and `gridMET_ETo`.

`ET_corr`—ET from energy-balance-corrected latent heat—is the ground-truth
label. The uncorrected `ET` column is never scored. Ninety-three published
`ET_corr` values are negative (minimum −1.204 mm/day); they are retained rather
than clipped or silently removed because they are source measurements. The
validator therefore preserves negative `measured_et_mm` values while continuing
to reject negative OpenET and reference-ET inputs.

The primary `eto_mm` field is the benchmark's pre-extracted `gridMET_ETo`,
which reproduces the published EToF construction. The raw NetCDF route is an
independent QC/seam, not a dependency of the primary join.

## QC and coverage

The 2016–2021 gridMET files overlap 84 stations and 4,599 joined station-days.
Nearest-cell extraction produced overall mean absolute difference **0.243
mm/day** from the benchmark `gridMET_ETo`, within the planned 0.1–0.3 mm/day
QC range. Three almond stations are explicit exceptions (1.452–1.690 mm/day);
their disagreement is retained as a source-specific QC caveat, not hidden.

The raw gridMET NetCDF collection covers only 2016–2021, roughly 28% of the
OpenET rows. It is therefore unsuitable as the sole historical reference-ET
source and is not used that way here.

The land-cover distribution across the 152 joined stations is: Croplands 59,
Grasslands 27, Shrublands 26, Evergreen Forests 17, Mixed Forests 14, and
Wetland/Riparian 9.

The common-complete-case comparison used by WeatherRidge and OpenETRidge has
7,923 finite-weather labeled rows from 85 stations. This is narrower than the
16,444-row label inventory and bounds the scope of the Phase 2 result.

## Dependencies and attribution

Phase 2 deliberately adds `numpy` for fixed models/inference, `xarray` and
`netCDF4` for gridMET extraction, and `openpyxl` for source metadata workbooks.
No pandas or scikit-learn model is used in the evaluation pipeline.

Please attribute the OpenET and flux datasets to Volk et al. under CC-BY-4.0,
and cite Abatzoglou (2013) for gridMET. Raw and interim files are reproducible
but intentionally gitignored.
