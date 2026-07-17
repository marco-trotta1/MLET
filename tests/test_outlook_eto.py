"""Non-scientific deterministic checks for ASCE reference ETo forwarding."""

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from mlet.outlook.contracts import WeatherMember
from mlet.outlook.eto import (
    eto_for_member,
    summarize_member_groups,
    summarize_members,
)
from pyfao56 import refet


@pytest.fixture
def weather_member() -> WeatherMember:
    """Non-scientific ASCE forwarding row: 2026-07-15, 43.6175°N, 824 m."""
    return WeatherMember(
        grid_id="fixture-grid-a",
        latitude=43.6175,
        longitude=-116.1997,
        elevation_m=824.0,
        member_id="fixture-member-01",
        issued_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
        valid_date=date(2026, 7, 15),
        tmax_c=33.0,
        tmin_c=15.0,
        vapor_pressure_kpa=1.2,
        wind_m_s=2.5,
        solar_mj_m2_day=28.0,
        precip_mm=0.0,
    )


def test_eto_matches_vendored_asce_short_reference(
    weather_member: WeatherMember,
) -> None:
    expected = refet.ascedaily(
        "S",
        weather_member.elevation_m,
        weather_member.latitude,
        weather_member.valid_date.timetuple().tm_yday,
        weather_member.solar_mj_m2_day,
        weather_member.tmax_c,
        weather_member.tmin_c,
        vapr=weather_member.vapor_pressure_kpa,
        wndsp=weather_member.wind_m_s,
        wndht=2.0,
    )

    assert eto_for_member(weather_member) == pytest.approx(expected)


def test_member_summary_is_order_independent() -> None:
    first = summarize_members([4.0, 2.0, 6.0])
    second = summarize_members([6.0, 4.0, 2.0])

    assert first == second
    assert first.p50 == pytest.approx(4.0)


@pytest.mark.parametrize("values", [[], [1.0, float("nan")], [1.0, -0.1]])
def test_member_summary_rejects_invalid_eto_values(values: list[float]) -> None:
    with pytest.raises(ValueError, match="finite non-negative"):
        summarize_members(values)


def test_member_summary_rejects_unordered_quantiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unordered_quantiles(*args: object, **kwargs: object) -> tuple[float, float, float]:
        del args, kwargs
        return (3.0, 2.0, 4.0)

    monkeypatch.setattr("mlet.outlook.eto.np.quantile", unordered_quantiles)

    with pytest.raises(ValueError, match="must be ordered"):
        summarize_members([2.0, 3.0, 4.0])


def test_member_groups_are_keyed_by_grid_and_valid_date(
    weather_member: WeatherMember,
) -> None:
    members = [
        weather_member,
        replace(weather_member, member_id="fixture-member-02", tmax_c=34.0),
        replace(weather_member, member_id="fixture-member-03", tmax_c=35.0),
        replace(
            weather_member,
            member_id="fixture-member-other-date-01",
            valid_date=date(2026, 7, 16),
        ),
        replace(
            weather_member,
            member_id="fixture-member-other-date-02",
            valid_date=date(2026, 7, 16),
            tmax_c=34.0,
        ),
        replace(
            weather_member,
            member_id="fixture-member-other-date-03",
            valid_date=date(2026, 7, 16),
            tmax_c=35.0,
        ),
    ]

    result = summarize_member_groups(members)

    assert set(result) == {
        (weather_member.grid_id, weather_member.valid_date),
        (weather_member.grid_id, date(2026, 7, 16)),
    }
    assert summarize_member_groups(list(reversed(members))) == result


def test_member_groups_require_at_least_three_members(
    weather_member: WeatherMember,
) -> None:
    second_member = replace(weather_member, member_id="fixture-member-02")

    with pytest.raises(ValueError, match="at least three"):
        summarize_member_groups([weather_member, second_member])
