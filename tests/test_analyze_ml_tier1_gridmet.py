import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/analyze_ml_tier1_gridmet.py"
SPEC = importlib.util.spec_from_file_location("analyze_ml_tier1_gridmet", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
analysis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analysis)


def test_holm_adjustment_is_monotone_and_bounded():
    adjusted = analysis.holm_adjust([0.01, 0.04, 0.03])

    assert adjusted == [0.03, 0.06, 0.06]
