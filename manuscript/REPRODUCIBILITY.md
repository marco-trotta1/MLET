# Reproduce the MLET selective correction paper

The reproduction ZIP is a selected evidence bundle. It is not a full MLET checkout. Run the manuscript packaging commands from the full repository root.

This package contains fixed protocols, saved predictions, receipts, analysis code, and figure builders. The primary crop-only comparison was specified before its model fit. The older measured-weather analysis remains exploratory.
SupportGain was chosen using earlier test outcomes from the same archive, including the cropland test rows. The primary interval does not account for this choice.

## Environment

Use Python 3.13.5 and the pinned dependencies in `requirements-paper.lock`. The model runs use one numerical thread. The receipts record library versions, seeds, source hashes, fit warnings, and runtimes.

## Inspect the saved evidence

The main results are in these directories:

- `docs/results/ml_tier1_cropland/` contains the predeclared target-population comparison.
- `docs/results/ml_tier1_gridmet_10member/` contains the ten-member rolling evaluation.
- `docs/results/ml_tier1_gridmet_stuck_corrected/` contains the exploratory daily fault correction.
- `docs/results/ml_tier1_gridmet_sensitivity/` contains split and proximity summaries.
- `docs/results/ml_tier1_selective/` preserves the original measured-weather run.
- `docs/results/ml_tier1_selective_corrected/` contains the exploratory augmentation correction.
- `docs/results/ml_tier1_natural_violations/` contains the natural input violation extension.
- `docs/results/ml_tier1_supportgain_directional_audit/` contains the exploratory reverse-direction comparisons.
- `docs/results/ml_tier1_spatial_holdout/` contains the exploratory first-fold audit.
- `docs/results/ml_tier1_spatial_holdout_sensitivity/` contains the post hoc five-fold extension.
- `docs/results/ml_tier3_gridmet/` contains tuned and standard selector results.
- `docs/results/ml_tier3_gridmet_risk_coverage/` contains risk-coverage curves and intervals.

Each directory includes a report or receipt that identifies its protocol and outputs. The crop-only primary outcome is 0.0414 mm/day, with a paired 95% spatial-group interval from 0.0085 to 0.0788. It uses 3,234 rows from 49 stations and 24 groups. The interval conditions on fitted models and selectors.

## Rebuild analyses and figures

Run these commands from the repository root. Use a clean checkout or preserve each output directory first. Analysis and figure scripts write their result files.

```bash
python3 scripts/analyze_ml_tier1_cropland.py
python3 scripts/build_ml_tier1_cropland_figure.py
python3 scripts/analyze_ml_tier3_gridmet_risk_coverage.py
python3 scripts/build_ml_tier3_gridmet_risk_coverage_figure.py
python3 scripts/analyze_ml_tier1_gridmet_sensitivity.py
python3 scripts/build_ml_tier1_gridmet_sensitivity_figure.py
python3 scripts/analyze_ml_tier1_supportgain_directional_audit.py
python3 scripts/analyze_ml_tier1_supportgain_two_sided_audit.py
python3 scripts/build_ml_tier1_supportgain_directional_audit_figure.py
```

These commands use saved predictions. They do not fit new outer models. The directional audit followed outcome review. The two-sided audit allows either selector to win within each comparison and applies Holm correction across all 39 comparisons. Both audits remain exploratory. Their scripts refuse to overwrite existing results. The risk-coverage analyzer reconstructs inner SupportGain score scales. Its recorded first uncached run took 159.0 seconds; one cached run took 14.0 seconds. Those are single-run measurements without timing intervals.

The spatial holdout extension compares Gain directly with SupportGain. Its clean interval includes zero. Four fixed unit-error transforms have positive simultaneous intervals, with lower acceptance. These results are post hoc and use the same archive.

## Refit the spatial holdout

Run these commands in order from the repository root. The five-fold extension reuses fold-zero predictions and fits the other four folds.

```bash
python3 scripts/run_ml_tier1_spatial_holdout.py
python3 scripts/run_ml_tier1_spatial_holdout_sensitivity.py
python3 scripts/build_ml_tier1_spatial_holdout_figure.py
```

Both runners refuse to overwrite saved results. Use a clean working copy without the two spatial holdout result directories. Read both spatial protocols before fitting. The five-fold analysis remains exploratory and conditions on fitted models.

## Refit the cropland comparison

Start from a clean checkout with the public archive inputs acquired and the all-station cohort and ten-member predictions rebuilt. The crop runner refuses to overwrite a nonempty result directory.

```bash
python3 scripts/run_ml_tier1_cropland.py
python3 scripts/analyze_ml_tier1_cropland.py
python3 scripts/build_ml_tier1_cropland_figure.py
```

The crop-only run uses 270 inner and 90 outer neural members. All 360 members reach the 120-iteration limit and report convergence warnings. Its recorded runtime is 58.3 seconds in one run. No timing interval was measured. Read `docs/evaluation/ML_TIER1_CROPLAND_TRAINING_PROTOCOL.md` before refitting.

## Refit the natural input violation extension

Read `docs/evaluation/ML_TIER1_NATURAL_VIOLATIONS_PROTOCOL.md` before fitting.
The named comparison excludes the known `manilacotton` station.
It uses 133 rows from 21 stations and 17 groups. The runner refuses to overwrite saved results.

```bash
python3 scripts/run_ml_tier1_natural_violations.py
python3 scripts/analyze_ml_tier1_natural_violations.py
python3 scripts/build_ml_tier1_natural_violations_figure.py
python3 scripts/run_ml_tier1_gridmet_stuck_correction.py
python3 scripts/analyze_ml_tier1_gridmet_stuck_correction.py
```

The 17-group interval touches zero. Only two groups have nonzero method differences.
Unchanged OpenET has lower point error than Gain and SupportGain on this population.
The 47.6-second fit time is one measurement without a timing interval.

Read the protocol in each result directory before running any other experiment. The split sensitivity ran for 111.8 minutes across 29 new fits. Its warnings and every setting remain in the source repository. Do not treat split settings as independent trials.

## Build the manuscript package

The canonical source is `manuscript/arxiv/mlet_preprint.tex`. Compile and package it from the repository root:

```bash
cd manuscript/arxiv
tectonic --outdir ../../output/pdf --keep-logs --keep-intermediates mlet_preprint.tex
cd ../..
python3 scripts/package_selective_paper.py
python3 scripts/verify_arxiv_manuscript.py --pdf output/pdf/mlet_preprint.pdf
```

The package script writes the current PDF, PDF metadata, source archive, and separate reproduction ZIP. The source archive contains the files needed to compile the paper. The ZIP contains code and saved evidence. arXiv server-side compilation remains untested. The preprint is not submitted and has no arXiv identifier.

## Data and figure provenance

The experiments use the [OpenET validation archive](https://doi.org/10.5281/zenodo.10119477) and [processed flux archive](https://doi.org/10.5281/zenodo.7636781). Source checksums appear in the data manifest and run receipts. Raw weather archives are not copied into the source package.

New figures adapt the layout, typography, palette, and vector-export guidance from [figures4papers](https://github.com/ChenLiu-1996/figures4papers), revision `3c181f85e82c6f24948fcaaf3be6696102b41d8d`. See its [scientific figure workflow](https://github.com/ChenLiu-1996/figures4papers/blob/main/scientific-figure-making/SKILL.md). The source scripts and figures retain the CC BY-NC 4.0 attribution in `manuscript/licenses/`.
