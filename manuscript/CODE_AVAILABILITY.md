# Code availability

Repository: https://github.com/marco-trotta1/MLET

The current selective study is implemented in `scripts/ml_selective_residual.py`.
Its fixed protocol is `docs/evaluation/ML_SELECTIVE_RESIDUAL_PROTOCOL.md`.
The result receipt records code, protocol, cohort, and partition hashes.

`build_selective_artifacts.py` performs the declared post hoc matched-budget analysis and builds its figures.
`verify_selective_results.py` checks saved predictions without refitting models.
`package_selective_paper.py` builds the source archive and reproduction ZIP.

The earlier correction audit remains in the `ml_transfer` scripts and result directory.
The canonical manuscript is `manuscript/arxiv/mlet_preprint.tex`.
See `manuscript/REPRODUCIBILITY.md` for commands and pinned dependencies.
