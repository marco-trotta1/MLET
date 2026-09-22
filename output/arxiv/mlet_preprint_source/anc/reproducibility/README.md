# Reproduce the MLET selective correction paper

This package contains recorded experiments and their verification code.
The current study is exploratory. Its protocols state which earlier results were already known.

## Verify saved results

The recorded environment uses Python 3.13.5.
Install the pinned direct dependencies in a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-paper.lock
python -m pytest tests/test_ml_transfer_audit.py tests/test_ml_selective_residual.py tests/test_baselines.py tests/test_build_dataset.py tests/test_evaluate.py -q
python scripts/verify_ml_paper.py
python scripts/verify_selective_results.py
python scripts/build_ml_paper_artifacts.py
python scripts/build_selective_artifacts.py
```

The checks do not fit another model.
They verify partitions, code hashes, target alignment, selector arithmetic, metric values, exact negative controls, and the original graphics.
The figure builders read saved predictions.

## Refit the fixed experiments

Preserve the supplied result directories before fitting new models.
Completed experiments refuse to overwrite their results.

```bash
mv docs/results/ml_transfer docs/results/ml_transfer_recorded
mv docs/results/ml_selective docs/results/ml_selective_recorded
python scripts/fetch_ml_sources.py
python scripts/ml_transfer_audit.py
python scripts/ml_transfer_sensitivity.py
python scripts/ml_neural_sensitivity.py
python scripts/ml_landcover_sensitivity.py
python scripts/audit_ml_humidity.py
python scripts/ml_selective_residual.py
mkdir -p docs/results/ml_selective
cp docs/results/ml_selective_recorded/original_visuals.json docs/results/ml_selective/original_visuals.json
python scripts/build_ml_paper_artifacts.py
python scripts/build_selective_artifacts.py
python scripts/verify_ml_paper.py
python scripts/verify_selective_results.py
```

The source archives have published checksum verification.
The experiment receipts retain SHA-256 values, seeds, package versions, fit times, and warnings.
The selective run uses 480 neural fits and retains every outer and inner prediction.
Three ensemble seeds are 20260713, 20260714, and 20260715.
Bootstrap comparisons use 2,000 draws and seed 20260922.
No seed is selected from its test performance.

`docs/evaluation/ML_SELECTIVE_RESIDUAL_PROTOCOL.md` defines the fixed experiment.
`docs/evaluation/ML_MATCHED_SELECTION_ANALYSIS.md` identifies the later matched-budget analysis as post hoc.
`docs/evaluation/ML_LITERATURE_POSITIONING.md` links the closest arXiv, alphaXiv, and ICML papers.

## Build the manuscript in the full repository

The canonical manuscript is `manuscript/arxiv/mlet_preprint.tex`.
Its author is Marco Trotta, with contact address `m@irrigant.xyz`.
The original Irrigant logo and five original figures remain present.
Meetpal S. Kukal appears in the acknowledgements.

```bash
cd manuscript/arxiv
tectonic --keep-logs --keep-intermediates --outdir ../../output/pdf mlet_preprint.tex
cd ../..
python scripts/package_selective_paper.py
python scripts/verify_arxiv_manuscript.py --pdf output/pdf/mlet_preprint.pdf
```

Packaging synchronizes `output/pdf/mlet_arxiv_preprint.pdf` with the canonical compiled PDF.
It generates `output/arxiv/arxiv_metadata.txt` from the current manuscript abstract and PDF metadata.
The source archive includes that metadata, the compiled bibliography, and the ancillary reproduction package.
The separate reproduction package contains no LaTeX source because arXiv ancillary directories exclude TeX files.

## Provenance and licenses

The original MLET source revision is `9b922ad6036f96aec3a2490c03928e0fb3c30cb5`.
The reproduction package includes source modules for the frozen code.
Its source-adapter initializer omits imports for unrelated forecast adapters.
The original figures retain their exact PDF bytes and source claims.
The new model study does not change the reference-ETo outlook's validation state.

Data sources:

- https://doi.org/10.5281/zenodo.10119477
- https://doi.org/10.5281/zenodo.7636781

New graphics use the attributed style adaptation from Chen Liu's figures4papers:
https://github.com/ChenLiu-1996/figures4papers, revision `3c181f85e82c6f24948fcaaf3be6696102b41d8d`.
The source is `figure_ImmunoStruct/plot_bars.py`.
The adapted plotting scripts and their figures retain the CC BY-NC 4.0 license in `licenses/`.
The original MLET logo and the five retained figures are separate existing assets.
