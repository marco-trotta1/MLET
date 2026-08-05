"""Non-scientific deterministic checks for the qc-eto cross-check command."""

import json

from mlet.cli import main

MEMBER = {
    "grid_id": "fixture-grid-a",
    "latitude": 43.6175,
    "longitude": -116.1997,
    "elevation_m": 824.0,
    "member_id": "fixture-member-01",
    "issued_at": "2026-07-14T00:00:00+00:00",
    "valid_date": "2026-07-15",
    "tmax_c": 33.0,
    "tmin_c": 15.0,
    "vapor_pressure_kpa": 1.2,
    "wind_m_s": 2.5,
    "solar_mj_m2_day": 28.0,
    "precip_mm": 0.0,
}


def test_qc_eto_reports_agreement_and_exits_zero(tmp_path, capsys) -> None:
    path = tmp_path / "member.json"
    path.write_text(json.dumps(MEMBER), encoding="utf-8")

    exit_code = main(["qc-eto", "--member-json", str(path)])

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "ASCE-PM (mlet)        : 6.7158 mm/day" in captured
    assert "Priestley-Taylor      : 6.2683 mm/day" in captured
    assert "PT / ASCE-PM ratio    : 0.9334" in captured
    assert "ok: both paths agree" in captured


def test_qc_eto_fails_when_solar_units_are_wrong(tmp_path, capsys) -> None:
    """A W m-2 solar value must be rejected, not silently cross-checked."""
    payload = dict(MEMBER, solar_mj_m2_day=324.0)
    path = tmp_path / "member_watts.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = main(["qc-eto", "--member-json", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "error:" in captured.err
    assert "MJ m-2 d-1" in captured.err


def test_qc_eto_returns_2_for_missing_member_json(capsys, tmp_path) -> None:
    missing = tmp_path / "missing.json"

    exit_code = main(["qc-eto", "--member-json", str(missing)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "error:" in captured.err


def test_qc_eto_returns_2_for_malformed_json(tmp_path, capsys) -> None:
    path = tmp_path / "malformed.json"
    path.write_text("{not valid json", encoding="utf-8")

    exit_code = main(["qc-eto", "--member-json", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "error:" in captured.err
