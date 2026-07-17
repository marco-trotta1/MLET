# Idaho Outlook Residual-Model Protocol

**Frozen:** 2026-07-17  
**Status:** prospective, non-serving research protocol; it reports no model skill result.

## Purpose and boundary

The Idaho outlook's operational research baseline remains the weather-driven ASCE short-reference ETo calculation and its transparent ETc/conditional-ETa scenario layers. This protocol tests a learned *residual* only to the physical p50 of the explicitly named `eta_well_watered_mm` scenario, against the matching `declared_well_watered_scenario_target`. It cannot be relabelled as a generic future actual-ET model. It does not replace, blend into, or otherwise alter an outlook build, static research-candidate map, Helios integration, Irrigant input, or irrigation decision.

The experiment asks whether a quantile residual model improves held-out error over the unmodified physical p50 while retaining honest intervals. A negative or inconclusive result remains a valid result.

## Frozen data and split protocol

`mlet evaluate-outlook-residual --cases ARCHIVE.json --out REPORT.md` accepts a strict schema-version-1 archive. It requires a classification (`real_archived` or `software_fixture`), a versioned/checksummed provenance receipt, a frozen split ID, train/calibration issue-time cutoffs, named held-out spatial blocks, named held-out calendar seasons, and immutable cases. A real archive must also include a relative, checksummed Task 8 hindcast evidence bundle. MLET reconstructs that bundle and refuses any hindcast fixture or source that was available after issue time. A software fixture must set this field to `null` and remains permanently non-scientific.

Each case records only these issue-time features, with a strict-UTC availability timestamp for every feature: `lead_day`, `eto_p50`, `eto_spread`, `precip_p50`, `crop_fraction`, `kc`, `taw_mm`, `initial_depletion_mm`, and `eta_analysis_age_days`. No feature may have become available after its issue time. Training cases must be at or before the frozen training cutoff; calibration cases must be at or before the calibration cutoff. Held-out spatial blocks or seasons are forbidden from training and calibration, while every test case must occupy at least one declared holdout. Explicit `train`, `calibration`, and `test` roles prevent a calibration or test row from silently becoming training data.

The experiment records the complete case-file SHA-256, canonical report digest, split ID/cutoffs, feature list, model settings, random seed, Python, NumPy, and scikit-learn versions. The archived raw data itself is not committed here.

## Model and calibration

The fitted target is `target_mm - physical_p50`. A `StandardScaler` and three `GradientBoostingRegressor(loss="quantile")` estimators (0.1, 0.5, 0.9) are fit on training cases only with seed `20260717`. Their residual quantiles are added back to the unchanged physical p50. A symmetric absolute-residual conformal inflation is estimated on the separate calibration partition at 80% nominal coverage and applied only when scoring test cases.

Held-out output reports physical versus residual p50 MAE, p10-p90 empirical coverage, and interval width by lead day and season. These are experiment diagnostics—not an operational forecast layer.

## Pre-registered candidate gates

A real archive is computationally eligible for independent review only if all 20 held-out lead days improve p50 MAE, all lead-day p10-p90 coverages lie within 0.70–0.90 of the 0.80 target, no held-out season has worse MAE than the physical baseline, and every feature availability time is at or before issue time. Missing partitions, leakage, missing lead metrics, or failed thresholds are blockers. A `software_fixture` is permanently non-scientific even if its values satisfy a gate.

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
