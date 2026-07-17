# Idaho Outlook Residual-Model Protocol

**Frozen:** 2026-07-17  
**Status:** prospective, non-serving research protocol; it reports no model skill result.

## Purpose and boundary

The Idaho outlook's operational research baseline remains the weather-driven ASCE short-reference ETo calculation and its transparent ETc/conditional-ETa scenario layers. This protocol tests a learned *residual* only to the physical p50 of the explicitly named `eta_well_watered_mm` scenario, against the matching `declared_well_watered_scenario_target`. It cannot be relabelled as a generic future actual-ET model. It does not replace, blend into, or otherwise alter an outlook build, static research-candidate map, Helios integration, Irrigant input, or irrigation decision.

The experiment asks whether a quantile residual model improves held-out error over the unmodified physical p50 while retaining honest intervals. A negative or inconclusive result remains a valid result.

## Frozen data and split protocol

`mlet evaluate-outlook-residual --cases ARCHIVE.json --out REPORT.md` accepts a strict schema-version-1 archive. It requires a classification (`real_archived` or `software_fixture`), a versioned/checksummed provenance receipt, a frozen split ID, train/calibration issue-time cutoffs, named held-out spatial blocks, named held-out calendar seasons, and immutable cases. The split ID is an allow-listed preregistered Idaho tile assignment: an archive cannot invent its fold labels or seasons.

A real archive must include a relative, checksummed Task 8 hindcast evidence bundle and its false-only authority request. MLET reconstructs the bundle, requires it to have no computational blocker other than the separately trusted release-authority blocker, and records its evaluation digest, case digests, authority-request digest, and provenance revision. Every ML case cites one of those Task 8 case digests plus one relative, checksummed feature-receipt artifact for every feature; each receipt binds case ID, feature value, availability time, URI, and source revision. Its complete issue time, valid date, spatial group, feature values/availability, physical p50, and target are content-addressed in the candidate report. A caller-supplied JSON file without these bindings is rejected; it is not a scientific result or an external-authority-eligible candidate. A software fixture must set the hindcast field to `null` and remains permanently non-scientific.

Each case records only these issue-time features, with a strict-UTC availability timestamp for every feature: `lead_day`, `eto_p50`, `eto_spread`, `precip_p50`, `crop_fraction`, `kc`, `taw_mm`, `initial_depletion_mm`, and `eta_analysis_age_days`. `lead_day` is an integer 1–20; `valid_date` must equal `issue_date + lead_day`, and the evaluator derives the meteorological season from that date rather than trusting a label. No feature may have become available after issue time. Training is at or before its cutoff; after a one-day temporal gap, calibration is between the cutoffs; after another gap, test begins. Training and calibration exclude both held-out geography and season, and each test row belongs to both. All declared blocks and seasons must occur in test data.

The experiment records the complete case-file SHA-256, canonical report digest, split ID/cutoffs and fold IDs, feature schema, exact estimator hyperparameters, seed, fitted calibration method/rank/value/case hashes, Task 8/source-receipt revisions and hashes, row hashes, and Python/NumPy/scikit-learn versions. The archived raw data itself is not committed here.

## Model and calibration

The fitted target is `target_mm - physical_p50`. A `StandardScaler` and three `GradientBoostingRegressor(loss="quantile")` estimators (0.1, 0.5, 0.9; `n_estimators=80`, `max_depth=2`, `min_samples_leaf=2`, `learning_rate=0.05`) are fit on training cases only with seed `20260717`. Their residual quantiles are added back to the unchanged physical p50. A symmetric split-conformal inflation is estimated on the separate calibration partition at 80% nominal coverage using the finite-sample order statistic `k = min(n, ceil((n + 1) * 0.80))` of sorted nonconformity scores. It is applied only when scoring test cases, preserving p10 ≤ p50 ≤ p90.

Held-out output reports physical versus residual p50 MAE, p10-p90 empirical coverage, and interval width by lead day and season only for strata with adequate support: at least 5 calibration and 5 test cases per lead, and 20 calibration and 20 test cases per held-out season. Underpowered strata remain listed with `n` but no metric; they create explicit blockers rather than silently contributing a claim. These are experiment diagnostics—not an operational forecast layer.

## Pre-registered candidate gates

A real archive is computationally eligible for independent review only if all 20 support-qualified held-out lead days improve p50 MAE, all lead-day p10-p90 coverages lie within 0.70–0.90 of the 0.80 target, no support-qualified held-out season has worse MAE than the physical baseline, every required calibration/test support threshold is met, and every feature availability time is at or before issue time. Missing partitions, leakage, missing lead metrics, or failed thresholds are blockers. A `software_fixture` is permanently non-scientific even if its values satisfy a gate.

## External authority boundary

MLET is inside the evaluator threat boundary and never writes `promotion: true`, a validated ML claim, or a production ML claim. Each run writes a canonical adjacent `<report>.authority_request.json` with `promotion: false`, an evidence-bound digest, candidate-report SHA-256, and all blockers. Its writer reconstructs the report from the archive before serialization, so caller mutations of an in-memory report cannot create a local true claim.

Only a separately controlled external release authority may independently retrieve the archive, verify the digest and frozen gates, and issue a distinct signed or auditable `separately_trusted_release_validation_receipt`. That receipt is not parsed as a local promotion route, and it does not authorize the MLET map, forecast build, Helios, or Irrigant to consume this experiment. Any future integration requires a separately reviewed product contract and release process.

## Reproducible software-fixture smoke test

```bash
python3 -m mlet evaluate-outlook-residual \
  --cases examples/outlook/hindcast_cases.json \
  --out /private/tmp/idaho_outlook_residual.md
```

The existing zero-case fixture exits with status 1 after writing a visibly non-scientific, non-promoted report and authority request. It is a software test only and must never be cited as model performance.
