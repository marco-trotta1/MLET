"""Priestley-Taylor PET and the three-way ETo cross-check.

Ported from neuralhydrology v1.13.0 ``datautils/pet.py`` (BSD-3-Clause) with two
corrections recorded in ``UPSTREAM.md``: the FAO-56 Eq. 37 elevation
coefficient, and the double energy-to-depth conversion in the PET total.

Nothing here is on the serving path. Its purpose is to give MLET a second
implementation of reference evapotranspiration whose disagreement with the
vendored pyfao56 ASCE-PM path is a measured quantity.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from mlet.outlook.contracts import WeatherMember
from mlet.reference import fao56_radiation as rad

LATENT_HEAT_VAPOURISATION = 2.45
DEFAULT_ALPHA = 1.26
MAX_PLAUSIBLE_SOLAR_MJ_M2_DAY = 50.0
PT_OVER_ASCE_MIN = 0.60
PT_OVER_ASCE_MAX = 1.05


@dataclass(frozen=True)
class EtoComparison:
    """One row of the three-way reference-ET cross-check, all mm d-1."""

    asce_mlet_mm: float
    asce_pyfao56_mm: float
    priestley_taylor_mm: float
    pt_over_asce_ratio: float

    @property
    def within_documented_band(self) -> bool:
        return PT_OVER_ASCE_MIN <= self.pt_over_asce_ratio <= PT_OVER_ASCE_MAX


def priestley_taylor_pet(
    t_min_c,
    t_max_c,
    solar_mj_m2_day,
    latitude_deg,
    elevation_m,
    doy,
    *,
    alpha: float = DEFAULT_ALPHA,
):
    """Priestley-Taylor potential evapotranspiration (mm d-1).

    ``E = (alpha / lambda) * (D / (D + gamma)) * Rn`` with Rn in MJ m-2 d-1.
    The ground heat flux G is taken as zero at daily resolution.

    ``solar_mj_m2_day`` must be MJ m-2 d-1, not W m-2. Passing W m-2 raises,
    because upstream's signature takes W m-2 and a silent acceptance here would
    inflate PET by about 11.6x.
    """
    solar = np.asarray(solar_mj_m2_day, dtype=float)
    if np.any(solar > MAX_PLAUSIBLE_SOLAR_MJ_M2_DAY):
        raise ValueError(
            "solar radiation must be MJ m-2 d-1, not W m-2; "
            f"received a value above {MAX_PLAUSIBLE_SOLAR_MJ_M2_DAY} MJ m-2 d-1"
        )

    t_min = np.asarray(t_min_c, dtype=float)
    t_max = np.asarray(t_max_c, dtype=float)
    lat_rad = np.radians(np.asarray(latitude_deg, dtype=float))

    slope_svp = rad.slope_saturation_vapour_pressure(0.5 * (t_min + t_max))

    sol_dec = rad.solar_declination(doy)
    ird = rad.inverse_relative_distance(doy)
    sha = rad.sunset_hour_angle(lat_rad, sol_dec)
    et_rad = rad.extraterrestrial_radiation(lat_rad, sol_dec, sha, ird)
    cs_rad = rad.clear_sky_radiation(elevation_m, et_rad)

    net_sw = rad.net_shortwave_radiation(solar)
    a_vp = rad.actual_vapour_pressure_from_tmin(t_min)
    net_lw = rad.net_outgoing_longwave_radiation(t_min, t_max, solar, cs_rad, a_vp)
    net_rad = rad.net_radiation(net_sw, net_lw)

    gamma = rad.psychrometric_constant(rad.atmospheric_pressure(elevation_m))

    return (alpha / LATENT_HEAT_VAPOURISATION) * (slope_svp * net_rad) / (slope_svp + gamma)


def compare_eto_implementations(member: WeatherMember) -> EtoComparison:
    """Compare the three reference-ET paths available to MLET on one member.

    GEFS wind speed is supplied at 10 m. pyfao56 performs the standard internal
    adjustment to the 2 m reference height for the ASCE calculation.
    """
    from pyfao56 import refet

    from mlet.outlook.eto import eto_for_member

    doy = member.valid_date.timetuple().tm_yday

    asce_mlet = eto_for_member(member)
    asce_pyfao56 = float(
        refet.ascedaily(
            "S",
            member.elevation_m,
            member.latitude,
            doy,
            member.solar_mj_m2_day,
            member.tmax_c,
            member.tmin_c,
            vapr=member.vapor_pressure_kpa,
            wndsp=member.wind_m_s,
            wndht=10.0,
        )
    )
    pt = float(
        priestley_taylor_pet(
            member.tmin_c,
            member.tmax_c,
            member.solar_mj_m2_day,
            member.latitude,
            member.elevation_m,
            doy,
        )
    )
    if not math.isfinite(asce_mlet) or asce_mlet <= 0:
        raise ValueError("ASCE reference ETo must be finite and positive to compare")
    return EtoComparison(
        asce_mlet_mm=asce_mlet,
        asce_pyfao56_mm=asce_pyfao56,
        priestley_taylor_mm=pt,
        pt_over_asce_ratio=pt / asce_mlet,
    )
