# Selective residual regression for spatial ET

Research date: September 22, 2026.
Discovery uses alphaXiv and arXiv. Technical claims use the underlying papers.

## The narrow question

When a satellite estimate already exists, can a neural correction selector predict the benefit of changing that estimate at an unseen station?
This is regression with model deferral under spatial shift.
The selector must compare two prediction errors. A low neural error alone does not establish an improvement.

## Closest methods

| Paper | Relevant mechanism | Relationship to MLET |
| --- | --- | --- |
| Mao, Mohri, and Zhong, 2024. [Regression with Multi-Expert Deferral](https://arxiv.org/abs/2403.19494). [ICML version](https://proceedings.mlr.press/v235/mao24d.html). [alphaXiv](https://www.alphaxiv.org/abs/2403.19494). | Learns whether to use a predictor or another expert. Covers regression and two-stage learning. | Establishes the surrounding problem. MLET does not claim to invent deferral, its optimal decision rule, or consistency theory. |
| Sokol, Moniz, and Chawla, 2024. [Conformalized Selective Regression](https://arxiv.org/abs/2402.16300). [alphaXiv](https://www.alphaxiv.org/abs/2402.16300). | Uses prediction intervals to rank regression reliability and studies error versus retained coverage. | Motivates testing uncertainty rankings. MLET scores the complete fallback system and claims no conformal coverage guarantee. |
| Nguyen et al., 2026. [GeoQ](https://arxiv.org/abs/2608.21652). [alphaXiv](https://www.alphaxiv.org/abs/2608.21652). | Uses cross-fitted errors, representation displacement, local support, and conditional quantile increments for scientific surrogates. | Motivates a support control. MLET's five-neighbor distance is deliberately simpler and is not a GeoQ reproduction. |
| Meyer and Pebesma, 2020. [Predicting into unknown space?](https://arxiv.org/abs/2005.07939). | Defines an applicability domain from predictor-space dissimilarity and validation-aware thresholds. | Establishes that spatial location and covariate support differ. MLET does not claim novelty for distance thresholds. |
| Lakshminarayanan, Pritzel, and Blundell, 2016. [Deep Ensembles](https://arxiv.org/abs/1612.01474). | Combines independently trained neural predictors and studies uncertainty under distribution shift. | Motivates seed disagreement. MLET uses a three-seed mean-only residual ensemble, not the full heteroscedastic method. |
| de Mathelin et al., 2023. [Deep Anti-Regularized Ensembles](https://arxiv.org/abs/2304.04042). | Addresses overconfident ensemble predictions outside training support. | Prevents treating ensemble spread as a guaranteed error detector. MLET does not implement their regularizer. |
| Hu et al., 2023. [Graph Neural Processes for Spatio-Temporal Extrapolation](https://arxiv.org/abs/2305.18719). [alphaXiv](https://www.alphaxiv.org/abs/2305.18719). | Models sparse environmental sensors through graph context and latent predictive distributions. | Provides a real spatial prediction example. MLET's sparse satellite-day table does not support a matched reproduction without a new temporal context dataset. |
| Xu et al., 2020. [How Neural Networks Extrapolate](https://arxiv.org/abs/2009.11848). [alphaXiv](https://www.alphaxiv.org/abs/2009.11848). | Analyzes extrapolation of ReLU networks and graph networks. | Connects input support to neural behavior. MLET's tests concern a finite fitted ensemble, not their asymptotic theorem. |

## What this study can contribute

The candidate contribution is empirical: whether support screening and neural disagreement identify the same baseline-relative failures in a real environmental archive.
The comparison uses a fixed satellite fallback, matched neural predictions, geographic grouping, later years, and controlled input faults.
The no-VPD arm tests whether the conclusion survives removal of the already discovered anomaly.
All selectors, thresholds, fault magnitudes, and reporting rules are fixed before the new run.
The earlier archive remains previously inspected. The new protocol does not make it independent confirmation.

## Claims that the evidence cannot establish

The study does not establish a new deferral algorithm, new uncertainty theory, or a universally superior neural architecture.
It does not establish general gains for irrigated fields, forecasting, or irrigation interventions.
Controlled input faults are paired robustness probes, not independent datasets or estimates of fault prevalence.
ICML-level generality would require further independent datasets and matched implementations of leading deferral methods.
The literature search does not prove priority for a specific empirical observation.
