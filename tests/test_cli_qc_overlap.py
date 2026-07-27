"""Non-scientific deterministic checks for the qc-overlap command."""

import json

from mlet.cli import main

BASE = {
    "grid_id": "fixture-grid-a",
    "latitude": 43.6175,
    "longitude": -116.1997,
    "elevation_m": 824.0,
    "issued_at": "2026-07-15T12:00:00+00:00",
    "tmin_c": 15.0,
    "vapor_pressure_kpa": 1.2,
    "wind_m_s": 2.5,
    "solar_mj_m2_day": 28.0,
    "precip_mm": 0.0,
}
DAYS = ["2026-07-12", "2026-07-13", "2026-07-14"]


def _window(forecast_tmax: float) -> dict:
    return {
        "issue_time": "2026-07-15T12:00:00+00:00",
        "overlap_days": 3,
        "observed": [
            dict(BASE, member_id="obs", valid_date=day, tmax_c=33.0) for day in DAYS
        ],
        "forecast": [
            dict(BASE, member_id="fc", valid_date=day, tmax_c=forecast_tmax) for day in DAYS
        ],
    }


def test_qc_overlap_exits_zero_when_consistent(tmp_path, capsys) -> None:
    path = tmp_path / "window.json"
    path.write_text(json.dumps(_window(34.5)), encoding="utf-8")

    exit_code = main(["qc-overlap", "--window-json", str(path)])

    assert exit_code == 0
    assert "verdict               : consistent" in capsys.readouterr().out


def test_qc_overlap_exits_one_on_identical_drivers(tmp_path, capsys) -> None:
    path = tmp_path / "identical.json"
    path.write_text(json.dumps(_window(33.0)), encoding="utf-8")

    exit_code = main(["qc-overlap", "--window-json", str(path)])

    assert exit_code == 1
    assert "verdict               : suspiciously_identical" in capsys.readouterr().out


def test_qc_overlap_returns_2_for_missing_required_key(tmp_path, capsys) -> None:
    path = tmp_path / "missing_key.json"
    payload = _window(34.5)
    del payload["observed"][0]["grid_id"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = main(["qc-overlap", "--window-json", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "error:" in captured.err
