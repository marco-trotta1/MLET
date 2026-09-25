import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_ml_tier3_gridmet as analysis


def test_primary_family_covers_all_methods_and_conditions():
    assert len(analysis.COMPARISONS) == 52
    assert {condition for _, _, condition in analysis.COMPARISONS} == set(
        analysis.CONDITIONS
    )
    assert {method for method, _, _ in analysis.COMPARISONS} == {
        "TunedGain",
        "LogisticSign",
        "ConformalCSR",
    }
