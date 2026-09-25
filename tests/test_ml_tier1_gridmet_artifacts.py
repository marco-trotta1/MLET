import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_ml_tier1_gridmet_artifacts as artifacts


def test_wind_dose_builds_pdf_and_png(monkeypatch, tmp_path):
    monkeypatch.setattr(artifacts, "FIGURES", tmp_path)
    results = {}
    for factor in [0, 0.447, 1, 2.237, 3.6, 5, 10]:
        methods = {
            method: {
                "station_macro_mae": 1.0,
                "station_macro_acceptance": 0.8,
                "vs_openet": {
                    "delta_macro_mae": 0.1,
                    "ci95": [0.05, 0.15],
                },
            }
            for method in artifacts.METHODS
        }
        results[f"wind_x{factor:g}"] = {"pooled": methods}

    artifacts.wind_dose(results)

    assert (tmp_path / "figure_15_tier1_gridmet_10member_wind_dose.pdf").exists()
    assert (tmp_path / "figure_15_tier1_gridmet_10member_wind_dose.png").exists()
