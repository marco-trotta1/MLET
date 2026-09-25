"""Run Tier 1 gridMET sensitivity arms across split seeds and distances."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import build_ml_tier1_gridmet_cohort as cohort_builder
import ml_tier1_gridmet as tier1_runner
import analyze_ml_tier1_gridmet as tier1_analysis
import ml_transfer_audit as audit

OUT = ROOT / "docs/results/ml_tier1_gridmet_sensitivity"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_GRIDMET_SPLIT_PROXIMITY_PROTOCOL.md"
BASE = ROOT / "docs/results/ml_tier1_gridmet_10member"
PRIMARY_COHORT = ROOT / "docs/results/ml_tier1_gridmet/cohort.csv"
METADATA = ROOT / "data/raw/openet_phase2/OpenET_PhaseII_model_ET_dataset/Station_metadata.xlsx"
THRESHOLDS_KM = [5, 10, 25]
SPLIT_SEEDS = list(range(20260924, 20260934))
NEEDED_COLUMNS = [
    "row_id",
    "test_year",
    "station",
    "group",
    "y",
    "openet",
    "Gain",
    "SupportGain",
]
OPTIONAL_COLUMNS = ["accept_Gain", "accept_SupportGain"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def make_cohorts() -> tuple[dict[int, Path], dict[int, int]]:
    original = pd.read_csv(PRIMARY_COHORT, parse_dates=["date"])
    metadata = cohort_builder.load_station_metadata(str(METADATA))
    stations = sorted(original.station.unique())
    paths = {10: PRIMARY_COHORT}
    counts: dict[int, int] = {}

    for threshold in THRESHOLDS_KM:
        groups = cohort_builder.proximity_groups(metadata, stations, float(threshold))
        assigned = original.station.map(groups)
        if assigned.isna().any():
            raise ValueError(f"The {threshold} km map omits a cohort station")
        counts[threshold] = len(set(groups.values()))
        if threshold == 10:
            if not original.group.reset_index(drop=True).equals(
                assigned.reset_index(drop=True)
            ):
                raise ValueError("The 10 km map differs from the frozen cohort")
            continue

        frame = original.copy()
        frame["group"] = assigned
        path = OUT / "cohorts" / f"cohort_{threshold}km.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = pd.read_csv(path, parse_dates=["date"])
            if not frame.equals(existing):
                raise RuntimeError(f"The saved {threshold} km cohort has changed")
        else:
            frame.to_csv(path, index=False, float_format="%.8f")
        paths[threshold] = path

    expected_counts = {5: 113, 10: 102, 25: 86}
    if counts != expected_counts:
        raise ValueError(f"Proximity group counts differ from the frozen protocol: {counts}")
    return paths, counts


def manifest_records(cohort_paths: dict[int, Path]) -> list[dict]:
    records = []
    for threshold in THRESHOLDS_KM:
        for seed_index, split_seed in enumerate(SPLIT_SEEDS):
            anchor = threshold == 10 and split_seed == 20260924
            run_path = BASE if anchor else OUT / f"threshold_{threshold}km" / f"seed_{split_seed}"
            records.append(
                {
                    "threshold_km": threshold,
                    "seed_index": seed_index,
                    "split_seed": split_seed,
                    "anchor": anchor,
                    "cohort_path": str(cohort_paths[threshold].relative_to(ROOT)),
                    "run_path": str(run_path.relative_to(ROOT)),
                    "status": "planned",
                }
            )
    return records


def validate_anchor(cohort_path: Path) -> None:
    receipt_path = BASE / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if sha256(cohort_path) != receipt["cohort_sha256"]:
        raise ValueError("The anchor cohort hash does not match the frozen run")
    if receipt["split_seed"] != 20260924:
        raise ValueError("The anchor split seed does not match the protocol")
    if receipt["script_sha256"] != sha256(Path(tier1_runner.__file__)):
        raise ValueError("The anchor script hash does not match the current script")
    if receipt["splits_sha256"] != sha256(BASE / "splits.json"):
        raise ValueError("The anchor split hash does not match its receipt")
    if receipt["neural_seeds"] != tier1_runner.NEURAL_SEEDS:
        raise ValueError("The anchor neural seeds do not match the protocol")
    if receipt["fault_seed"] != tier1_runner.tier1.FAULT_SEED:
        raise ValueError("The anchor fault seed does not match the protocol")
    for condition in tier1_analysis.CONDITIONS:
        if not (BASE / f"predictions_{condition}.csv").is_file():
            raise ValueError(f"The anchor lacks predictions for {condition}")


def compress_predictions(run_path: Path) -> dict[str, str]:
    hashes = {}
    keep_columns = NEEDED_COLUMNS + OPTIONAL_COLUMNS
    for condition in tier1_analysis.CONDITIONS:
        source = run_path / f"predictions_{condition}.csv"
        target = run_path / f"predictions_{condition}.csv.gz"
        if source.is_file():
            frame = pd.read_csv(source)
            missing = sorted(set(NEEDED_COLUMNS) - set(frame.columns))
            if missing:
                raise ValueError(f"{condition} predictions lack columns: {missing}")
            columns = [name for name in keep_columns if name in frame]
            temporary = target.with_suffix(target.suffix + ".tmp")
            frame[columns].to_csv(
                temporary,
                index=False,
                float_format="%.17g",
                compression="gzip",
            )
            temporary.replace(target)
            source.unlink()
        if not target.is_file():
            raise RuntimeError(f"The run lacks saved predictions for {condition}")
        hashes[condition] = sha256(target)
    return hashes


def validate_completed_run(run_path: Path, cohort_path: Path, split_seed: int) -> None:
    receipt_path = run_path / "receipt.json"
    results_path = run_path / "results.json"
    splits_path = run_path / "splits.json"
    if not receipt_path.is_file() or not results_path.is_file() or not splits_path.is_file():
        raise RuntimeError(f"The run is incomplete: {run_path}")
    receipt = json.loads(receipt_path.read_text())
    if receipt["protocol_sha256"] != sha256(PROTOCOL):
        raise ValueError(f"The run uses a different protocol: {run_path}")
    if receipt["script_sha256"] != sha256(Path(tier1_runner.__file__)):
        raise ValueError(f"The run uses a different Tier 1 script: {run_path}")
    if receipt["cohort_sha256"] != sha256(cohort_path):
        raise ValueError(f"The run uses a different cohort: {run_path}")
    if receipt["split_seed"] != split_seed:
        raise ValueError(f"The run uses a different split seed: {run_path}")
    if receipt["splits_sha256"] != sha256(splits_path):
        raise ValueError(f"The run split hash is invalid: {run_path}")


def finish_run(record: dict) -> None:
    run_path = ROOT / record["run_path"]
    cohort_path = ROOT / record["cohort_path"]
    validate_completed_run(run_path, cohort_path, record["split_seed"])
    prediction_hashes = compress_predictions(run_path)
    run_receipt = run_path / "receipt.json"
    receipt = {
        "protocol_sha256": sha256(PROTOCOL),
        "runner_sha256": sha256(Path(__file__)),
        "tier1_script_sha256": sha256(Path(tier1_runner.__file__)),
        "cohort_sha256": sha256(cohort_path),
        "run_receipt_sha256": sha256(run_receipt),
        "results_sha256": sha256(run_path / "results.json"),
        "splits_sha256": sha256(run_path / "splits.json"),
        "split_seed": record["split_seed"],
        "threshold_km": record["threshold_km"],
        "prediction_columns": NEEDED_COLUMNS + OPTIONAL_COLUMNS,
        "compressed_predictions": prediction_hashes,
    }
    write_json(run_path / "sensitivity_run_receipt.json", receipt)


def validate_prior_manifest(path: Path, expected: dict) -> dict:
    if not path.exists():
        if any(item.name != "cohorts" for item in OUT.iterdir()):
            raise RuntimeError("The sensitivity directory has files without a manifest")
        write_json(path, expected)
        return expected
    saved = json.loads(path.read_text())
    if saved["protocol_sha256"] != expected["protocol_sha256"]:
        raise ValueError("The saved run manifest uses a different protocol")
    if saved["runner_sha256"] != expected["runner_sha256"]:
        raise ValueError("The saved run manifest uses a different runner")
    if saved["tier1_script_sha256"] != expected["tier1_script_sha256"]:
        raise ValueError("The saved run manifest uses a different Tier 1 script")
    if saved["group_counts"] != expected["group_counts"]:
        raise ValueError("The saved run manifest uses different group counts")
    if len(saved["runs"]) != len(expected["runs"]):
        raise ValueError("The saved run manifest has different configurations")
    for saved_record, expected_record in zip(saved["runs"], expected["runs"]):
        for key, value in expected_record.items():
            if key != "status" and saved_record.get(key) != value:
                raise ValueError("The saved run manifest has different configurations")
    return saved


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cohort_paths, group_counts = make_cohorts()
    records = manifest_records(cohort_paths)
    manifest_path = OUT / "run_manifest.json"
    manifest = validate_prior_manifest(
        manifest_path,
        {
            "protocol_sha256": sha256(PROTOCOL),
            "runner_sha256": sha256(Path(__file__)),
            "tier1_script_sha256": sha256(Path(tier1_runner.__file__)),
            "group_counts": {str(key): value for key, value in group_counts.items()},
            "runs": records,
        },
    )
    if manifest["tier1_script_sha256"] != sha256(Path(tier1_runner.__file__)):
        raise ValueError("The manifest Tier 1 script hash is invalid")
    validate_anchor(PRIMARY_COHORT)

    for record in manifest["runs"]:
        run_path = ROOT / record["run_path"]
        cohort_path = ROOT / record["cohort_path"]
        if record["anchor"]:
            record["status"] = "complete"
            record["run_receipt_sha256"] = sha256(BASE / "receipt.json")
            for condition in tier1_analysis.CONDITIONS:
                record.setdefault("prediction_hashes", {})[condition] = sha256(
                    BASE / f"predictions_{condition}.csv"
                )
        else:
            wrapper_receipt = run_path / "sensitivity_run_receipt.json"
            if wrapper_receipt.is_file():
                saved = json.loads(wrapper_receipt.read_text())
                validate_completed_run(run_path, cohort_path, record["split_seed"])
                if saved["threshold_km"] != record["threshold_km"]:
                    raise ValueError(f"The saved run receipt has a different threshold: {run_path}")
                if saved["runner_sha256"] != sha256(Path(__file__)):
                    raise ValueError(f"The saved run receipt uses a different runner: {run_path}")
                if saved["run_receipt_sha256"] != sha256(run_path / "receipt.json"):
                    raise ValueError(f"The saved Tier 1 receipt hash is invalid: {run_path}")
                for condition, expected_hash in saved["compressed_predictions"].items():
                    prediction_path = run_path / f"predictions_{condition}.csv.gz"
                    if not prediction_path.is_file():
                        raise FileNotFoundError(f"Missing saved predictions: {prediction_path}")
                    if sha256(prediction_path) != expected_hash:
                        raise ValueError(f"The saved prediction hash is invalid: {prediction_path}")
                if set(saved["compressed_predictions"]) != set(tier1_analysis.CONDITIONS):
                    raise ValueError(f"The saved run receipt lacks conditions: {run_path}")
                if saved["protocol_sha256"] != sha256(PROTOCOL):
                    raise ValueError(f"The saved run receipt uses a different protocol: {run_path}")
            else:
                if run_path.exists() and any(run_path.iterdir()):
                    if (run_path / "receipt.json").is_file():
                        finish_run(record)
                    else:
                        raise RuntimeError(f"The run has incomplete files: {run_path}")
                else:
                    run_path.parent.mkdir(parents=True, exist_ok=True)
                    tier1_runner.OUT = run_path
                    tier1_runner.COHORT = cohort_path
                    tier1_runner.PROTOCOL = PROTOCOL
                    tier1_runner.SPLIT_SEED = record["split_seed"]
                    print(
                        f"Starting {record['threshold_km']} km, seed {record['split_seed']}",
                        flush=True,
                    )
                    tier1_runner.run()
                    finish_run(record)
            record["status"] = "complete"
            record["run_receipt_sha256"] = sha256(run_path / "receipt.json")
            saved_run_receipt = json.loads(
                (run_path / "sensitivity_run_receipt.json").read_text()
            )
            record["prediction_hashes"] = saved_run_receipt["compressed_predictions"]

        write_json(manifest_path, manifest)
        print(
            f"Completed {record['threshold_km']} km, seed {record['split_seed']}",
            flush=True,
        )

    if any(record["status"] != "complete" for record in manifest["runs"]):
        raise RuntimeError("The sensitivity run manifest is incomplete")
    print("Tier 1 split and proximity sensitivity runs complete.", flush=True)


if __name__ == "__main__":
    run()
