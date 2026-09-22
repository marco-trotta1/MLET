# Study limitations

The current evidence is exploratory and uses an already inspected environmental benchmark.
The selective protocol precedes its new run, but the matched-budget analysis follows the fixed-threshold outcomes.
Neither step supplies an independent confirmation dataset.

The data contain sparse satellite validation dates from 85 stations.
They do not provide complete temporal sequences or reliable irrigation-action labels.
Cropland classification does not establish irrigated status.
The complete-weather selection can favor particular sites and instruments.

The three-seed residual ensemble and the selector hyperparameters are fixed.
This is not an exhaustive architecture comparison.
The study does not implement the leading deferral surrogates, GeoQ, or graph neural processes.
It cannot establish superiority over those methods or novelty of the deferral decision rule.

Synthetic input faults preserve labels and the satellite fallback.
They measure input-corruption behavior, not the physical effect of weather changes or real fault prevalence.
The source of the negative vapor-pressure exports remains unverified at instrument level.

Bootstrap intervals condition on fitted models, partitions, and selector ranks.
They omit retraining uncertainty and have no multiple-comparison adjustment.
The small later-year and cropland populations constrain generalization.
The upstream OpenET development history can also overlap this archive.

The original ETo outlook remains a negative diagnostic from one issue, one station, and 20 targets.
Its support gate remains incomplete.
The present work does not establish operational forecast skill, water savings, or irrigation decisions.
