# Exploratory Full-model crop-training comparison

Status: exploratory. The point estimates were reviewed before interval analysis.
This audit does not change the frozen SupportGain primary comparison.

## Question

Estimate the spatial-group uncertainty for the planned descriptive comparison of Full models.
The models use the same test rows and differ only in their training population.
The Full method applies every neural correction without selector rejection.

## Outcome and analysis

Define the difference as all-station Full MAE minus cropland-only Full MAE.
Positive values favor crop-only training.
Use station-macro MAE on the saved 3,234 test rows from 49 stations and 24 groups.
Keep each station and all its test rows within its spatial group.
Sample the 24 groups with replacement for 2,000 percentile-bootstrap draws.
Use seed 20261006.
Report the point difference and the 95% interval.
Do not calculate a p-value or add this comparison to a test family.

This interval conditions on the fitted models.
The point estimates were visible before the interval was defined, so treat the interval as exploratory.
Do not use it as independent confirmation.
