"""FAO-56 radiation chain, ported from neuralhydrology and corrected.

Ported from neuralhydrology v1.13.0 ``neuralhydrology/datautils/pet.py``
(BSD-3-Clause). Equation numbers refer to Allen, R. G., Pereira, L. S.,
Raes, D., & Smith, M. (1998). Crop evapotranspiration: Guidelines for
computing crop water requirements. FAO Irrigation and Drainage Paper 56.

Deviations from upstream are deliberate and recorded in ``UPSTREAM.md``. The
important one: upstream's clear-sky radiation uses an elevation coefficient ten
times the published value. This module implements FAO-56 Eq. 37 as published.

Units are FAO-56 units throughout. Solar radiation is MJ m-2 d-1 to match the
``WeatherMember`` contract, not the W m-2 upstream expects.
"""

from __future__ import annotations

import numpy as np

STEFAN_BOLTZMANN = 4.903e-09  # MJ K-4 m-2 d-1, FAO-56 Eq. 39
DEFAULT_ALBEDO = 0.23  # hypothetical grass reference surface, FAO-56 Eq. 38


def slope_saturation_vapour_pressure(t_mean_c):
    """Slope of the saturation vapour pressure curve (kPa degC-1). Eq. 13."""
    t_mean_c = np.asarray(t_mean_c, dtype=float)
    numerator = 4098 * (0.6108 * np.exp((17.27 * t_mean_c) / (t_mean_c + 237.3)))
    return numerator / (t_mean_c + 237.3) ** 2


def solar_declination(doy):
    """Solar declination (rad). Eq. 24."""
    doy = np.asarray(doy, dtype=float)
    return 0.409 * np.sin((2 * np.pi) / 365 * doy - 1.39)


def inverse_relative_distance(doy):
    """Inverse relative Earth-Sun distance (dimensionless). Eq. 23."""
    doy = np.asarray(doy, dtype=float)
    return 1 + 0.033 * np.cos((2 * np.pi) / 365 * doy)


def sunset_hour_angle(lat_rad, sol_dec_rad):
    """Sunset hour angle (rad). Eq. 25."""
    lat_rad = np.asarray(lat_rad, dtype=float)
    sol_dec_rad = np.asarray(sol_dec_rad, dtype=float)
    return np.arccos(np.clip(-np.tan(lat_rad) * np.tan(sol_dec_rad), -1.0, 1.0))


def extraterrestrial_radiation(lat_rad, sol_dec_rad, sha_rad, ird):
    """Extraterrestrial radiation (MJ m-2 d-1). Eq. 21."""
    lat_rad = np.asarray(lat_rad, dtype=float)
    sol_dec_rad = np.asarray(sol_dec_rad, dtype=float)
    sha_rad = np.asarray(sha_rad, dtype=float)
    ird = np.asarray(ird, dtype=float)
    term1 = (24 * 60) / np.pi * 0.082 * ird
    term2 = (
        sha_rad * np.sin(lat_rad) * np.sin(sol_dec_rad)
        + np.cos(lat_rad) * np.cos(sol_dec_rad) * np.sin(sha_rad)
    )
    return term1 * term2


def clear_sky_radiation(elevation_m, et_rad):
    """Clear-sky solar radiation (MJ m-2 d-1). Eq. 37.

    The published coefficient is 2e-5 per metre. neuralhydrology 1.13.0 writes
    ``2 * 10e-5`` (== 2e-4), overestimating Rso by 19.4% at 824 m. This is the
    published form.
    """
    elevation_m = np.asarray(elevation_m, dtype=float)
    et_rad = np.asarray(et_rad, dtype=float)
    return (0.75 + 2e-5 * elevation_m) * et_rad


def net_shortwave_radiation(solar_mj_m2_day, albedo: float = DEFAULT_ALBEDO):
    """Net shortwave radiation (MJ m-2 d-1). Eq. 38."""
    solar_mj_m2_day = np.asarray(solar_mj_m2_day, dtype=float)
    return (1 - albedo) * solar_mj_m2_day


def actual_vapour_pressure_from_tmin(t_min_c):
    """Actual vapour pressure approximated from Tmin (kPa). Eq. 48."""
    t_min_c = np.asarray(t_min_c, dtype=float)
    return 0.6108 * np.exp((17.27 * t_min_c) / (t_min_c + 237.3))


def net_outgoing_longwave_radiation(t_min_c, t_max_c, solar_mj_m2_day, cs_rad, a_vp):
    """Net outgoing longwave radiation (MJ m-2 d-1). Eq. 39."""
    t_min_c = np.asarray(t_min_c, dtype=float)
    t_max_c = np.asarray(t_max_c, dtype=float)
    solar_mj_m2_day = np.asarray(solar_mj_m2_day, dtype=float)
    cs_rad = np.asarray(cs_rad, dtype=float)
    a_vp = np.asarray(a_vp, dtype=float)
    mean_fourth_power = ((t_max_c + 273.16) ** 4 + (t_min_c + 273.16) ** 4) / 2
    emissivity = 0.34 - 0.14 * np.sqrt(a_vp)
    cloudiness = 1.35 * solar_mj_m2_day / cs_rad - 0.35
    return STEFAN_BOLTZMANN * mean_fourth_power * emissivity * cloudiness


def net_radiation(sw_rad, lw_rad):
    """Net radiation (MJ m-2 d-1). Eq. 40."""
    return np.asarray(sw_rad, dtype=float) - np.asarray(lw_rad, dtype=float)


def atmospheric_pressure(elevation_m):
    """Mean atmospheric pressure (kPa). Eq. 7."""
    elevation_m = np.asarray(elevation_m, dtype=float)
    return 101.3 * ((293.0 - 0.0065 * elevation_m) / 293.0) ** 5.26


def psychrometric_constant(atm_pressure_kpa):
    """Psychrometric constant (kPa degC-1). Eq. 8."""
    return 0.000665 * np.asarray(atm_pressure_kpa, dtype=float)

