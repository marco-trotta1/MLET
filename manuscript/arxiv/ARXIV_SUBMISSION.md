# MLET arXiv source

Title: MLET: Incremental Predictive Value of OpenET and an Auditable
Reference-Evapotranspiration Outlook.

Use mlet_preprint.tex as the main file. The source compiles with Tectonic and
uses the letter-paper layout in the manuscript.

The source archive contains these files:

- mlet_preprint.tex
- generated_claims.tex
- figures/figure_1_evidence_paths.pdf
- figures/figure_2_phase2_models.pdf
- figures/figure_3_boii_feasibility.pdf
- figures/figure_4_native_grid.pdf
- figures/figure_5_support_tensor.pdf
- assets/uidaho_logo.png
- assets/irrigant_logo.png
- ARXIV_SUBMISSION.md

Generate claims and figures from the repository root before a new build:

PYTHONPATH=src python3 scripts/build_arxiv_claims.py --out
manuscript/arxiv/generated_claims.tex

PYTHONPATH=src python3 scripts/build_arxiv_figures.py --out
manuscript/arxiv/figures

Compile from manuscript/arxiv:

tectonic --outdir ../../output/pdf --keep-logs mlet_preprint.tex

Run the source, citation, figure, and PDF checks from the repository root:

PYTHONPATH=src python3 scripts/verify_arxiv_manuscript.py --pdf
output/pdf/mlet_preprint.pdf

The Phase 2 result is reproduced. The full reference-ETo hindcast remains
pending. The BOII artifact is a retrospective reforecast diagnostic. Its later
archive retrieval does not prove operational availability at the historical
issue time. The AgriMet target retrieval time does not prove original
publication time. Do not promote the outlook until the full archive, support
checks, checksums, and independent release review are complete.
