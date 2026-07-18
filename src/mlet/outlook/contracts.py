"""Typed records shared by every Idaho outlook pipeline stage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class WeatherMember:
    grid_id: str
    latitude: float
    longitude: float
    elevation_m: float
    member_id: str
    issued_at: datetime
    valid_date: date
    tmax_c: float
    tmin_c: float
    vapor_pressure_kpa: float
    wind_m_s: float
    solar_mj_m2_day: float
    precip_mm: float


@dataclass(frozen=True)
class SourceRecord:
    name: str
    uri: str
    retrieved_at: datetime
    sha256: str
    observed_through: date | None


@dataclass(frozen=True)
class OutlookQuantiles:
    p10: float
    p50: float
    p90: float


@dataclass(frozen=True)
class OutlookDay:
    grid_id: str
    valid_date: date
    eto_mm: OutlookQuantiles
    potential_et_c_mm: OutlookQuantiles
    eta_well_watered_mm: OutlookQuantiles
    eta_no_irrigation_mm: OutlookQuantiles
    eta_analysis_mm: float | None
    eta_analysis_date: date | None
