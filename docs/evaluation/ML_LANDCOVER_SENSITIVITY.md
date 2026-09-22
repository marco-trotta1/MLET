# Land-cover calibration control

Declared after the other results on 2026-09-22.
This is an exploratory baseline prompted by known OpenET forest biases.

Fit an independent intercept and slope for OpenET within each training land-cover class.
Use the original saved outer partitions and the same measured labels.
If a class has fewer than three training observations, use the global training affine fit.
Use the test station's archived general land-cover class only to select its fitted equation.
This baseline has extra static information relative to the main seven-input models.
It must not be described as a matched-information architecture comparison.
Report its performance in every split and in cropland and other-land-cover strata.
Do not adjust classes, coefficients, or fallback rules after inspecting test scores.
