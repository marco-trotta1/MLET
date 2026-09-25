"""Build the fixed physical-validity audit and clean Tier 1 cohort."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ml_transfer_audit as audit

OUT = ROOT / "docs/results/ml_tier1"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_SELECTIVE_PROTOCOL.md"
INPUT = audit.OUT / "cohort.csv"
HUMIDITY = audit.OUT / "humidity_audit.csv"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rule_flags(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "actual_vapor_pressure": frame.vp_kpa.notna() & (frame.vp_kpa >= 0),
            "vpd_physical": frame.vpd_kpa.notna()
            & frame.es_kpa.notna()
            & (frame.vpd_kpa >= 0)
            & (frame.vpd_kpa <= frame.es_kpa),
            "wind_plausible": frame.ws.notna() & frame.ws.between(0, 75),
            "temperature_plausible": frame.t_avg.notna()
            & frame.t_avg.between(-50, 60),
        }
    )


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite existing results: {OUT}")
    OUT.mkdir(parents=True)
    cohort = pd.read_csv(INPUT)
    humidity = pd.read_csv(HUMIDITY)
    frame = cohort.merge(humidity, on=["station", "date"], validate="one_to_one")
    flags = rule_flags(frame)
    frame["valid"] = flags.all(axis=1)
    frame["failed_rules"] = flags.apply(
        lambda row: ";".join(row.index[~row.to_numpy()]), axis=1
    )
    cleaned = frame.loc[frame.valid, cohort.columns].copy()
    cleaned.to_csv(OUT / "cohort_clean.csv", index=False)
    frame.to_csv(OUT / "physical_audit_complete_weather.csv", index=False)

    # Audit every labeled station row, including rows without complete weather.
    all_rows = pd.read_csv(ROOT / "data/interim/all_stations.csv")
    flux_root = ROOT / "data/raw/flux_et/flux_ET_dataset/daily_data_files"
    records = []
    columns = ["date", "t_avg", "vpd", "ws", "vp", "es"]
    for station, station_rows in all_rows.groupby("site_id", sort=True):
        source = pd.read_csv(flux_root / f"{station}_daily_data.csv")
        source = source.reindex(columns=columns)
        selected = source.loc[source.date.isin(station_rows.date)].copy()
        selected["station"] = station
        records.append(selected)
    complete = pd.concat(records, ignore_index=True)
    complete = complete.rename(
        columns={"vp": "vp_kpa", "vpd": "vpd_kpa", "es": "es_kpa"}
    )
    complete_flags = rule_flags(complete.rename(columns={"t_avg": "t_avg"}))
    complete["valid"] = complete_flags.all(axis=1)
    summary = {
        "protocol_sha256": sha(PROTOCOL),
        "build_script_sha256": sha(Path(__file__)),
        "source_cohort_sha256": sha(INPUT),
        "humidity_audit_sha256": sha(HUMIDITY),
        "labeled_rows": len(all_rows),
        "labeled_stations": int(all_rows.site_id.nunique()),
        "rows_with_complete_model_weather": len(cohort),
        "stations_with_complete_model_weather": int(cohort.station.nunique()),
        "complete_weather_failures": {
            name: int((~flags[name]).sum()) for name in flags
        },
        "complete_weather_retained_rows": len(cleaned),
        "complete_weather_retained_stations": int(cleaned.station.nunique()),
        "all_labeled_rule_failures": {
            name: int((~complete_flags[name]).sum()) for name in complete_flags
        },
        "all_labeled_rows_retained_by_rule": int(complete.valid.sum()),
        "all_labeled_stations_retained_by_rule": int(
            complete.loc[complete.valid, "station"].nunique()
        ),
        "unknown_required_measurements": {
            name: int(complete[name].isna().sum())
            for name in ["vp_kpa", "vpd_kpa", "es_kpa", "ws", "t_avg"]
        },
    }
    (OUT / "physical_audit.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
