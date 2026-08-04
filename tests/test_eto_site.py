"""Tests for the verified ETo static site path."""

from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import pytest

from mlet.outlook.contracts import WeatherMember
from mlet.outlook.eto_build import write_eto_outlook
from mlet.outlook.eto_site import build_eto_site
from mlet.outlook.manifest import build_manifest


def _candidate_source(tmp_path: Path) -> Path:
    source = tmp_path / "candidate"
    source.mkdir()
    source_bytes = b"archived weather source\n"
    weather = tmp_path / "weather.jsonl"
    weather.write_bytes(source_bytes)
    manifest = build_manifest(
        "2026-07-01T18:00:00Z",
        {"weather": weather},
        "test-revision",
        "2026-07-01T18:00:00Z",
    )
    members = [
        WeatherMember(
            grid_id="43.50:-116.50",
            latitude=43.5,
            longitude=-116.5,
            elevation_m=824.0,
            member_id=f"member-{member_index}",
            issued_at=manifest.issued_at,
            valid_date=date(2026, 7, 1) + timedelta(days=lead_day),
            tmax_c=30.0 + member_index,
            tmin_c=12.0,
            vapor_pressure_kpa=1.2,
            wind_m_s=2.0,
            solar_mj_m2_day=25.0,
            precip_mm=0.0,
        )
        for member_index in range(3)
        for lead_day in range(1, 21)
    ]
    write_eto_outlook(members, manifest, source)
    return source


def test_build_eto_site_preserves_provenance_and_accessible_controls(
    tmp_path: Path,
) -> None:
    source = _candidate_source(tmp_path)
    result = build_eto_site(source, tmp_path / "site")

    assert result.run_id
    assert (result.destination / "index.html").is_file()
    assert (result.destination / "outlook/index.html").is_file()
    assert (result.destination / "outlook/viewer-data.json").is_file()
    viewer = json.loads(
        (result.destination / "outlook/viewer-data.json").read_text()
    )
    assert viewer["kind"] == "mlet.eto.viewer-data"
    assert viewer["run"]["production_status"] == "research_candidate"
    assert len(viewer["days"]) == 20
    assert viewer["grid_count"] == 1

    page = (result.destination / "outlook/index.html").read_text()
    assert 'aria-live="polite"' in page
    assert 'role="status"' in page
    assert 'role="img"' in page
    assert "p10" in page and "p50" in page and "p90" in page
    assert "No grid data for this selection." in page
    assert "@media (max-width:680px)" in page
    assert "https://" not in page
    assert "fixture" not in page.lower()

    site_manifest = json.loads((result.destination / "manifest.json").read_text())
    assert site_manifest["source_candidate_sha256"] == result.candidate_sha256
    assert site_manifest["source_manifest_sha256"] == result.source_manifest_sha256
    assert result.site_manifest_sha256 == hashlib.sha256(
        (result.destination / "manifest.json").read_bytes()
    ).hexdigest()


def test_build_eto_site_is_deterministic(tmp_path: Path) -> None:
    source = _candidate_source(tmp_path)
    first = build_eto_site(source, tmp_path / "first")
    second = build_eto_site(source, tmp_path / "second")

    relative_paths = [
        "index.html",
        "manifest.json",
        "outlook/index.html",
        "outlook/viewer-data.json",
        "outlook/source/outlook.json",
        "outlook/source/manifest.json",
    ]
    for relative in relative_paths:
        assert (first.destination / relative).read_bytes() == (
            second.destination / relative
        ).read_bytes()


def test_build_eto_site_rejects_a_candidate_hash_mismatch(tmp_path: Path) -> None:
    source = _candidate_source(tmp_path)
    candidate = source / "outlook.json"
    candidate.write_bytes(candidate.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="does not bind outlook.json"):
        build_eto_site(source, tmp_path / "site")
