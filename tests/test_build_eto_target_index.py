"""Tests for the history-bound AgriMet target index builder."""

from datetime import date, datetime, timezone
import json
from pathlib import Path

import pytest

from mlet.sources.agrimet import AgriMetEtosObservation
from scripts.build_eto_target_index import (
    _case_targets,
    _load_index,
    _prior_year_baselines,
)


def _observation(year: int, valid_date: date, value: float) -> AgriMetEtosObservation:
    return AgriMetEtosObservation(
        station_id="BOII",
        latitude=43.6,
        longitude=-116.2,
        elevation_m=829.0,
        valid_date=valid_date.replace(year=year),
        etos_mm=value,
        available_at=datetime(year, 7, 5, 12, tzinfo=timezone.utc),
        uri="https://example.test/boii",
        source_version="source-v1",
    )


def test_prior_year_baseline_excludes_the_evaluated_year() -> None:
    observations = (
        _observation(2017, date(2017, 7, 3), 4.0),
        _observation(2018, date(2018, 7, 3), 5.0),
        _observation(2019, date(2019, 7, 3), 6.0),
    )

    baselines = _prior_year_baselines(observations)

    assert baselines[("BOII", date(2019, 7, 3))] == 4.5
    assert baselines[("BOII", date(2018, 7, 3))] == 4.0


def test_prior_year_baseline_uses_all_prior_station_years_only() -> None:
    observations = (
        _observation(2016, date(2016, 7, 3), 3.0),
        _observation(2017, date(2017, 7, 3), 4.0),
        _observation(2018, date(2018, 7, 3), 5.0),
        _observation(2019, date(2019, 7, 3), 6.0),
        _observation(2020, date(2020, 7, 3), 100.0),
    )

    baselines = _prior_year_baselines(observations)

    assert baselines[("BOII", date(2019, 7, 3))] == pytest.approx(4.5)
    assert baselines[("BOII", date(2020, 7, 3))] == pytest.approx(3.0)


def test_prior_year_baseline_uses_target_valid_date_year_for_year_crossing() -> None:
    observations = (
        _observation(2018, date(2018, 1, 1), 2.0),
        _observation(2019, date(2019, 1, 1), 4.0),
        _observation(2020, date(2020, 1, 1), 6.0),
    )

    baselines = _prior_year_baselines(observations)

    assert baselines[("BOII", date(2020, 1, 1))] == pytest.approx(3.0)


def test_target_builder_accepts_gefs_schema_two_and_rejects_schema_one(
    tmp_path: Path,
) -> None:
    index = tmp_path / "gefs-index.json"
    common = {
        "kind": "mlet.eto.gefs-index",
        "issues": [{"case_id": "placeholder"}],
    }
    index.write_text(
        json.dumps({**common, "schema_version": 2}), encoding="utf-8"
    )
    payload, _ = _load_index(index, "mlet.eto.gefs-index")
    assert payload["schema_version"] == 2

    index.write_text(
        json.dumps({**common, "schema_version": 1}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="schema_version 2"):
        _load_index(index, "mlet.eto.gefs-index")


def test_case_targets_explicitly_excludes_other_seasons_and_missing_baselines() -> None:
    issue_time = datetime(2019, 8, 20, tzinfo=timezone.utc)
    observation = _observation(2019, date(2019, 8, 21), 6.0)

    targets, exclusions = _case_targets(
        station_id="BOII",
        issue_time=issue_time,
        season="JJA",
        observations_by_key={("BOII", observation.valid_date): observation},
        exclusions_by_key={},
        baselines={},
    )

    assert targets == ()
    reasons = {item["reason"] for item in exclusions}
    assert "baseline_support_missing" in reasons
    assert "outside_held_out_season" in reasons
