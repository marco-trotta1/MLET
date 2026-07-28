"""Non-scientific deterministic checks for the independent FAO-56 radiation chain.

Each expected value is the FAO-56 (Allen et al., 1998) equation transcribed
directly from the publication, independently of the implementation under test.
"""

import math

import numpy as np
import pytest

from mlet.reference import fao56_radiation as rad


def test_slope_saturation_vapour_pressure_matches_equation_13() -> None:
    t_mean = 24.0
    expected = (
        4098 * (0.6108 * math.exp((17.27 * t_mean) / (t_mean + 237.3)))
        / ((t_mean + 237.3) ** 2)
    )
    assert rad.slope_saturation_vapour_pressure(t_mean) == pytest.approx(expected, rel=1e-12)


def test_atmospheric_pressure_matches_equation_7() -> None:
    elevation_m = 824.0
    expected = 101.3 * ((293.0 - 0.0065 * elevation_m) / 293.0) ** 5.26
    assert rad.atmospheric_pressure(elevation_m) == pytest.approx(expected, rel=1e-12)


def test_psychrometric_constant_matches_equation_8() -> None:
    assert rad.psychrometric_constant(91.9) == pytest.approx(0.000665 * 91.9, rel=1e-12)


def test_extraterrestrial_radiation_matches_equation_21() -> None:
    lat_rad = math.radians(43.6175)
    doy = 196
    sol_dec = 0.409 * math.sin(2 * math.pi / 365 * doy - 1.39)
    ird = 1 + 0.033 * math.cos(2 * math.pi / 365 * doy)
    sha = math.acos(-math.tan(lat_rad) * math.tan(sol_dec))
    expected = (24 * 60) / math.pi * 0.082 * ird * (
        sha * math.sin(lat_rad) * math.sin(sol_dec)
        + math.cos(lat_rad) * math.cos(sol_dec) * math.sin(sha)
    )
    assert rad.solar_declination(doy) == pytest.approx(sol_dec, rel=1e-12)
    assert rad.inverse_relative_distance(doy) == pytest.approx(ird, rel=1e-12)
    assert rad.sunset_hour_angle(lat_rad, sol_dec) == pytest.approx(sha, rel=1e-12)
    assert rad.extraterrestrial_radiation(lat_rad, sol_dec, sha, ird) == pytest.approx(
        expected, rel=1e-12
    )


def test_clear_sky_radiation_uses_the_published_elevation_coefficient() -> None:
    """FAO-56 Eq. 37: Rso = (0.75 + 2e-5 * z) * Ra.

    neuralhydrology 1.13.0 writes ``2 * 10e-5``, which is 1e-4 * 2 = 2e-4, ten
    times the published coefficient. This asserts MLET does not inherit that.
    """
    et_rad = 41.0
    elevation_m = 824.0
    expected = (0.75 + 2e-5 * elevation_m) * et_rad
    assert rad.clear_sky_radiation(elevation_m, et_rad) == pytest.approx(expected, rel=1e-12)

    upstream_defect = (0.75 + 2 * 10e-5 * elevation_m) * et_rad
    assert upstream_defect / expected == pytest.approx(1.1935, abs=1e-4)
    assert rad.clear_sky_radiation(elevation_m, et_rad) != pytest.approx(upstream_defect)


def test_net_outgoing_longwave_radiation_matches_equation_39() -> None:
    t_min, t_max, solar, cs_rad, a_vp = 15.0, 33.0, 28.0, 31.4, 1.7
    expected = (
        4.903e-09
        * (((t_max + 273.16) ** 4 + (t_min + 273.16) ** 4) / 2)
        * (0.34 - 0.14 * math.sqrt(a_vp))
        * (1.35 * solar / cs_rad - 0.35)
    )
    assert rad.net_outgoing_longwave_radiation(
        t_min, t_max, solar, cs_rad, a_vp
    ) == pytest.approx(expected, rel=1e-12)


def test_net_shortwave_and_net_radiation() -> None:
    assert rad.net_shortwave_radiation(28.0) == pytest.approx((1 - 0.23) * 28.0, rel=1e-12)
    assert rad.net_radiation(21.56, 5.2) == pytest.approx(16.36, rel=1e-12)


def test_actual_vapour_pressure_from_tmin_matches_equation_48() -> None:
    t_min = 15.0
    expected = 0.6108 * math.exp((17.27 * t_min) / (t_min + 237.3))
    assert rad.actual_vapour_pressure_from_tmin(t_min) == pytest.approx(expected, rel=1e-12)


def test_functions_are_array_safe() -> None:
    doy = np.array([1, 100, 196, 365])
    declination = rad.solar_declination(doy)
    assert isinstance(declination, np.ndarray)
    assert declination.shape == (4,)
    assert np.all(np.isfinite(declination))
