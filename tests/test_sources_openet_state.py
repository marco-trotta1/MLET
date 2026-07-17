"""Software-only checks for dated, availability-gated OpenET ETa analyses."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

import pytest

from mlet.sources.openet_state import normalize_openet_state


ISSUED_AT = "2026-07-16T18:00:00Z"
RETRIEVED_AT = "2026-07-20T12:00:00Z"


def _openet_rows() -> list[dict[str, object]]:
    return [
        {
            "grid_id": "fixture-idaho-grid",
            "eta_analysis_mm": 4.2,
            "observation_date": "2026-07-14",
            "source_available_at": "2026-07-15T18:00:00Z",
            "model": "fixture-openet-model",
            "model_version": "fixture-v1",
        }
    ]


def test_openet_state_carries_issue_availability_version_and_whole_day_latency() -> None:
    state = normalize_openet_state(
        _openet_rows(), issued_at=ISSUED_AT, retrieved_at=RETRIEVED_AT
    )

    assert len(state) == 1
    assert state[0].observed_through == date(2026, 7, 14)
    assert state[0].issued_at == datetime(2026, 7, 16, 18, tzinfo=timezone.utc)
    assert state[0].retrieved_at == datetime(2026, 7, 20, 12, tzinfo=timezone.utc)
    assert state[0].source_available_at == datetime(2026, 7, 15, 18, tzinfo=timezone.utc)
    assert state[0].latency_days == 2
    assert state[0].model == "fixture-openet-model"
    assert state[0].model_version == "fixture-v1"


def test_openet_state_rejects_same_issue_day_observation() -> None:
    rows = _openet_rows()
    rows[0]["observation_date"] = "2026-07-16"

    with pytest.raises(ValueError, match="completed day"):
        normalize_openet_state(rows, issued_at=ISSUED_AT, retrieved_at=RETRIEVED_AT)


def test_openet_state_rejects_source_available_after_historical_issue_even_when_retrieved_later() -> None:
    rows = _openet_rows()
    rows[0]["source_available_at"] = "2026-07-17T00:00:00Z"

    with pytest.raises(ValueError, match="source_available_at"):
        normalize_openet_state(rows, issued_at=ISSUED_AT, retrieved_at=RETRIEVED_AT)


def test_openet_state_rejects_missing_or_non_utc_source_availability() -> None:
    rows = _openet_rows()
    del rows[0]["source_available_at"]

    with pytest.raises(ValueError, match="source_available_at"):
        normalize_openet_state(rows, issued_at=ISSUED_AT, retrieved_at=RETRIEVED_AT)

    rows = _openet_rows()
    rows[0]["source_available_at"] = "2026-07-15T18:00:00-06:00"
    with pytest.raises(ValueError, match="UTC"):
        normalize_openet_state(rows, issued_at=ISSUED_AT, retrieved_at=RETRIEVED_AT)


def test_openet_state_rejects_unversioned_model_and_never_fills_missing_rows() -> None:
    rows = _openet_rows()
    del rows[0]["model_version"]

    with pytest.raises(ValueError, match="model_version"):
        normalize_openet_state(rows, issued_at=ISSUED_AT, retrieved_at=RETRIEVED_AT)
    assert normalize_openet_state([], issued_at=ISSUED_AT, retrieved_at=RETRIEVED_AT) == []


def test_openet_state_rejects_duplicate_grid_model_observation() -> None:
    rows = _openet_rows()
    rows.append(rows[0].copy())

    with pytest.raises(ValueError, match="duplicate"):
        normalize_openet_state(rows, issued_at=ISSUED_AT, retrieved_at=RETRIEVED_AT)


def test_openet_fixture_is_conspicuously_non_scientific() -> None:
    fixture_path = Path("examples/outlook/state.jsonl")
    rows = [json.loads(line) for line in fixture_path.read_text().splitlines()]

    assert rows[0]["fixture_non_scientific"] is True
    assert (
        normalize_openet_state(rows, issued_at=ISSUED_AT, retrieved_at=RETRIEVED_AT)[0].latency_days
        == 2
    )
