# ML transfer audit

Frozen before the new model comparison on 2026-09-22.
This is an exploratory extension of the previously inspected Phase 2 results.
It is not an independent preregistration or a new untouched dataset.

## Question

When does learned correction improve an existing satellite ET estimate at unseen stations?
Does correction remain useful when the test years also follow the training years?

## Data and estimand

Rebuild the original 7,923-row, 85-station complete-weather cohort from the two checksum-verified archives.
Retain the original measured labels, negative values, and complete-case rules.
Predict measured actual ET on the archived satellite observation dates.
Use the OpenET ensemble, reference ET, temperature, vapor pressure deficit, wind, and annual sine/cosine terms.
Do not claim an operational forecast or a causal irrigation response.

## Splits

Use the original ten station folds and seed 20260713 for direct reproduction.
Use a second ten-fold split with sites linked within 10 km in the same connected component.
The proximity split addresses nearby towers; it does not establish independence across regions.
For joint transfer, train only before 2019 and test from 2019 in withheld proximity groups.
Inner selection uses three disjoint proximity groups from the outer training data.
For joint transfer, inner training ends before 2016 and inner validation starts in 2016.
Never use outer test labels for selection, scaling, stopping, or correction strength.
Save every split and prediction.

## Models

Reproduce the original crop coefficient, weather ridge, direct OpenET, affine OpenET, and combined ridge.
Add a training median and weather-only histogram gradient boosting.
Tune combined ridge over alpha = 1, 10, 100, 1000 using inner station-macro MAE.
Compare direct and residual histogram gradient boosting with identical fixed capacity.
Use 150 iterations, learning rate 0.05, 7 leaves, minimum 30 rows per leaf, and L2 = 10.
Disable internal random-row early stopping.
Residual learning predicts measured ET minus the unchanged OpenET ensemble.
Compare direct and residual neural networks with identical capacity and optimization.
Use two 32-unit ReLU layers, Adam, learning rate 0.001, batch size 256, and 120 epochs.
Use the scikit-learn L2 penalty alpha = 0.001 and seeds 20260713, 20260714, 20260715.
Standardize inputs and targets from each training partition only.
Do not select epochs using test data.
Run each neural seed once and retain every result.

## Correction gate and mechanism

Estimate a scalar correction weight from inner out-of-group residual predictions.
For squared loss, lambda = clip(E[r*g] / E[g*g], 0, 1).
Use equal station weights for both expectations.
Apply the fixed lambda to a residual model refit on the outer training set.
Compare lambda = 0, lambda = 1, and the inner-estimated lambda.
Report the test moments as explanatory diagnostics, never as a deployable oracle.
An orthogonal rotation alone cannot improve isotropically regularized linear regression.
Demonstrate this equivalence with a numerical test instead of claiming an architecture contribution.

## Reporting

Primary metric: mean of station MAEs on the proximity split.
Report pooled MAE, RMSE, bias, station win counts, and cropland results on identical rows.
Use 2,000 paired proximity-component bootstrap draws, seed 20260922, for 95% intervals.
Bootstrap intervals condition on fitted models and do not include retraining uncertainty.
Report joint-transfer results separately because its test cohort differs.
Inspect weather support, station contributions, and correction-residual alignment.
Do not infer physical mechanisms from feature importance or orthogonality.
Keep inconclusive comparisons and failed corrections in the paper.
Record code hashes, archive hashes, package versions, training time, and batch inference time.
No paid compute or API training is required.
