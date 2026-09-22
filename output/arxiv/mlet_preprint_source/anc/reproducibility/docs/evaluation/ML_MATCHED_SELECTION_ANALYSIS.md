# Matched acceptance analysis

This is a post hoc diagnostic specified after the fixed-threshold experiment.
The fixed-threshold scores show different fallback frequencies.
This diagnostic asks whether rejecting more corrections explains their risk differences.
It does not fit another neural model or adjust a deployed selector.

Use every saved condition, both input specifications, and both outer evaluations.
Rank spread divided by its inner 95th-percentile threshold, distance divided by its corresponding threshold, and negative predicted gain.
Lower rank means earlier acceptance.
Use station weights and acceptance budgets 0, 0.1, ..., 1.
Give the boundary observation a fractional acceptance probability to match the station-weighted budget exactly.
Report expected loss under this randomized boundary decision, not loss from interpolating the two predictions.
The outer score distribution defines these label-free ranks. This is a transductive ranking diagnostic, not a preselected deployment threshold.

Report paired component-bootstrap intervals for spread versus support at the fixed 50% budget.
Keep the selectors fixed within each bootstrap sample.
Use 2,000 draws and seed 20260922.
These intervals condition on fitted models and ranks. They do not account for multiple comparisons or retraining.
Save every budget and condition, including cases that reverse the expected ordering.
