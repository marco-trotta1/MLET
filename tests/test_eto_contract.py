"""Tests for the strict ETo-only candidate contract."""

from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path

import pytest

from mlet.outlook.contracts import WeatherMember
from mlet.outlook.eto_build import serialize_eto_outlook
from mlet.outlook.eto_contract import load_eto_candidate, validate_eto_candidate_payload
from mlet.outlook.manifest import build_manifest


def _candidate_payload(tmp_path: Path) -> dict[str, object]:
    source = tmp_path / "weather.jsonl"
    source.write_text("{}\n", encoding="utf-8")
    manifest = build_manifest(
        "2026-07-01T18:00:00Z",
        {"weather": source},
        "test-revision",
        "2026-07-01T18:00:00Z",
    )
    members = [
        WeatherMember(
            grid_id="43:-117",
            latitude=43.5,
            longitude=-116.5,
            elevation_m=824.0,
            member_id=f"member-{member_index}",
            issued_at=manifest.issued_at,
            valid_date=manifest.issued_at.date() + timedelta(days=lead_day),
            tmax_c=30.0,
            tmin_c=12.0,
            vapor_pressure_kpa=1.2,
            wind_m_s=2.0,
            solar_mj_m2_day=25.0,
            precip_mm=0.0,
        )
        for member_index in range(3)
        for lead_day in range(1, 21)
    ]
    return json.loads(serialize_eto_outlook(members, manifest).decode("utf-8"))


def test_eto_contract_returns_identity_and_full_coverage(tmp_path: Path) -> None:
    payload = _candidate_payload(tmp_path)

    contract = validate_eto_candidate_payload(payload)

    assert contract.run_id == payload["run_id"]
    assert len(contract.grid_ids) == 1
    assert len(contract.valid_dates) == 20


def test_eto_contract_rejects_conditional_layers(tmp_path: Path) -> None:
    payload = _candidate_payload(tmp_path)
    payload["layers"] = {"eto_mm": payload["layers"]["eto_mm"], "eta_analysis_mm": {}}

    with pytest.raises(ValueError, match="layers must contain only eto_mm"):
        validate_eto_candidate_payload(payload)


def test_eto_contract_loader_rejects_duplicate_keys(tmp_path: Path) -> None:
    payload = _candidate_payload(tmp_path)
    candidate = tmp_path / "outlook.json"
    candidate.write_text(
        json.dumps(payload, sort_keys=True).replace(
            '"schema_version": 1,', '"schema_version": 1, "schema_version": 1,'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate-key-free"):
        load_eto_candidate(candidate)


def test_eto_contract_loader_rejects_a_symlink(tmp_path: Path) -> None:
    payload = _candidate_payload(tmp_path)
    target = tmp_path / "target.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="must not be a symlink"):
        load_eto_candidate(link)
