<picture>
  <source media="(prefers-reduced-motion: reduce)" srcset="docs/assets/mlet-wordmark-static.svg">
  <img src="docs/assets/mlet-wordmark.svg" alt="MLET: Machine Learning Evapotranspiration. Learn the correction. Test the transfer." width="1080">
</picture>

# MLET: Target-Population Training for Selective Evapotranspiration Correction

**[Paper](output/pdf/mlet_arxiv_preprint.pdf) · [Source package](output/arxiv/mlet_preprint_source.tar.gz) · [Reproduction](manuscript/REPRODUCIBILITY.md) · [Primary result](docs/results/ml_tier1_cropland/README.md) · [Static graphic](docs/assets/mlet-wordmark-static.svg)**

MLET studies when a neural residual model should change an OpenET estimate.
The primary result tests whether crop-only training improves SupportGain on held-out Croplands rows.

| Training arm | Station-macro MAE | Pooled MAE | Station-weighted acceptance |
| --- | ---: | ---: | ---: |
| All-station SupportGain | 0.8291 mm/day | 0.8333 mm/day | 64.1% |
| Cropland-only SupportGain | 0.7877 mm/day | 0.7941 mm/day | 57.4% |

The predeclared paired difference is 0.0414 mm/day in favor of crop-only training.
Its 95% spatial-group bootstrap interval is 0.0085 to 0.0788 mm/day.
It uses 3,234 rows from 49 stations and 24 groups, with 2,000 draws and seed `20261005`.
The interval conditions on fitted models and selectors. Stations recur across years.
SupportGain was chosen using earlier test outcomes from this archive, including these crop test rows.
The interval does not include uncertainty from that choice.

The [cropland report](docs/results/ml_tier1_cropland/README.md) contains the predictions, receipts, and figure.
The [Tier 1 report](docs/results/ml_tier1_gridmet_10member/README.md) covers the all-station rolling evaluation.
The [corrected stuck-wind report](docs/results/ml_tier1_gridmet_stuck_corrected/README.md) audits the daily fault transform.
The [split sensitivity report](docs/results/ml_tier1_gridmet_sensitivity/README.md) covers ten split seeds at three proximity thresholds.
The [natural archive fault report](docs/results/ml_tier1_selective/README.md) describes one held-out station with 32 corrupted rows.
The [corrected measured-weather report](docs/results/ml_tier1_selective_corrected/README.md) reports the exploratory implementation correction.
The [natural violation extension](docs/results/ml_tier1_natural_violations/README.md) tests 133 other invalid rows from 17 groups.
The [Tier 3 report](docs/results/ml_tier3_gridmet/README.md) compares tuned and standard selector baselines.
The [risk-coverage report](docs/results/ml_tier3_gridmet_risk_coverage/README.md) reports fixed gates, curves, and intervals.
The [data card](docs/data/DATA_CARD.md) documents the physically screened gridMET cohort.

**Marco Trotta · Irrigant · [m@irrigant.xyz](mailto:m@irrigant.xyz)**

The manuscript is a preprint draft. It has no arXiv identifier or peer-reviewed acceptance.
Cropland labels do not identify irrigation, and this study does not establish performance on irrigated fields.

## Research question

**Does training on the target land-cover population improve selective evapotranspiration correction?**

For satellite estimate $o$, neural correction $g(x)$, and selector $a(x)$, the prediction is

$$\hat y(x) = o + a(x)g(x), \qquad a(x)\in\lbrace 0,1\rbrace.$$

Rejecting a correction returns OpenET. The benefit target is the absolute-error reduction,

$$D(x,y)=|y-o|-|y-o-g(x)|.$$

A positive value means the correction improves on OpenET. Low predictor error and positive correction benefit are different targets.

The study makes one predeclared target-population comparison. It also examines selector transfer under rolling time splits and controlled input changes.
It does not introduce a new deferral algorithm or establish a universally better ET estimator.
See the [literature comparison](docs/evaluation/ML_LITERATURE_POSITIONING.md).

## Method and data

The primary predictor is a ten-member residual ensemble with two 32-unit ReLU layers per member.
It uses seven inputs, Adam, training-only standardization, and a fixed 120-iteration limit.
The fixed seeds run from `20260713` through `20260722`.

| Method | Correction rule |
| --- | --- |
| OpenET | Return the satellite estimate. |
| Full | Apply the ensemble mean correction. |
| Gain | Accept when a fitted regressor predicts positive benefit. |
| SupportGain | Require positive predicted benefit and acceptable five-neighbor distance. |
| Tier 3 selectors | Compare tuned, monotone, augmented, sign-classifier, and conformal baselines. |

The study joins the OpenET validation archive with processed flux measurements.
The physical screen retains 16,366 rows from 151 stations and 102 proximity groups.
Rolling tests from 2012 through 2020 contain 7,842 rows from 101 stations and 64 groups.
The Croplands test subset contains 3,234 rows from 49 stations and 24 groups.

The [OpenET archive](https://doi.org/10.5281/zenodo.10119477) and [processed flux archive](https://doi.org/10.5281/zenodo.7636781) supply the measurements.
See the [data card](docs/data/DATA_CARD.md) and the frozen [cropland protocol](docs/evaluation/ML_TIER1_CROPLAND_TRAINING_PROTOCOL.md).

## Main findings and limits

The crop-only SupportGain model has lower station-macro MAE than the saved all-station SupportGain model on the shared crop test rows.
This is the primary result. It supports target-population training within this archive.
The interval does not include model refitting or method-selection uncertainty. No independent dataset confirms the result.

Across 30 split and proximity settings, the clean SupportGain advantage over Gain averages 0.00438 mm/day, with SD 0.00289.
Only one of 30 group-bootstrap intervals excludes zero.
SupportGain has lower point MAE than Gain in all 30 settings for each of 12 synthetic weather transforms.
The primary one-sided family tests whether Gain variants beat SupportGain. It does not test SupportGain superiority.
These repeated settings use the same rows, and the transforms hold fitted models fixed. They do not estimate natural fault prevalence.

An exploratory five-fold spatial holdout finds no clear clean difference between Gain and SupportGain.
The simultaneous clean interval is -0.0069 to 0.0186 mm/day.
Four fixed unit-error transforms have positive simultaneous intervals, with lower SupportGain acceptance.
At wind x3.6, SupportGain accepts 9.3% of corrections; under the Fahrenheit and VPD transforms, it accepts less than 0.3%.
These post hoc results use the same archive and condition on fitted models.
See the [spatial holdout report](docs/results/ml_tier1_spatial_holdout_sensitivity/README.md).

One natural archive fault contains 32 rows from one held-out station.
Gain accepts every correction on those rows and has 22.681 mm/day station-macro MAE.
SupportGain rejects them and returns OpenET, which scores 1.095 mm/day.
This case has one spatial group and no multi-group uncertainty interval.
Outside this known station, SupportGain improves on Gain by 0.0151 mm/day across 133 rows and 17 groups.
The paired group interval is 0.0000 to 0.0336 mm/day. Only two groups have nonzero differences.
Unchanged OpenET has lower point error than both selectors on these rows.
This exploratory extension does not confirm a broad natural-fault advantage.

The Tier 3 family has 52 planned comparisons and uses Holm correction.
One adjusted comparison favors TunedGain over Gain under a synthetic temperature fault.
TunedGain still has 0.5553 mm/day higher MAE than SupportGain under that fault.

The evidence tests temporal transfer, not unseen-station transfer or forecasting.
Synthetic faults do not estimate sensor-fault prevalence.
The land-cover field does not establish irrigation status.
The study does not establish irrigation benefits, water savings, or upstream OpenET independence.
See [study limitations](manuscript/LIMITATIONS.md).

## Reproduce the evidence

Use Python **3.13.5** and the pinned dependencies in `requirements-paper.lock`.
The [reproduction guide](manuscript/REPRODUCIBILITY.md) lists protocols, saved evidence, and build steps.
Completed fit directories refuse overwrite. The package does not include raw weather archives.

## Repository map

| Path | Content |
| --- | --- |
| [`scripts/`](scripts/) | Frozen experiment runners, analyzers, and figure builders. |
| [`docs/evaluation/`](docs/evaluation/) | Scientific protocols and literature positioning. |
| [`docs/results/ml_tier1_cropland/`](docs/results/ml_tier1_cropland/) | Primary target-population result and saved predictions. |
| [`docs/results/ml_tier1_gridmet_10member/`](docs/results/ml_tier1_gridmet_10member/) | Ten-member rolling results. |
| [`docs/results/ml_tier1_gridmet_stuck_corrected/`](docs/results/ml_tier1_gridmet_stuck_corrected/) | Exploratory daily stuck-wind correction. |
| [`docs/results/ml_tier1_spatial_holdout_sensitivity/`](docs/results/ml_tier1_spatial_holdout_sensitivity/) | Exploratory five-fold spatial comparison of Gain and SupportGain. |
| [`docs/results/ml_tier3_gridmet/`](docs/results/ml_tier3_gridmet/) | Tuned selectors and deferral baselines. |
| [`manuscript/arxiv/`](manuscript/arxiv/) | Canonical LaTeX, references, tables, and figures. |
| [`output/arxiv/`](output/arxiv/) | Submission source, metadata, and reproduction package. |

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
  title = {When Should a Satellite Estimate Be Changed? Stress-Testing Neural Corrections for Evapotranspiration},
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
