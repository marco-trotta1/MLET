# MLET arXiv source

Title: When Should a Satellite Estimate Be Changed? Stress-Testing Neural Corrections for Evapotranspiration.
Author: Marco Trotta.
Affiliation: Irrigant, Idaho, USA.
Contact: m@irrigant.xyz.

Use `mlet_preprint.tex` as the main source file. The paper reports a predeclared comparison of all-station and cropland-only SupportGain training. The paired station-macro MAE improvement is 0.0414 mm/day, with a 95% spatial-group bootstrap interval from 0.0085 to 0.0788. It uses 3,234 cropland test rows, 49 stations, 24 groups, 2,000 bootstrap draws, and seed 20261005. The interval conditions on fitted models and selectors.
SupportGain was chosen using earlier test outcomes from this archive, including the cropland test rows. The interval does not account for this choice.

The paper reports fixed-input weather changes, one natural archive violation, and selector repair checks. The measured-weather study and its implementation correction remain exploratory. Tier 3 risk-coverage results, matched-budget analyses, and earlier benchmark and covariate analyses remain in the reproducibility package. The paper does not establish irrigated-crop performance, unseen-station transfer, or forecast skill.
An exploratory two-sided audit finds Holm-adjusted SupportGain advantages over Gain in 10 of 13 conditions and MonoGain in nine of 13. It finds no adjusted advantage over AugmentedGain. The outcomes were visible before this analysis, so it needs independent confirmation.

## Author and affiliation status

Dr. Meetpal S. Kukal declined co-authorship on September 21, 2026. Marco confirmed a single-author preprint with an acknowledgement on September 22. The paper lists Marco Trotta and Irrigant, Idaho, USA. It does not list Kukal as an author or assign him an author affiliation.
Kukal also said the current analysis is not defensible for a journal paper. He asked whether the data could be reoriented to answer a real issue. The manuscript does not imply his support for its current claims.

## Endorsement status

Dr. Alessandro Meregaglia introduced Marco to Dr. Edoardo Serra on September 24. Serra said he may not meet current requirements, but invited Marco to send a request. Marco replied that he would submit the paper and request endorsement. No endorsement is confirmed.

arXiv lists Serra on two recent cs.LG papers: [2111.04826](https://arxiv.org/abs/2111.04826), submitted November 8, 2021, and [2606.04287](https://arxiv.org/abs/2606.04287), submitted June 2, 2026. Both dates fall within arXiv's current three-month to five-year window. The public listings do not confirm account-level eligibility or an active positive endorsement.

The current [arXiv endorsement guide](https://info.arxiv.org/help/endorsement.html) starts the personal request during submission and provides an endorsement code. A previous arXiv submission alone does not prove current eligibility. arXiv counts recent work in its endorsement domain and requires active endorsement status. Check the category and account path in arXiv before requesting support. The paper has not been submitted.

The [citation audit](../../docs/evaluation/ML_CITATION_AUDIT.md) records the checked DOI, arXiv, publisher, and data-source links.

The source tar contains only the files needed to compile the paper. The metadata sidecar is `output/arxiv/arxiv_metadata.txt`. The separate reproduction ZIP contains protocols, saved evidence, code, and licenses. It is not embedded in the source tar. The ZIP excludes raw weather archives and credentials. New figures adapt the figures4papers workflow under its stated CC BY-NC 4.0 license.

Compile from this directory:

```bash
tectonic --keep-logs --keep-intermediates mlet_preprint.tex
```

Build the paper and source package from the repository root:

```bash
cd manuscript/arxiv
tectonic --outdir ../../output/pdf --keep-logs --keep-intermediates mlet_preprint.tex
cd ../..
python3 scripts/package_selective_paper.py
python3 scripts/verify_arxiv_manuscript.py --pdf output/pdf/mlet_preprint.pdf
```

Packaging synchronizes `output/pdf/mlet_arxiv_preprint.pdf` with the compiled PDF. It generates metadata from the PDF title and current abstract. The source archive includes the compiled bibliography and figure files. The evidence ZIP remains separate. The source package has no assigned arXiv identifier and is not submitted. Local compilation does not verify arXiv server processing.

Suggested category: cs.LG. arXiv moderators assign categories. Start the submission only when the current source package is ready and the author can share the endorsement request with Serra.

The paper makes a bounded empirical contribution. It proposes no new deferral algorithm. It makes no claim about conference acceptance or ISEF competitiveness.
