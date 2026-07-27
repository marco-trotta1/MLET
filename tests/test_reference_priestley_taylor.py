"""Non-scientific deterministic checks for Priestley-Taylor PET and the ETo cross-check.

The fixture is the same non-scientific row used by tests/test_outlook_eto.py:
2026-07-15, 43.6175 N, 824 m, srad 28 MJ m-2 d-1, Tmax 33 C, Tmin 15 C.
"""

from datetime import date, datetime, timezone

import numpy as np
import pytest

from mlet.outlook.contracts import WeatherMember
from mlet.reference.priestley_taylor import (
    EtoComparison,
    compare_eto_implementations,
    priestley_taylor_pet,
)

FIXTURE_TMIN = 15.0
FIXTURE_TMAX = 33.0
FIXTURE_SRAD = 28.0
FIXTURE_LAT = 43.6175
FIXTURE_ELEV = 824.0
FIXTURE_DOY = 196


@pytest.fixture
def weather_member() -> WeatherMember:
    return WeatherMember(
        grid_id="fixture-grid-a",
        latitude=FIXTURE_LAT,
        longitude=-116.1997,
        elevation_m=FIXTURE_ELEV,
        member_id="fixture-member-01",
        issued_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
        valid_date=date(2026, 7, 15),
        tmax_c=FIXTURE_TMAX,
        tmin_c=FIXTURE_TMIN,
        vapor_pressure_kpa=1.2,
        wind_m_s=2.5,
        solar_mj_m2_day=FIXTURE_SRAD,
        precip_mm=0.0,
    )


def test_priestley_taylor_applies_the_energy_conversion_exactly_once() -> None:
    """Upstream neuralhydrology divides by lambda twice; PET must not.

    Priestley-Taylor: E = (alpha / lambda) * (D / (D + gamma)) * Rn, with Rn in
    MJ m-2 d-1 and lambda = 2.45 MJ kg-1. The factor 0.408 is 1/lambda, so
    multiplying by it after dividing by lambda understates PET by 2.451x.
    """
    result = priestley_taylor_pet(
        FIXTURE_TMIN, FIXTURE_TMAX, FIXTURE_SRAD, FIXTURE_LAT, FIXTURE_ELEV, FIXTURE_DOY
    )
    assert float(result) == pytest.approx(6.2683, abs=1e-3)

    upstream_double_conversion = float(result) * 0.408
    assert upstream_double_conversion == pytest.approx(2.5575, abs=1e-3)
    assert float(result) / upstream_double_conversion == pytest.approx(2.4510, abs=1e-3)


def test_priestley_taylor_alpha_is_linear_and_documented() -> None:
    base = float(
        priestley_taylor_pet(
            FIXTURE_TMIN, FIXTURE_TMAX, FIXTURE_SRAD, FIXTURE_LAT, FIXTURE_ELEV, FIXTURE_DOY
        )
    )
    doubled = float(
        priestley_taylor_pet(
            FIXTURE_TMIN,
            FIXTURE_TMAX,
            FIXTURE_SRAD,
            FIXTURE_LAT,
            FIXTURE_ELEV,
            FIXTURE_DOY,
            alpha=2.52,
        )
    )
    assert doubled == pytest.approx(2 * base, rel=1e-12)


def test_priestley_taylor_rejects_watts_per_square_metre() -> None:
    """A W m-2 value (about 324) must not be silently accepted as MJ m-2 d-1."""
    with pytest.raises(ValueError, match="MJ m-2 d-1"):
        priestley_taylor_pet(
            FIXTURE_TMIN, FIXTURE_TMAX, 324.0, FIXTURE_LAT, FIXTURE_ELEV, FIXTURE_DOY
        )


def test_priestley_taylor_is_array_safe() -> None:
    result = priestley_taylor_pet(
        np.array([10.0, 15.0]),
        np.array([28.0, 33.0]),
        np.array([24.0, 28.0]),
        FIXTURE_LAT,
        FIXTURE_ELEV,
        np.array([180, 196]),
    )
    assert result.shape == (2,)
    assert np.all(result > 0)


def test_comparison_agrees_exactly_where_the_equation_is_shared(
    weather_member: WeatherMember,
) -> None:
    comparison = compare_eto_implementations(weather_member)
    assert isinstance(comparison, EtoComparison)
    assert comparison.asce_mlet_mm == comparison.asce_pyfao56_mm


def test_comparison_ratio_sits_in_the_documented_band(
    weather_member: WeatherMember,
) -> None:
    """PT has no aerodynamic term, so it should fall below ASCE-PM but stay close.

    The 0.60-1.05 band is wide enough for real physical disagreement and narrow
    enough to catch a factor-of-2.45 unit error or a 10x radiation coefficient.
    """
    comparison = compare_eto_implementations(weather_member)
    assert comparison.asce_mlet_mm == pytest.approx(7.2813, abs=1e-3)
    assert comparison.priestley_taylor_mm == pytest.approx(6.2683, abs=1e-3)
    assert 0.60 <= comparison.pt_over_asce_ratio <= 1.05
    assert comparison.pt_over_asce_ratio == pytest.approx(0.861, abs=1e-2)
