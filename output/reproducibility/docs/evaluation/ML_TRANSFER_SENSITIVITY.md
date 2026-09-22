# Exploratory covariate sensitivity

This extension follows inspection of the raw covariates on 2026-09-22.
The original protocol and original-data run remain unchanged.
It is post hoc and cannot supply an independent confirmatory claim.

The variable workbook specifies kPa for vapor pressure deficit and actual vapor pressure.
The manilacotton station contains vapor pressure deficits above 20 kPa and negative actual vapor pressure.
Do not infer a conversion factor or silently repair the archive.

Run the original folds with the VPD feature omitted from both training and testing.
Retain all target values and all 7,923 rows.
Compare weather ridge, combined ridge, weather boosting, direct boosting, residual boosting, and gated residual boosting.
Use the original fixed hyperparameters and nested gate selection.
Also clip each weather feature to its training 1st and 99th percentiles before fitting the original ridge models.
This is a generic input-support control, not a reconstruction of meteorology.

Report original errors with the suspect station excluded from scoring, without retraining.
Separate this descriptive influence calculation from the actual no-VPD refits.
Quantify the fraction of squared-error excess attributable to that station.
Audit negative actual vapor pressure across all selected rows.
Save the metadata evidence and all sensitivity predictions.
Do not run new model families or tune parameters after seeing sensitivity outcomes.
