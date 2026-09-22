# MLET arXiv source

Title: MLET: Selective Neural Residual Correction for Spatial Evapotranspiration.
Author: Marco Trotta.
Affiliation: Irrigant, Idaho, USA.
Contact: m@irrigant.xyz.

Use `mlet_preprint.tex` as the main source file.
The source uses the original MLET letter-paper design, Irrigant logo, and five original visuals.
Meetpal S. Kukal appears in the acknowledgements, not the author block.
The current paper studies selective neural residual correction under spatial transfer and input corruption.
The main text focuses on selective neural correction, spatial cross-fitting, controlled input faults, and cropland transfer.
The original evidence architecture and reference-ETo diagnostics remain in separate appendices.
The references follow all appendices and figures.

The archive contains the manuscript, generated tables, bibliography, 13 vector figures, and Irrigant logo.
The generated `arxiv_metadata.txt` contains the current title, author, and abstract.
Packaging copies the compiled paper to both repository PDF paths.
The README links to `output/pdf/mlet_arxiv_preprint.pdf`.
The `anc/reproducibility/` directory contains code, protocols, and saved predictions.
It contains no private email, raw weather archive, credentials, or LaTeX source.

Compile from this directory:

```bash
tectonic --keep-logs --keep-intermediates mlet_preprint.tex
```

Build and verify from the full repository:

```bash
python3 scripts/build_ml_paper_artifacts.py
python3 scripts/build_selective_artifacts.py
cd manuscript/arxiv
tectonic --outdir ../../output/pdf --keep-logs --keep-intermediates mlet_preprint.tex
cd ../..
python3 scripts/package_selective_paper.py
python3 scripts/verify_arxiv_manuscript.py --pdf output/pdf/mlet_preprint.pdf
```

Suggested arXiv category: cs.LG.
This is a subject suggestion, not a moderation decision.
The package is not submitted, and the arXiv server build remains untested.
The branded preprint is not an anonymous ICML submission template.
The paper cites existing deferral theory and makes a limited empirical contribution.
It does not claim a new deferral algorithm or establish ICML acceptance or ISEF competitiveness.

The previous complete-weather benchmark is already inspected.
The selective protocol precedes its run; the matched-budget diagnostic is post hoc.
Synthetic input faults test robustness, not physical weather interventions.
The original outlook remains a negative one-issue feasibility diagnostic with incomplete support.
