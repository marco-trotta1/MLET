"""Tests for the history-bound AgriMet target index builder."""

from datetime import date, datetime, timezone

from mlet.sources.agrimet import AgriMetEtosObservation
from scripts.build_eto_target_index import _case_targets, _prior_year_baselines


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
