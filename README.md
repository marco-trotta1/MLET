<picture>
  <source media="(prefers-reduced-motion: reduce)" srcset="docs/assets/mlet-wordmark-static.svg">
  <img src="docs/assets/mlet-wordmark.svg" alt="MLET: Machine Learning Evapotranspiration. Learn the correction. Test the transfer." width="1080">
</picture>

# MLET: Selective Neural Residual Correction for Spatial Evapotranspiration

**[Paper](output/pdf/mlet_arxiv_preprint.pdf) · [Source package](output/arxiv/mlet_preprint_source.tar.gz) · [Reproduction](manuscript/REPRODUCIBILITY.md) · [Saved results](docs/results/ml_selective/) · [Static graphic](docs/assets/mlet-wordmark-static.svg)**

**Marco Trotta · Irrigant · [m@irrigant.xyz](mailto:m@irrigant.xyz)**

MLET studies when a neural residual model should modify an existing satellite evapotranspiration estimate at an unseen location.
The repository contains the research manuscript, experiment code, fixed protocols, saved predictions, and verification scripts.
The manuscript is a preprint draft. It has no assigned arXiv identifier or peer-reviewed acceptance.

## Research question

**Can a selector identify when a neural correction improves OpenET, rather than only estimate the neural model's uncertainty?**

For satellite estimate $o$, neural correction $g(x)$, and binary selector $a(x)$, the complete prediction is

$$\hat y(x) = o + a(x)g(x), \qquad a(x)\in\lbrace 0,1\rbrace.$$

Rejecting a correction returns OpenET. Every test observation receives a prediction and contributes to the reported error.
The selector's target is the realized absolute-error benefit,

$$D(x,y)=|y-o|-|y-o-g(x)|.$$

Positive benefit means that the correction helps relative to the satellite estimate.
Low neural error and positive correction benefit are different objectives.

This study contributes an empirical analysis of selector transfer under spatial withholding and controlled input corruption.
It does not introduce a new deferral algorithm or establish a universally better ET estimator.
The [literature comparison](docs/evaluation/ML_LITERATURE_POSITIONING.md) relates the study to regression with deferral, selective regression, and spatial applicability domains.

## Method

The predictor is an ensemble of three neural residual predictors, each with two 32-unit ReLU hidden layers.
Training uses Adam, 120 epochs, and training-only input and target standardization.
The fixed seeds are `20260713`, `20260714`, and `20260715`.
All selectors within an outer configuration use the same fitted neural predictions.

| Method | Rule for using the correction |
| --- | --- |
| OpenET | Always return the satellite estimate. |
| Full | Always apply the ensemble mean correction. |
| Spread95 | Accept below the calibrated ensemble-disagreement threshold. |
| Support95 | Accept below the calibrated five-neighbor input-distance threshold. |
| Gain | Accept when a boosted regressor predicts positive benefit over OpenET. |
| SupportGain | Require both the support test and positive predicted benefit. |
| Uniform | Apply one correction multiplier selected from `0, 0.25, 0.5, 0.75, 1`. |
| Clip | Clip weather inputs to training percentiles before applying the full correction. |

Inner spatial cross-fitting supplies the selector targets and thresholds.
Outer test labels do not fit the selector, scaler, predictor, or thresholds.
The earlier benchmark also includes affine calibration, weather ridge, combined ridge, and matched direct and residual nonlinear models.
See the [selective protocol](docs/evaluation/ML_SELECTIVE_RESIDUAL_PROTOCOL.md) and [earlier benchmark protocol](docs/evaluation/ML_TRANSFER_PROTOCOL.md) for complete specifications.

## Data and evaluation

The target is energy-balance-corrected **actual evapotranspiration**, in mm/day, from processed flux measurements.
Reference evapotranspiration is an input, not the response.
The archive contains sparse satellite validation dates from 2001 through 2020, rather than complete daily time series.

| Evaluation population | Observations | Stations | Proximity groups |
| --- | ---: | ---: | ---: |
| Complete-weather cohort | 7,923 | 85 | 63 |
| Matched input-fault probes | 7,873 | 84 | 62 |
| Unseen groups and later years | 649 | 27 | 24 |
| Later-year input-fault probes | 646 | 27 | 24 |
| Cropland subset of the complete cohort | 2,670 | 32 | 18 |

Sources: [OpenET validation archive](https://doi.org/10.5281/zenodo.10119477) and [processed flux archive](https://doi.org/10.5281/zenodo.7636781).
The [data manifest](data/manifest.json), [cohort](docs/results/ml_transfer/cohort.csv), and [split assignments](docs/results/ml_transfer/splits.json) bind the evaluated data.
The complete-weather cohort selects 85 of 152 joined stations.
Cropland classification does not establish irrigation status.

The primary evaluation withholds proximity groups across ten outer folds.
Groups are connected components of station pairs within 10 km; transitive connections remain together.
The joint evaluation also restricts training to dates before 2019 and tests 2019 through 2020 at unseen groups.
Three inner spatial folds supply selection data. The joint inner split also separates dates before 2016 from later validation dates.

The primary metric is **station-macro MAE**: average absolute error within each station, then average equally across stations.
The paper also reports pooled MAE, RMSE, signed bias, cropland results, and correction acceptance rates.
Paired intervals use 2,000 bootstrap draws over proximity groups, with seed `20260922`.
They condition on fitted models and ranks, omit retraining uncertainty, and have no multiplicity adjustment.

## Main result and its limits

A learned benefit selector can fail under input corruption even when its training objective correctly compares against the fallback.
However, returning OpenET more often can explain an apparent robustness advantage.
The analysis therefore compares both fixed thresholds and equal acceptance budgets.

After omitting vapor-pressure deficit (VPD), the paired wind probe multiplies the test wind input by ten.
It holds labels, satellite estimates, and fitted models fixed.
On 7,873 observations at 84 stations in 62 groups, Full changes from 0.829 to 1.415 mm/day station MAE.
OpenET scores 0.853 mm/day on these same rows.
Support95 scores 0.857 mm/day but accepts only 1.74% of the station-weighted population.
These point estimates describe the fixed probe; they do not establish a general accuracy gain.

The following **post hoc** comparison fixes acceptance at 50%.
Each difference is the named method's expected station MAE minus Support's expected station MAE, in mm/day.
Positive values favor Support.

| Probe | Comparison | Difference | Paired 95% interval |
| --- | --- | ---: | --- |
| Spatial groups, wind input multiplied by 10 | Gain minus Support | 0.243 | [0.110, 0.412] |
| Spatial groups, wind input multiplied by 10 | Spread minus Support | 0.023 | [-0.022, 0.066] |
| Groups and later years, wind input multiplied by 10 | Gain minus Support | 0.032 | [-0.105, 0.194] |

The first two rows use 7,873 observations and 62 groups. The third uses 646 observations and 24 groups.
The support-versus-disagreement comparison is inconclusive, and later years do not confirm the benefit-selector ordering.
Equal-budget ranking uses label-free test scores and a randomized boundary decision. It does not establish a deployable threshold.
Read the [analysis protocol](docs/evaluation/ML_MATCHED_SELECTION_ANALYSIS.md), [paired comparisons](docs/results/ml_selective/matched_comparisons.json), and [complete curves](docs/results/ml_selective/matched_coverage.csv).

Agricultural transfer also limits the conclusion.
On 2,670 cropland observations from 32 stations in 18 groups, no-VPD Uniform scores 0.961 versus OpenET's 0.931 mm/day.
Its paired improvement interval is [-0.074, 0.017] mm/day.
Every no-VPD selective alternative has a higher cropland point error than OpenET in that spatial evaluation.
The [complete results](docs/results/ml_selective/results.json) retain all methods, input specifications, faults, and subgroups.

### Scope of inference

- The archive was inspected before this study. The selective protocol preceded its new run; the matched-budget analysis followed the threshold results.
- Synthetic faults test predictor corruption. They do not simulate weather interventions or estimate fault prevalence.
- Three seeds measure initialization variation. They do not provide calibrated posterior uncertainty.
- The study does not implement matched leading deferral surrogates, GeoQ, or graph neural processes.
- Spatial withholding applies to the added MLET models. It does not establish independence from upstream OpenET development.
- The evidence does not establish operational forecast skill, irrigation benefits, or water savings.

See [study limitations](manuscript/LIMITATIONS.md) for the full scope.

## Reproduce the evidence

Use Python **3.13.5** to match the recorded numerical environment.
Run these commands from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-paper.lock
PYTHONPATH=src python scripts/verify_ml_paper.py
PYTHONPATH=src python scripts/verify_selective_results.py
python -m pytest tests/test_ml_transfer_audit.py tests/test_ml_selective_residual.py -q
```

These commands verify saved evidence without downloading raw archives or fitting new models.
The audits check partitions, target alignment, source hashes, selector arithmetic, negative controls, and original figure preservation.
The pandas compatibility patch copies two masks; the exact recorded runner remains available for provenance.
All 90 recorded inner partitions remain identical under the patch.

For data acquisition, full refits, figure generation, and paper compilation, follow [the reproduction instructions](manuscript/REPRODUCIBILITY.md).
Completed experiments refuse to overwrite recorded results.
The [standalone reproduction package](output/arxiv/mlet_reproducibility.zip) includes code, protocols, tests, and saved predictions.

### Compute record

The selective experiment runs 480 neural fits across 40 outer configurations and 120 inner partitions.
Its recorded end-to-end wall time is **161.98 seconds**, on macOS ARM with one numerical thread, for one complete run.
This timing has no repeated-run uncertainty estimate and is not a comparative speed claim.
Paid training compute is USD 0; electricity cost is unmeasured.
Per-model fit and prediction timings for the earlier baseline comparison appear in the paper's compute table.
The [receipt](docs/results/ml_selective/receipt.json) records fit timings, seeds, and warnings; [software versions](docs/results/ml_selective/software_environment.json) record the environment.

## Repository map

| Path | Content |
| --- | --- |
| [`scripts/ml_selective_residual.py`](scripts/ml_selective_residual.py) | Fixed selective-correction experiment. |
| [`scripts/ml_transfer_audit.py`](scripts/ml_transfer_audit.py) | Earlier model benchmark and shared partition logic. |
| [`docs/evaluation/`](docs/evaluation/) | Scientific protocols and literature positioning. |
| [`docs/results/ml_selective/`](docs/results/ml_selective/) | Selectors, inner predictions, outer predictions, and robustness probes. |
| [`docs/results/ml_transfer/`](docs/results/ml_transfer/) | Earlier benchmark, humidity audit, and sensitivity results. |
| [`manuscript/arxiv/`](manuscript/arxiv/) | Canonical LaTeX, references, tables, and figures. |
| [`output/arxiv/`](output/arxiv/) | Submission source, metadata, and reproduction package. |
| [`tests/`](tests/) | Software, partition, loss, provenance, and manuscript checks. |

## Development and related components

For general package development, install the test extra and run the repository gate before a commit:

```bash
python3 -m pip install -e ".[test]"
./scripts/verify.sh
```

The gate runs the test suite, checks serving-path isolation, and builds the recorded ETo candidate site.
See [software reproducibility](docs/REPRODUCIBILITY.md) for the general environment contract.
The exact paper environment is pinned separately in `requirements-paper.lock`.

The repository also retains earlier research components:

- [Idaho reference-ETo outlook](docs/outlook/PRODUCT_CONTRACT.md) and [its evaluation protocol](docs/evaluation/OUTLOOK_PREREGISTRATION.md).
- [Historical OpenET information-value benchmark](docs/results/phase2_openet_value.md).
- [FAO-56 soil-water scaffold](docs/methods/HYBRID_MODEL_SCAFFOLD.md) and [separate residual-model protocol](docs/evaluation/OUTLOOK_RESIDUAL_MODEL_PROTOCOL.md).
- [NeuralHydrology provenance](docs/methods/NEURALHYDROLOGY_PROVENANCE.md) and [vendored pyfao56 provenance](vendor/pyfao56/UPSTREAM.md).

The outlook remains a research candidate with incomplete validation. These components do not supply additional evidence for the selective-correction paper.

## Citation and attribution

Cite the current manuscript as an unpublished research preprint. No arXiv identifier is assigned.

```bibtex
@misc{trotta2026mlet,
  author = {Trotta, Marco},
  title = {MLET: Selective Neural Residual Correction for Spatial Evapotranspiration},
  year = {2026},
  howpublished = {Research manuscript and accompanying code},
  url = {https://github.com/marco-trotta1/MLET}
}
```

Meetpal S. Kukal receives acknowledgement for research mentorship and earlier feedback.
The paper cites the source data and discloses AI assistance in coding, analysis, figures, and drafting.
New paper graphics adapt [figures4papers](https://github.com/ChenLiu-1996/figures4papers), with the [stated CC BY-NC 4.0 license](manuscript/licenses/figures4papers_CC-BY-NC-4.0.txt).
The original MLET visuals and Irrigant logo remain separate existing assets.
The README wordmark is an original decorative SVG; its animation is not a model result.
No repository-wide license is currently declared. Vendored components retain their own licenses and provenance.

This README uses [Chronos](https://github.com/amazon-science/chronos-forecasting), [TimesFM](https://github.com/google-research/timesfm), and [NeuralHydrology](https://github.com/neuralhydrology/neuralhydrology) as structural precedents.
Their paper links, concise usage paths, and citation sections inform the organization. Their models and results are not MLET baselines.
