# MLET: Selective Neural Residual Correction for Spatial Evapotranspiration

Marco Trotta · Irrigant · m@irrigant.xyz

The canonical manuscript is [the LaTeX source](arxiv/mlet_preprint.tex).
Its compiled PDF is `output/pdf/mlet_preprint.pdf`.
Meetpal S. Kukal receives acknowledgement for mentorship and earlier feedback.

The paper asks when a neural correction should change an existing satellite ET estimate at an unseen location.
It compares ensemble disagreement, input support, predicted relative benefit, uniform shrinkage, and clipped inputs.
Spatial cross-fitting supplies the selector targets without outer-label leakage.
A second evaluation also excludes later years from training.

The study keeps the original Irrigant branding and all five original graphics.
The reference-ETo outlook remains separate from the actual-ET neural task.
Its original diagnostic, spatial map, and support tensor remain in the appendix.
The retrospective actual-ET target does not establish forecast or irrigation skill.

The key ML finding concerns selector transfer under a controlled wind-input fault.
At equal 50% acceptance after VPD omission, the learned benefit ranking has higher error than the support ranking.
The paired difference is 0.243 mm/day, with interval [0.110, 0.412].
The comparison uses 7,873 matched observations, 84 stations, 62 proximity groups, and 2,000 paired bootstrap draws.
The later-year comparison does not confirm that ordering.
The paper retains that limit and the other negative results.

Read [the reproduction instructions](REPRODUCIBILITY.md), [limitations](LIMITATIONS.md), and [literature positioning](../docs/evaluation/ML_LITERATURE_POSITIONING.md).
