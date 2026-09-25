"""Apply the frozen Tier 3 paired comparisons."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/results/ml_tier3_gridmet"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER3_GRIDMET_PROTOCOL.md"
import analyze_ml_tier1_gridmet as tier1_analysis

SEED = 20260924
CONDITIONS = tier1_analysis.CONDITIONS
COMPARISONS = [
    (method, baseline, condition)
    for method, baseline in [
        ("TunedGain", "Gain"),
        ("TunedGain", "SupportGain"),
        ("LogisticSign", "SupportGain"),
        ("ConformalCSR", "SupportGain"),
    ]
    for condition in CONDITIONS
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyze() -> list[dict]:
    if not (OUT / "results.json").exists() or not (OUT / "receipt.json").exists():
        raise RuntimeError("The fixed Tier 3 selector run is incomplete")
    rows = []
    for index, (method, baseline, condition) in enumerate(COMPARISONS):
        frame = pd.read_csv(OUT / f"predictions_{condition}.csv")
        group_sums, station = tier1_analysis.group_differences(
            frame, method, baseline
        )
        groups = station.groupby("group", sort=True).delta.agg(["sum", "count"])
        rows.append(
            {
                "method": method,
                "baseline": baseline,
                "condition": condition,
                "delta_macro_mae_favoring_method": float(station.delta.mean()),
                "ci95": tier1_analysis.bootstrap_interval(
                    groups["sum"].to_numpy(), groups["count"].to_numpy(), SEED
                ),
                "groups": int(len(groups)),
                "stations": int(len(station)),
                "rows": int(len(frame)),
                "one_sided_signflip_p": tier1_analysis.signflip_p(
                    group_sums, SEED + index
                ),
            }
        )
    adjusted = tier1_analysis.holm_adjust(
        [row["one_sided_signflip_p"] for row in rows]
    )
    for row, value in zip(rows, adjusted):
        row["holm_p"] = value
    target = OUT / "primary_comparisons.json"
    target.write_text(json.dumps(rows, indent=2) + chr(10))
    receipt = {
        "protocol_sha256": sha256(PROTOCOL),
        "analysis_script_sha256": sha256(Path(__file__)),
        "results_sha256": sha256(OUT / "results.json"),
        "run_receipt_sha256": sha256(OUT / "receipt.json"),
        "primary_comparisons_sha256": sha256(target),
        "comparison_count": len(rows),
        "bootstrap_draws": tier1_analysis.BOOTSTRAP_DRAWS,
        "bootstrap_seed": SEED,
        "signflip_draws": tier1_analysis.SIGNFLIP_DRAWS,
        "signflip_seed_base": SEED,
        "holm_family": "all comparisons in primary_comparisons.json",
    }
    (OUT / "analysis_receipt.json").write_text(
        json.dumps(receipt, indent=2) + chr(10)
    )
    print(json.dumps(receipt, indent=2))
    return rows


if __name__ == "__main__":
    analyze()
