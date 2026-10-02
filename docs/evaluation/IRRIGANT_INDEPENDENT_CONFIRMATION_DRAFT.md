# Irrigant independent confirmation protocol

**Status: DRAFT. NOT REGISTERED. No confirmation data are approved or accessed.**

This draft defines a future forecast study. It does not change the locked Round 01 study or authorize data access.

## Claims and scope

| Claim | Population | Endpoint | Status |
| --- | --- | --- | --- |
| Primary: unfamiliar-site forecast transfer | Independently verified sites absent from all model development and selection | Exact measured soil-water tension at 48 hours, compared with persistence | Proposed. Site supply and practical margin are open. |
| Secondary: familiar-site temporal transfer | Sites used for development, with later periods held out | Exact measured soil-water tension at 48 hours | Proposed. This does not support an unfamiliar-site claim. |
| Irrigation policy effect | Fields with verified irrigation actions and outcome measurements | Water use, crop response, or another approved policy endpoint | Out of scope for this forecast study. Requires a separate protocol. |

The primary claim concerns forecast error only. It does not establish irrigation advice, causal response, water savings, or crop benefit.

Use centibars for the primary tension endpoint. Record the sensor's native unit and conversion. Freeze the conversion before enrollment.

## Historical evidence boundary

MLET has inspected its archive and selected SupportGain using prior test outcomes, including the cropland test rows. Its results cannot serve as untouched confirmation evidence.

The MLET archive tests evapotranspiration correction. It does not provide an independent soil-water-tension forecast test.

The Irrigant Round 01 record remains a historical temporal evaluation. Its independently verified site count is zero. Keep its locked-data and promotion gates closed.

Do not infer irrigation status from a crop or land-cover label. Do not count repeated rows, forecast horizons, seeds, or data transforms as independent sites.

Use MLET only to inform method selection, baseline choice, and reporting risks. Record that SupportGain selection used inspected test outcomes.

## Proposed design

### Population and split

Define one independent cluster as a field or site with a distinct operator and irrigation-management unit. Freeze the cluster rule before enrollment.

Assign every cluster to development, familiar-site temporal evaluation, or unfamiliar-site confirmation. Do not place one cluster in multiple roles.

Verify each unfamiliar cluster's identity and independence before enrollment. Keep site identity and confirmation labels with an approved data custodian.

Train, select, calibrate, and tune only with approved development data. Keep confirmation outcomes hidden until the method and predictions are locked.

### Primary comparison

Compare one frozen forecast method with a persistence baseline at 48 hours. Persistence uses the latest eligible measured tension at or before issue time.

For each eligible issue, target the same sensor channel and registered depth at issue time plus 48 hours. Select the nearest valid measurement within a timing tolerance fixed before enrollment.

Report the site-cluster macro MAE difference: persistence MAE minus method MAE. A positive value favors the method.

Use paired resampling over independent confirmation clusters for the 95% interval. Keep each cluster's records together.

Before enrollment, an agronomist must set the practical improvement margin, δ. The primary claim passes only when the 95% interval's lower bound exceeds δ.

Report the estimate, interval, cluster count, missingness, and every failed or inconclusive result. Report row-level metrics as descriptive only.

### Method and outcome lock

Before enrollment, record the method name, source commit, model and configuration hashes, input list, unit conversion, training data version, and software versions.

Freeze the issue schedule, eligible-input rule, persistence rule, missing-data rule, endpoint timing tolerance, aggregation, interval method, and analysis code.

Save every issued forecast with its issue time, target time, input receipt times, model hash, and forecast value. Do not replace a failed or missing forecast silently.

The custodian releases confirmation labels only after the evaluator deposits prediction files, analysis code, and checksums.

## Power and recruitment

Use independent confirmation clusters as the sample units. Do not use rows, days, sensors, horizons, repeated fits, or random seeds as extra units.

Estimate paired cluster-level variance from approved development data without viewing confirmation outcomes. Set the practical margin, δ, before this estimate informs recruitment.

Calculate the required number of clusters from the approved δ, paired variance, type-I error, and target power. Record the method and assumptions.

The margin, variance, target power, type-I error, cluster count, site availability, recruitment plan, and budget remain OPEN. No defensible sample size exists yet.

## Evidence gaps and blockers

| Requirement | Current evidence | Status |
| --- | --- | --- |
| Untouched, approved tension data | No approved confirmation dataset is identified | BLOCKED_EXTERNAL |
| Independent verified sites | Round 01 records zero verified sites | BLOCKED_EXTERNAL |
| Site and management identity | No confirmation roster or adjudication is available | OPEN |
| Sensor depth and calibration | No confirmation sensor records are available | OPEN |
| Observation and receipt clocks | No approved timestamp records are available | OPEN |
| Practical improvement margin | No agronomist-approved value exists | OPEN |
| Variance and power inputs | No approved blinded variance or margin exists | OPEN |
| Recruitment and budget | No approved site commitments or budget exist | OPEN |
| Consent and data custody | No confirmation-specific approval is recorded | OPEN |
| Irrigation actions and policy outcomes | No verified application records are available | OUT OF SCOPE |

Do not access locked data or open promotion gates to fill these gaps. Record new evidence and approval before changing a status.

## Field collection checklist

1. Record the site, field, operator, and irrigation-management cluster identifiers.
2. Record the identity review, independence decision, reviewer, and date.
3. Record sensor make, model, serial number, channel, native unit, and installed depth.
4. Record calibration checks, reference instrument, date, operator, and certificate.
5. Record observation time, receipt time, UTC offset, clock source, raw value, unit, and quality flags.
6. Record forecast issue time, target time, model hash, available inputs, and input receipt times.
7. Measure the endpoint at the registered sensor and depth near the 48-hour target.
8. Record irrigation plans, applied amount, flow, pressure, start and stop times, and operator actions.
9. Record maintenance, sensor movement, deviations, missing observations, and reasons.
10. Record consent, permitted use, retention period, export path, and deletion instructions.
11. Store source files and prediction files with checksums and access logs.
12. Keep forecast error separate from water-use, yield, and irrigation-policy outcomes.

## Existing protocol references

- [ML transfer protocol](ML_TRANSFER_PROTOCOL.md)
- [Tier 1 cropland training protocol](ML_TIER1_CROPLAND_TRAINING_PROTOCOL.md)
- [Phase 2 preregistration](PREREGISTRATION.md)
- [MLET primary result and limits](../results/ml_tier1_cropland/README.md)

These documents describe inspected historical analyses. They do not register or validate this proposed confirmation study.
