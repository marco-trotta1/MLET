"""Non-scientific checks for the Idaho GEFS normalization boundary."""

from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import pytest

from mlet.sources.gefs import fetch_gefs, normalize_gefs_rows


ISSUED_AT = "2026-07-16T00:00:00Z"
IDAHO_BBOX = (-117.25, 42.0, -111.0, 49.0)


def _gefs_rows() -> list[dict[str, object]]:
    """Return synthetic, non-scientific rows for deterministic software tests."""
    rows: list[dict[str, object]] = []
    issue_date = date(2026, 7, 16)
    for member_index in range(3):
        for lead_day in range(1, 21):
            rows.append(
                {
                    "grid_id": "fixture-idaho-grid",
                    "latitude": 43.6,
                    "longitude": -116.2,
                    "elevation_m": 824.0,
                    "member_id": f"fixture-member-{member_index:02d}",
                    "valid_date": (issue_date + timedelta(days=lead_day)).isoformat(),
                    "tmax_c": 30.0 + member_index,
                    "tmin_c": 12.0 + member_index,
                    "vapor_pressure_kpa": 1.2,
                    "wind_m_s": 2.0,
                    "solar_mj_m2_day": 25.0,
                    "precip_mm": 0.5,
                }
            )
    return rows


def test_gefs_normalizer_requires_twenty_distinct_daily_leads() -> None:
    members = normalize_gefs_rows(_gefs_rows(), issued_at=ISSUED_AT)

    assert len(members) == 60
    for member_id in {member.member_id for member in members}:
        leads = {
            member.valid_date
            for member in members
            if member.grid_id == "fixture-idaho-grid" and member.member_id == member_id
        }
        assert len(leads) == 20


def test_gefs_normalizer_rejects_missing_required_radiation() -> None:
    rows = _gefs_rows()
    del rows[0]["solar_mj_m2_day"]

    with pytest.raises(ValueError, match="solar_mj_m2_day"):
        normalize_gefs_rows(rows, issued_at=ISSUED_AT)


def test_gefs_normalizer_rejects_duplicate_member_grid_day() -> None:
    rows = _gefs_rows()
    rows.append(rows[0].copy())

    with pytest.raises(ValueError, match="duplicate"):
        normalize_gefs_rows(rows, issued_at=ISSUED_AT)


def test_gefs_normalizer_rejects_missing_daily_lead_for_one_member() -> None:
    rows = _gefs_rows()
    rows.pop()

    with pytest.raises(ValueError, match="exactly 20 daily leads"):
        normalize_gefs_rows(rows, issued_at=ISSUED_AT)


def test_gefs_normalizer_rejects_non_finite_or_unsafe_weather_values() -> None:
    rows = _gefs_rows()
    rows[0]["wind_m_s"] = float("inf")

    with pytest.raises(ValueError, match="finite"):
        normalize_gefs_rows(rows, issued_at=ISSUED_AT)


def test_weather_fixture_is_conspicuously_non_scientific_and_complete() -> None:
    fixture_path = Path("examples/outlook/weather_members.jsonl")
    rows = [json.loads(line) for line in fixture_path.read_text().splitlines()]

    assert all(row["fixture_non_scientific"] is True for row in rows)
    assert len(normalize_gefs_rows(rows, issued_at=ISSUED_AT)) == 60


def test_fetch_gefs_writes_atomic_normalized_file_and_source_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = json.dumps(_gefs_rows()).encode("utf-8")

    class Response:
        content = payload
        url = "https://example.test/gefs?bounded=true"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict[str, object]]:
            return json.loads(payload)

    captured: dict[str, object] = {}

    def fake_get(url: str, *, params: dict[str, object], timeout: int) -> Response:
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return Response()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("mlet.sources.gefs.requests.get", fake_get)
    destination = tmp_path / "weather_members.jsonl"

    output = fetch_gefs(date(2026, 7, 16), IDAHO_BBOX, destination)

    assert output == destination
    assert len(destination.read_text().splitlines()) == 60
    receipt = json.loads(destination.with_suffix(".jsonl.source.json").read_text())
    assert receipt["uri"] == Response.url
    assert receipt["sha256"] == hashlib.sha256(payload).hexdigest()
    assert receipt["source_issue_at"] == ISSUED_AT
    assert captured["params"] == {
        "bottomlat": 42.0,
        "issue_date": "2026-07-16",
        "leftlon": -117.25,
        "rightlon": -111.0,
        "toplat": 49.0,
        "variables": "precip_mm,solar_mj_m2_day,tmax_c,tmin_c,vapor_pressure_kpa,wind_m_s",
    }
    assert len(list((tmp_path / "data" / "cache").glob("*.json"))) == 1


def test_fetch_gefs_leaves_no_normalized_artifact_when_weather_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    incomplete = _gefs_rows()[:-1]
    payload = json.dumps(incomplete).encode("utf-8")

    class Response:
        content = payload
        url = "https://example.test/gefs?incomplete=true"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict[str, object]]:
            return json.loads(payload)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "mlet.sources.gefs.requests.get", lambda *args, **kwargs: Response()
    )
    destination = tmp_path / "weather_members.jsonl"

    with pytest.raises(ValueError, match="exactly 20 daily leads"):
        fetch_gefs(date(2026, 7, 16), IDAHO_BBOX, destination)

    assert not destination.exists()
    assert not destination.with_suffix(".jsonl.source.json").exists()
