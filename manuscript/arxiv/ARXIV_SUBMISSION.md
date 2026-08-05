# MLET arXiv source

Use `mlet_preprint.tex` as the main file. Select XeLaTeX when the submission
interface asks for a compiler.

The source archive contains these required files:

- `mlet_preprint.tex`
- `generated_claims.tex`
- `figures/figure_1_evidence_paths.pdf`
- `figures/figure_2_phase2_models.pdf`
- `figures/figure_3_boii_feasibility.pdf`
- `figures/figure_4_native_grid.pdf`
- `figures/figure_5_support_tensor.pdf`
- `assets/uidaho_logo.png`
- `assets/irrigant_logo.png`

The repository generates the claim macros and figures from local evidence
artifacts. Run these commands from the repository root before a new build:

```text
PYTHONPATH=src python3 scripts/build_arxiv_claims.py --out manuscript/arxiv/generated_claims.tex
PYTHONPATH=src python3 scripts/build_arxiv_figures.py --out manuscript/arxiv/figures
```

Compile the manuscript from `manuscript/arxiv`:

```text
tectonic --outdir ../../output/pdf --keep-logs mlet_preprint.tex
```

Run the claim, citation, figure, and PDF checks from the repository root:

```text
PYTHONPATH=src python3 scripts/verify_arxiv_manuscript.py --pdf output/pdf/mlet_preprint.pdf
```

The current manuscript reports no reference-ETo skill claim. Do not remove
the incomplete-evaluation language before the full frozen hindcast exists.
