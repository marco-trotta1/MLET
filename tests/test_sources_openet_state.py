"""Non-scientific checks for dated OpenET ETa analyses."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

import pytest

from mlet.sources.openet_state import normalize_openet_state


RETRIEVED_AT = "2026-07-16T12:00:00Z"


def _openet_rows() -> list[dict[str, object]]:
    return [
        {
            "grid_id": "fixture-idaho-grid",
            "eta_analysis_mm": 4.2,
            "observation_date": "2026-07-14",
            "model": "fixture-openet-model",
            "model_version": "fixture-v1",
        }
    ]


def test_openet_state_carries_observation_date_model_version_and_whole_day_latency() -> None:
    state = normalize_openet_state(_openet_rows(), retrieved_at=RETRIEVED_AT)

    assert len(state) == 1
    assert state[0].observed_through == date(2026, 7, 14)
    assert state[0].retrieved_at == datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
    assert state[0].latency_days == 2
    assert state[0].model == "fixture-openet-model"
    assert state[0].model_version == "fixture-v1"


def test_openet_state_rejects_future_observation_date() -> None:
    rows = _openet_rows()
    rows[0]["observation_date"] = "2026-07-17"

    with pytest.raises(ValueError, match="later than retrieval/run time"):
        normalize_openet_state(rows, retrieved_at=RETRIEVED_AT)


def test_openet_state_rejects_unversioned_model_and_never_fills_missing_rows() -> None:
    rows = _openet_rows()
    del rows[0]["model_version"]

    with pytest.raises(ValueError, match="model_version"):
        normalize_openet_state(rows, retrieved_at=RETRIEVED_AT)
    assert normalize_openet_state([], retrieved_at=RETRIEVED_AT) == []


def test_openet_state_rejects_duplicate_grid_model_observation() -> None:
    rows = _openet_rows()
    rows.append(rows[0].copy())

    with pytest.raises(ValueError, match="duplicate"):
        normalize_openet_state(rows, retrieved_at=RETRIEVED_AT)


def test_openet_fixture_is_conspicuously_non_scientific() -> None:
    fixture_path = Path("examples/outlook/state.jsonl")
    rows = [json.loads(line) for line in fixture_path.read_text().splitlines()]

    assert rows[0]["fixture_non_scientific"] is True
    assert normalize_openet_state(rows, retrieved_at=RETRIEVED_AT)[0].latency_days == 2
