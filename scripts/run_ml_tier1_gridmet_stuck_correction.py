"""Run the exploratory daily-gridMET stuck-wind correction."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ml_tier1_gridmet as experiment

COHORT = ROOT / "docs/results/ml_tier1_gridmet/cohort.csv"
OUT = ROOT / "docs/results/ml_tier1_gridmet_stuck_corrected"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_GRIDMET_STUCK_CORRECTION_PROTOCOL.md"
ORIGINAL_OUT = ROOT / "docs/results/ml_tier1_gridmet_10member"
TEST_YEARS = set(range(2012, 2021))
INPUT_TOLERANCE = 1e-8


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def daily_stuck_inputs(cohort: pd.DataFrame) -> tuple[pd.DataFrame, dict[int, float], dict[str, str]]:
    records = []
    source_hashes = {}
    for (station, year), rows in cohort.groupby(["station", "year"], sort=True):
        path = ROOT / "data/raw/gridmet_weather" / f"{station}_{year}_vs.nc"
        if not path.is_file():
            raise FileNotFoundError(f"Missing daily GridMET wind file: {path.name}")
        with xr.open_dataset(path, mask_and_scale=False) as dataset:
            dates = pd.DatetimeIndex(pd.to_datetime(dataset["time"].to_numpy())).normalize()
            encoded = dataset["wind_speed"].to_numpy().astype(float).reshape(-1)
        if dates.has_duplicates or not dates.is_monotonic_increasing:
            raise ValueError(f"Daily dates are invalid in {path.name}")
        expected_dates = pd.date_range(dates[0], dates[-1], freq="D")
        if not dates.equals(expected_dates):
            raise ValueError(f"Daily dates are not contiguous in {path.name}")
        valid = np.isfinite(encoded) & (encoded != 32767) & (encoded >= 0)
        wind = np.full(encoded.shape, np.nan, dtype=float)
        wind[valid] = encoded[valid] * 0.1
        if not np.isfinite(wind).all():
            raise ValueError(f"Daily wind has missing values in {path.name}")
        source_hashes[path.name] = sha256(path)
        for row in rows.itertuples(index=False):
            sample_date = pd.Timestamp(row.date).normalize()
            offset = int((sample_date - dates[0]).days)
            if offset < 0 or offset >= len(dates) or dates[offset] != sample_date:
                raise ValueError(f"No daily GridMET value for {station} on {sample_date.date()}")
            block_start = (offset // 7) * 7
            block_date = dates[block_start]
            original_wind = float(row.ws)
            expected_wind = float(wind[offset])
            if not np.isclose(original_wind, expected_wind, rtol=0.0, atol=5e-7):
                raise ValueError(f"Cohort wind does not match {path.name} on {sample_date.date()}")
            records.append(
                {
                    "row_id": int(row.row_id),
                    "station": station,
                    "year": int(year),
                    "date": sample_date.strftime("%Y-%m-%d"),
                    "block_start": block_date.strftime("%Y-%m-%d"),
                    "gridmet_wind_original_m_s": original_wind,
                    "gridmet_wind_stuck_m_s": float(wind[block_start]),
                }
            )
    values = pd.DataFrame.from_records(records).sort_values("row_id").reset_index(drop=True)
    if len(values) != len(cohort) or values.row_id.duplicated().any():
        raise ValueError("Daily stuck inputs do not cover each cohort row once")
    lookup = dict(zip(values.row_id.astype(int), values.gridmet_wind_stuck_m_s.astype(float)))
    return values, lookup, source_hashes


def legacy_changed_rows(cohort: pd.DataFrame, features: list[str]) -> int:
    changed = 0
    for year in sorted(TEST_YEARS):
        test = cohort.loc[cohort.year == year]
        training = cohort.loc[cohort.year < year]
        variants = experiment.tier1.fault_inputs(
            test, test[features].to_numpy(), training, features
        )
        original = variants["wind_stuck_7_days"][:, features.index("ws")]
        changed += int(
            (~np.isclose(original, test.ws.to_numpy(), rtol=0.0, atol=INPUT_TOLERANCE)).sum()
        )
    return changed


def corrected_fault_inputs(lookup: dict[int, float]):
    original_fault_inputs = experiment.tier1.fault_inputs

    def apply(frame, inputs, training, columns):
        variants = original_fault_inputs(frame, inputs, training, columns)
        row_ids = frame.row_id.astype(int).to_numpy()
        try:
            held_wind = np.array([lookup[row_id] for row_id in row_ids], dtype=float)
        except KeyError as exc:
            raise ValueError(f"No corrected wind value for row {exc.args[0]}") from exc
        transformed = variants["wind_stuck_7_days"].copy()
        transformed[:, columns.index("ws")] = held_wind
        variants["wind_stuck_7_days"] = transformed
        return variants

    return apply


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite results in {OUT}")
    cohort = pd.read_csv(COHORT, parse_dates=["date"])
    values, lookup, source_hashes = daily_stuck_inputs(cohort)
    legacy_rows = legacy_changed_rows(cohort, experiment.audit.FEATURES)
    test_values = values.loc[values.year.isin(TEST_YEARS)]
    changed_mask = ~np.isclose(
        test_values.gridmet_wind_original_m_s.to_numpy(),
        test_values.gridmet_wind_stuck_m_s.to_numpy(),
        rtol=0.0,
        atol=INPUT_TOLERANCE,
    )

    experiment.OUT = OUT
    experiment.tier1.fault_inputs = corrected_fault_inputs(lookup)
    with threadpool_limits(limits=1):
        experiment.run()

    values.to_csv(OUT / "wind_stuck_daily_inputs.csv", index=False, float_format="%.8f")
    receipt_path = OUT / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["stuck_correction"] = {
        "protocol_sha256": sha256(PROTOCOL),
        "runner_sha256": sha256(Path(__file__)),
        "original_runner_sha256": sha256(Path(experiment.__file__)),
        "original_transform_sha256": sha256(Path(experiment.tier1.__file__)),
        "original_receipt_sha256": sha256(ORIGINAL_OUT / "receipt.json"),
        "original_results_sha256": sha256(ORIGINAL_OUT / "results.json"),
        "cohort_sha256": sha256(COHORT),
        "daily_input_sha256": sha256(OUT / "wind_stuck_daily_inputs.csv"),
        "daily_gridmet_wind_sha256": source_hashes,
        "xarray_version": xr.__version__,
        "definition": "seven-day blocks start at each station-year cache's first date; each block uses its first daily wind value",
        "rows_mapped": int(len(values)),
        "test_rows": int(len(test_values)),
        "corrected_test_wind_values_changed": int(changed_mask.sum()),
        "corrected_test_wind_values_changed_fraction": float(changed_mask.mean()),
        "original_test_wind_values_changed": legacy_rows,
        "input_tolerance_m_s": INPUT_TOLERANCE,
        "exploratory": True,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt["stuck_correction"], indent=2))


if __name__ == "__main__":
    main()
