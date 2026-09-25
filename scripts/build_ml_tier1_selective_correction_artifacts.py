"""Build figures and comparisons for the corrected measured-weather run."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_ml_tier1_artifacts as builder

DATA = ROOT / "docs/results/ml_tier1_selective_corrected"
FIG = ROOT / "manuscript/arxiv/figures/tier1_selective_corrected"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    builder.DATA = DATA
    builder.OUT = DATA
    builder.FIG = FIG
    builder.main()

    receipt_path = DATA / "analysis_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["correction_builder_sha256"] = sha256(Path(__file__))
    receipt["figures"] = {
        path.name: sha256(path)
        for path in sorted(FIG.glob("figure_*"))
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
