# When Should a Satellite Estimate Be Changed? Stress-Testing Neural Corrections for Evapotranspiration

Marco Trotta · Irrigant · m@irrigant.xyz

The canonical paper is [the LaTeX source](arxiv/mlet_preprint.tex). The compiled PDF is [available here](../output/pdf/mlet_preprint.pdf).

The study evaluates selective corrections to OpenET estimates on 16,366 flux-tower observations from 151 stations. Its main predeclared comparison finds 0.0414 mm/day lower station-macro MAE when SupportGain is trained on cropland stations, with a 95% spatial-group interval from 0.0085 to 0.0788. The interval conditions on the fitted models. SupportGain was selected using earlier outcomes from this archive, including the cropland test rows. The interval does not account for this selection.

None of 40 preplanned temporal comparisons passes Holm correction. That test family does not test whether SupportGain is better than Gain. In a post hoc five-fold spatial holdout, the clean-input difference is inconclusive. Under a wind input multiplied by 3.6, SupportGain lowers station-macro MAE by 0.148 mm/day, with a simultaneous 95% interval from 0.070 to 0.226. It accepts 9.3% of corrections, compared with 51.8% for Gain. The transformation is controlled and does not estimate natural fault prevalence.

At one held-out station, Gain accepts all 32 records with physically invalid weather. It predicts a mean benefit of 0.83 mm/day, but its corrections raise mean absolute error by 21.6 mm/day versus OpenET. This single station does not establish a general fault rate or device failure.

The preprint does not establish unseen-site transfer, forecast skill, irrigation status, or irrigation response. It has not been submitted or peer reviewed. See the [reproduction instructions](REPRODUCIBILITY.md), [limitations](LIMITATIONS.md), and [literature positioning](../docs/evaluation/ML_LITERATURE_POSITIONING.md).
