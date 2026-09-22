# Neural covariate sensitivity

Declared on 2026-09-22 after the original and tree/ridge sensitivity results.
This is a post hoc mechanism check, not confirmatory validation.

Refit both declared neural architectures after omitting VPD.
Use all three original seeds, unchanged folds, and unchanged optimization settings.
Retain all rows and targets.
Run each fit once and retain all results.
Report the paired change against each corresponding original neural model.
Do not select a seed, epoch, architecture, or covariate using these outcomes.
