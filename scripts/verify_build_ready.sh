#!/usr/bin/env bash
# Verify all manuscript and software work that does not require outcome data.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

./scripts/verify.sh

python3 - <<'PY'
from pathlib import Path
import hashlib
import tempfile

from mlet.manuscript_artifacts import build_phase2_artifacts
from mlet.outlook.eto_hindcast import evaluate_eto_hindcast_evidence
from scripts.verify_arxiv_manuscript import (
    FINAL_PDF,
    _verify_final_package,
    _verify_generated_artifacts,
    _verify_phase2_receipt,
)
from mlet.sources.agrimet_station_registry import (
    load_agrimet_station_registry,
    stations_for_state,
)

registry_path = Path("data/outlook/agrimet_station_registry.json")
snapshot = load_agrimet_station_registry(registry_path)
idaho = stations_for_state(snapshot, "ID")
if len(snapshot.stations) != 265 or len(idaho) != 52:
    raise SystemExit("AgriMet station registry counts changed")
expected_digest = "ae5f85f719a057276bf9549d2b4f69fd8a570f73ab700216d435e1c7639cb10b"
actual_digest = hashlib.sha256(registry_path.read_bytes()).hexdigest()
if actual_digest != expected_digest:
    raise SystemExit("AgriMet station registry digest changed")

_verify_phase2_receipt()
_verify_generated_artifacts()
_verify_final_package(FINAL_PDF)

fixture_report = evaluate_eto_hindcast_evidence(
    Path("examples/outlook/eto_hindcast_evidence.json")
)
if "software fixture is non-scientific" not in fixture_report.completion_blockers:
    raise SystemExit("ETo software fixture lost its non-scientific blocker")

with tempfile.TemporaryDirectory(prefix="mlet-build-ready-") as temporary:
    output = Path(temporary)
    build_phase2_artifacts(Path("docs/results/phase2_openet_value.json"), output)
    for relative in (
        "phase2_openet_value.md",
        "tables/phase2_model_comparison.csv",
        "figures/phase2_model_comparison.svg",
    ):
        generated = (output / relative).read_bytes()
        committed = (Path("docs/results") / relative).read_bytes()
        if generated != committed:
            raise SystemExit(f"Phase 2 artifact differs: {relative}")

for path in (
    "manuscript/manuscript.md",
    "manuscript/SUPPLEMENT.md",
    "manuscript/DATA_AVAILABILITY.md",
    "manuscript/CODE_AVAILABILITY.md",
    "manuscript/LIMITATIONS.md",
    "manuscript/references.bib",
    "docs/evaluation/2026-07-31-FEATURE_FREEZE.md",
):
    if not Path(path).is_file() or not Path(path).read_text(encoding="utf-8").strip():
        raise SystemExit(f"Missing manuscript file: {path}")
PY

echo "== BUILD READY: non-gated software and manuscript work passed =="
echo "ETo outcome readiness remains gated by historical station records and the full archive."
