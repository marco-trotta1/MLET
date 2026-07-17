# Idaho Outlook Residual-Model Protocol

**Frozen:** 2026-07-17
**Status:** prospective, non-serving research protocol; it reports no model skill result.

## Purpose and boundary

The Idaho outlook's operational research baseline remains the weather-driven ASCE short-reference ETo calculation and its transparent ETc/conditional-ETa scenario layers. This protocol tests a learned *residual* only to the physical p50 of the explicitly named `eta_well_watered_mm` scenario, against the matching `declared_well_watered_scenario_target`. It cannot be relabelled as a generic future actual-ET model. It does not replace, blend into, or otherwise alter an outlook build, static research-candidate map, Helios integration, Irrigant input, or irrigation decision.

The experiment asks whether a quantile residual model improves held-out error over the unmodified physical p50 while retaining honest intervals. A negative or inconclusive result remains a valid result.

## Frozen data and split protocol

`mlet evaluate-outlook-residual --cases ARCHIVE.json --out REPORT.md` accepts a strict schema-version-1 archive. It requires a classification (`real_archived` or `software_fixture`), a versioned/checksummed provenance receipt, a frozen split ID, train/calibration issue-time cutoffs, named held-out spatial blocks, named held-out calendar seasons, and immutable cases. The split ID is an allow-listed preregistered Idaho tile assignment: an archive cannot invent its fold labels or seasons.

A real archive must include a relative, checksummed Task 8 hindcast evidence bundle and its false-only authority request. MLET reconstructs these archive-local diagnostics and records its evaluation digest, case digests, authority-request digest, and provenance revision. Every ML case cites one of those Task 8 case digests plus one relative, checksummed feature-receipt artifact for every feature; each receipt binds case ID, feature value, availability time, URI, and source revision. It must also provide a relative, checksummed `target_receipt` artifact with kind `idaho_outlook_residual_target_receipt`. That target receipt binds the residual case, the Task 8 case digest, layer, target kind, lead, valid date, spatial block, target value, `target_available_at`, URI, and source revision. Training targets must have `target_available_at <= train_cutoff`; calibration targets must have `target_available_at <= calibration_cutoff`; test targets may arrive later for evaluation but still require the bound receipt. Its complete issue time, valid date, spatial group, feature values/availability, physical p50, target, target availability, and receipt digests are content-addressed in the candidate report. These checks detect accidental corruption, but they do **not** establish independent provenance: a caller can author both rows and receipts. Consequently, no repository ML code path can mark an archive `external_release_eligible`; a separately controlled archive-reconstruction authority must retrieve raw Task 8/source artifacts, rebuild every row and target receipt, and issue `independently_reconstructed_archive_authority_receipt` before any separately trusted release review. A software fixture must set the hindcast field to `null` and remains permanently non-scientific.

Each case records only these issue-time features, with a strict-UTC availability timestamp for every feature: `lead_day`, `eto_p50`, `eto_spread`, `precip_p50`, `crop_fraction`, `kc`, `taw_mm`, `initial_depletion_mm`, and `eta_analysis_age_days`. `lead_day` is an integer 1–20; `valid_date` must equal `outlook_valid_date(issue_time, lead_day)`: the lead offset from the issue instant's `America/Boise` civil date, including MST/MDT transitions. The evaluator derives the meteorological season from that Idaho-local date rather than trusting a label. No feature may have become available after issue time. Training is at or before its cutoff; after a one-day temporal gap, calibration is between the cutoffs; after another gap, test begins. Training and calibration exclude both held-out geography and season, and each test row belongs to both. All declared blocks and seasons must occur in test data.

The experiment records the complete case-file SHA-256, canonical report digest, split ID/cutoffs and fold IDs, feature schema, exact estimator hyperparameters, seed, fitted calibration method/rank/value/case hashes, Task 8/source-receipt revisions and hashes, target-receipt hashes and availability times, row hashes, and Python/NumPy/scikit-learn versions. The archived raw data itself is not committed here.

## Model and calibration

The fitted target is `target_mm - physical_p50`. A `StandardScaler` and three `GradientBoostingRegressor(loss="quantile")` estimators (0.1, 0.5, 0.9; `n_estimators=80`, `max_depth=2`, `min_samples_leaf=2`, `learning_rate=0.05`) are fit on training cases only with seed `20260717`. Their residual quantiles are added back to the unchanged physical p50. A symmetric **lead-stratified** split-conformal inflation is estimated on the separate calibration partition at 80% nominal coverage using the finite-sample order statistic `k = min(n, ceil((n + 1) * 0.80))` of sorted nonconformity scores for that exact lead day. It is applied only when scoring test cases at the same lead, preserving p10 ≤ p50 ≤ p90.

The split-conformal interval is **lead-stratified, not season-conditioned**. Held-out output lists every preregistered lead day and held-out season. Lead-day metrics require at least 5 calibration and 5 test cases for that exact lead; season diagnostics require at least 20 held-out test cases for that exact calendar season. There is deliberately no seasonal calibration-support claim because held-out seasons are excluded from calibration. Underpowered strata remain named with `n` but no metric and create explicit blockers rather than silently contributing a claim. These are experiment diagnostics—not an operational forecast layer.

## Pre-registered candidate gates

A real archive can satisfy the local numerical diagnostics only if all 20 support-qualified held-out lead days improve p50 MAE, all lead-day p10-p90 coverages lie within 0.70–0.90 of the 0.80 target, no support-qualified held-out season has worse MAE than the physical baseline, every required lead/test support threshold is met, every feature availability time is at or before issue time, and every training/calibration target receipt is available by its frozen cutoff. Missing partitions, leakage, a missing/mutated/fabricated target receipt, a named unsupported stratum, missing lead metrics, or failed thresholds are blockers. A `software_fixture` is permanently non-scientific even if its values satisfy a gate. Local numerical success is never an eligibility or release conclusion.

## External authority boundary

MLET is inside the evaluator threat boundary and never writes `promotion: true`, `external_release_eligible: true`, a validated ML claim, or a production ML claim. Each run writes a canonical adjacent `<report>.authority_request.json` with both values literally `false`, an evidence-bound digest, candidate-report SHA-256, and all blockers, including `requires_independently_reconstructed_archive_authority`. Its writer reconstructs the report from the archive before serialization, so caller mutations of an in-memory report cannot create a local true claim.

An external archive-reconstruction authority must first independently retrieve the raw Task 8 cases and source artifacts, verify source checksums/availability, reconstruct the ML rows and target receipts byte-for-byte, and issue a distinct signed or auditable `independently_reconstructed_archive_authority_receipt`. Only then may a separately controlled release authority verify the independent receipt, digest, and frozen gates and issue `separately_trusted_release_validation_receipt`. Neither receipt is parsed as a local promotion route, and neither authorizes the MLET map, forecast build, Helios, or Irrigant to consume this experiment. Any future integration requires a separately reviewed product contract and release process.

## Reproducible software-fixture smoke test

```bash
python3 -m mlet evaluate-outlook-residual \
  --cases examples/outlook/hindcast_cases.json \
  --out /private/tmp/idaho_outlook_residual.md
```

The existing zero-case fixture exits with status 1 after writing a visibly non-scientific, non-promoted report and authority request. It is a software test only and must never be cited as model performance.
