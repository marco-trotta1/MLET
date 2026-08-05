"""Assemble immutable ETo-only target artifacts from station observations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

from mlet.outlook.dates import outlook_valid_date
from mlet.sources.agrimet import AgriMetEtosObservation, AgriMetGridMatch


_TARGET_KIND = "independent_asce_short_reference_eto"
_RETROSPECTIVE_REFORECAST = "retrospective_reforecast"


@dataclass(frozen=True, slots=True)
class SourceTiming:
    """Record source issue time and later archive availability explicitly."""

    temporal_role: str
    source_issue_at: datetime
    archive_available_at: datetime

    def __post_init__(self) -> None:
        if self.temporal_role != _RETROSPECTIVE_REFORECAST:
            raise ValueError("source timing temporal_role must be retrospective_reforecast")
        _require_utc(self.source_issue_at, "source_issue_at")
        _require_utc(self.archive_available_at, "archive_available_at")
        if self.archive_available_at < self.source_issue_at:
            raise ValueError("archive_available_at must not precede source_issue_at")


def build_eto_target_artifact(
    *,
    case_id: str,
    run_id: str,
    issue_time: datetime,
    observations: Sequence[AgriMetEtosObservation],
    matches: Mapping[str, AgriMetGridMatch],
    baseline_p50_mm: Mapping[tuple[str, date], float],
    destination: Path,
    exclusions: Sequence[Mapping[str, object]] = (),
) -> Path:
    """Write one strict v2 target artifact for one forecast issue.

    The caller must provide a fixed station and day-of-year baseline built from
    strictly prior calendar years. This function records that precomputed
    value. It does not estimate a baseline from target observations.
    """
    issue = _require_utc(issue_time, "issue_time")
    _require_text(case_id, "case_id")
    _require_text(run_id, "run_id")
    if not observations or any(
        not isinstance(item, AgriMetEtosObservation) for item in observations
    ):
        raise ValueError("ETo target artifact requires AgriMetEtosObservation values")
    exclusion_values = _validate_exclusions(exclusions, issue)
    values = []
    available_times = []
    source_identities = set()
    seen: set[tuple[str, int]] = set()
    for observation in sorted(observations, key=lambda item: (item.station_id, item.valid_date)):
        match = matches.get(observation.station_id)
        if match is None or match.station_id != observation.station_id:
            raise ValueError("each AgriMet observation requires its station-grid match")
        lead_day = _lead_day_for_date(issue, observation.valid_date)
        baseline = baseline_p50_mm.get((observation.station_id, observation.valid_date))
        if type(baseline) not in (int, float) or float(baseline) < 0.0:
            raise ValueError("each ETo target requires a finite non-negative baseline_p50_mm")
        key = (observation.station_id, lead_day)
        if key in seen:
            raise ValueError("ETo target artifact contains duplicate station and lead")
        seen.add(key)
        source_identities.add((observation.uri, observation.source_version))
        available_times.append(observation.available_at)
        values.append(
            {
                "target_id": f"agrimet:{observation.station_id}",
                "grid_id": match.grid_id,
                "latitude": observation.latitude,
                "longitude": observation.longitude,
                "lead_day": lead_day,
                "valid_date": observation.valid_date.isoformat(),
                "target_mm": observation.etos_mm,
                "baseline_p50_mm": float(baseline),
                "target_kind": _TARGET_KIND,
            }
        )
    value_keys = {
        (value["target_id"], value["valid_date"])
        for value in values
    }
    for exclusion in exclusion_values:
        if (exclusion["target_id"], exclusion["valid_date"]) in value_keys:
            raise ValueError("ETo target exclusion overlaps a target value")
    if len(source_identities) != 1:
        raise ValueError("ETo target artifact requires one source URI and version")
    source_uri, source_version = source_identities.pop()
    payload = {
        "schema_version": 2,
        "kind": "idaho_outlook_eto_hindcast_target",
        "receipt": {
            "case_id": case_id,
            "run_id": run_id,
            "uri": source_uri,
            "source_version": source_version,
            "available_at": _format_utc(max(available_times)),
        },
        "exclusions": exclusion_values,
        "values": values,
    }
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("ETo target artifact destination must not already exist")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ValueError("ETo target artifact parent must be a real directory")
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    with destination.open("xb") as handle:
        handle.write(encoded)
    return destination


def _validate_exclusions(
    exclusions: Sequence[Mapping[str, object]], issue_time: datetime
) -> list[dict[str, str]]:
    if not isinstance(exclusions, Sequence) or isinstance(exclusions, (str, bytes)):
        raise ValueError("ETo target exclusions must be a sequence")
    expected_dates = {outlook_valid_date(issue_time, lead) for lead in range(1, 21)}
    seen: set[tuple[str, date]] = set()
    result: list[dict[str, str]] = []
    for exclusion in exclusions:
        if not isinstance(exclusion, Mapping) or set(exclusion) != {
            "target_id",
            "valid_date",
            "reason",
        }:
            raise ValueError(
                "ETo target exclusions must contain target_id, valid_date, and reason"
            )
        target_id = _require_text(exclusion["target_id"], "exclusion target_id")
        valid_date = exclusion["valid_date"]
        if isinstance(valid_date, str):
            try:
                parsed_date = date.fromisoformat(valid_date)
            except ValueError as error:
                raise ValueError("exclusion valid_date must be an ISO date") from error
            if parsed_date.isoformat() != valid_date:
                raise ValueError("exclusion valid_date must be an ISO date")
            valid_date = parsed_date
        if not isinstance(valid_date, date) or isinstance(valid_date, datetime):
            raise ValueError("exclusion valid_date must be a date")
        if valid_date not in expected_dates:
            raise ValueError("exclusion valid_date must be within the 20-day horizon")
        reason = _require_text(exclusion["reason"], "exclusion reason")
        key = (target_id, valid_date)
        if key in seen:
            raise ValueError("ETo target exclusions must not duplicate target and date")
        seen.add(key)
        result.append(
            {
                "target_id": target_id,
                "valid_date": valid_date.isoformat(),
                "reason": reason,
            }
        )
    return sorted(result, key=lambda item: (item["target_id"], item["valid_date"]))


def assemble_eto_hindcast_evidence(
    *,
    case_id: str,
    issue_time: datetime,
    forecast_directory: Path,
    target_path: Path,
    source_timing: Mapping[str, SourceTiming],
    held_out_fold: int,
    held_out_season: str,
    destination: Path,
) -> Path:
    """Write one strict ETo-only schema-v4 evidence bundle.

    The caller gives immutable forecast and target artifacts. This function
    copies their verified bytes into a new evidence directory and records the
    input availability and holdout boundary. It does not create ETc or ETa
    scenario receipts because those layers are outside the ETo validation
    scope.
    """
    issue = _require_utc(issue_time, "issue_time")
    _require_text(case_id, "case_id")
    if type(held_out_fold) is not int or held_out_fold not in range(5):
        raise ValueError("held_out_fold must be an integer from 0 through 4")
    if held_out_season not in {"DJF", "MAM", "JJA", "SON"}:
        raise ValueError("held_out_season must be DJF, MAM, JJA, or SON")

    supplied_forecast_root = Path(forecast_directory)
    if supplied_forecast_root.is_symlink():
        raise ValueError("forecast_directory must not be a symlink")
    forecast_root = supplied_forecast_root.resolve(strict=True)
    if not forecast_root.is_dir():
        raise ValueError("forecast_directory must be a real directory")
    manifest_path = _regular_child(forecast_root, "manifest.json")
    outlook_path = _regular_child(forecast_root, "outlook.json")
    from mlet.outlook.manifest import RunManifest

    manifest_bytes = manifest_path.read_bytes()
    manifest = RunManifest.from_json(manifest_bytes.decode("utf-8"))
    if manifest.issued_at != issue:
        raise ValueError("forecast manifest issued_at must match issue_time")
    outlook_bytes = outlook_path.read_bytes()
    outlook_digest = _sha256(outlook_bytes)
    if dict(manifest.artifact_sha256).get("outlook.json") != outlook_digest:
        raise ValueError("forecast manifest must bind outlook.json bytes")

    supplied_target = Path(target_path)
    if supplied_target.is_symlink():
        raise ValueError("target_path must not be a symlink")
    target = supplied_target.resolve(strict=True)
    if not target.is_file():
        raise ValueError("target_path must name a regular file")
    target_bytes = target.read_bytes()
    target_payload = _read_json_object(target_bytes, "ETo target artifact")
    target_receipt = target_payload.get("receipt")
    if not isinstance(target_receipt, dict):
        raise ValueError("ETo target artifact must contain a receipt")
    target_available = _require_utc_text(
        target_receipt.get("available_at"), "target available_at"
    )
    target_uri = _require_text(target_receipt.get("uri"), "target uri")
    target_source_version = _require_text(
        target_receipt.get("source_version"), "target source_version"
    )

    expected_source_names = {source.name for source in manifest.sources}
    if set(source_timing) != expected_source_names:
        raise ValueError("source_timing must name every manifest source exactly once")
    source_receipts: list[tuple[str, bytes]] = []
    source_archive_times: list[datetime] = []
    for source in manifest.sources:
        timing = source_timing[source.name]
        if not isinstance(timing, SourceTiming):
            raise ValueError("source_timing values must be SourceTiming records")
        if timing.source_issue_at != issue:
            raise ValueError("source_issue_at must match issue_time")
        if timing.archive_available_at != source.retrieved_at:
            raise ValueError("archive_available_at must match manifest source retrieved_at")
        source_archive_times.append(timing.archive_available_at)
        receipt = {
            "schema_version": 2,
            "kind": "idaho_outlook_hindcast_source_receipt",
            "case_id": case_id,
            "run_id": manifest.run_id,
            "name": source.name,
            "uri": source.uri,
            "source_version": "manifest-source-record-v1",
            "sha256": source.sha256,
            "temporal_role": timing.temporal_role,
            "source_issue_at": _format_utc(timing.source_issue_at),
            "archive_available_at": _format_utc(timing.archive_available_at),
        }
        source_receipts.append((source.name, _canonical_json_bytes(receipt)))

    training_folds = [fold for fold in range(5) if fold != held_out_fold]
    training_seasons = [
        season for season in ("DJF", "MAM", "JJA", "SON") if season != held_out_season
    ]
    holdout = {
        "schema_version": 1,
        "kind": "idaho_outlook_hindcast_holdout_receipt",
        "case_id": case_id,
        "run_id": manifest.run_id,
        "uri": f"urn:mlet:holdout:{case_id}",
        "source_version": "mlet-holdout-v1",
        "sha256": _sha256(
            _canonical_json_bytes(
                {"case_id": case_id, "fold": held_out_fold, "season": held_out_season}
            )
        ),
        "available_at": _format_utc(issue),
        "held_out_fold": held_out_fold,
        "training_folds": training_folds,
        "held_out_season": held_out_season,
        "training_seasons": training_seasons,
        "training_cutoff": _format_utc(issue),
        "calibration_cutoff": _format_utc(issue),
    }
    holdout_bytes = _canonical_json_bytes(holdout)

    root = Path(destination)
    if not root.is_dir() or root.is_symlink() or any(root.iterdir()):
        raise ValueError("evidence destination must be an existing empty real directory")
    forecast_root_out = root / "forecast"
    target_root_out = root / "target"
    receipt_root_out = root / "receipts"
    for directory in (forecast_root_out, target_root_out, receipt_root_out):
        directory.mkdir()
    _write_new(forecast_root_out / "manifest.json", manifest_bytes)
    _write_new(forecast_root_out / "outlook.json", outlook_bytes)
    _write_new(target_root_out / "target.json", target_bytes)

    source_descriptors = []
    for name, contents in source_receipts:
        relative = f"receipts/source-{name}.json"
        _write_new(root / relative, contents)
        source_descriptors.append({"path": relative, "sha256": _sha256(contents)})
    holdout_relative = "receipts/holdout.json"
    _write_new(root / holdout_relative, holdout_bytes)
    evidence = {
        "schema_version": 4,
        "evidence_classification": "real_archived",
        "validation_scope": _VALIDATION_SCOPE,
        "provenance": {
            "uri": root.resolve().as_uri(),
            "version": "mlet-eto-evidence-assembler-v1",
            "sha256": _sha256(manifest_bytes + target_bytes),
            "available_at": _format_utc(
                max([*source_archive_times, target_available])
            ),
        },
        "cases": [
            {
                "case_id": case_id,
                "issue_time": _format_utc(issue),
                "forecast": {
                    "run_id": manifest.run_id,
                    "manifest_path": "forecast/manifest.json",
                    "manifest_sha256": _sha256(manifest_bytes),
                    "artifact_path": "forecast/outlook.json",
                    "artifact_sha256": outlook_digest,
                },
                "target": {
                    "path": "target/target.json",
                    "uri": target_uri,
                    "source_version": target_source_version,
                    "sha256": _sha256(target_bytes),
                    "available_at": _format_utc(target_available),
                },
                "source_receipt_artifacts": source_descriptors,
                "holdout_receipt": {
                    "path": holdout_relative,
                    "sha256": _sha256(holdout_bytes),
                },
            }
        ],
    }
    evidence_path = root / "evidence.json"
    _write_new(evidence_path, _canonical_json_bytes(evidence))
    return evidence_path


def combine_eto_hindcast_evidence(
    evidence_paths: Sequence[Path], destination: Path
) -> Path:
    """Copy validated issue evidence into one self-contained ETo archive root.

    Each input may contain one or more cases. The output rewrites every file
    descriptor below its own directory. No case can retain a path into a
    staging directory after bundling.
    """
    if not evidence_paths:
        raise ValueError("ETo evidence bundle requires at least one input evidence path")
    root = Path(destination)
    if not root.is_dir() or root.is_symlink() or any(root.iterdir()):
        raise ValueError("ETo evidence bundle destination must be an existing empty real directory")
    from mlet.outlook.eto_hindcast import evaluate_eto_hindcast_evidence

    cases = []
    case_ids: set[str] = set()
    input_bytes = []
    availability: list[datetime] = []
    for evidence_path in evidence_paths:
        supplied_path = Path(evidence_path)
        if supplied_path.is_symlink():
            raise ValueError("ETo input evidence must not be a symlink")
        source_path = supplied_path.resolve(strict=True)
        source_root = source_path.parent
        if not source_path.is_file() or source_path.is_symlink():
            raise ValueError("ETo input evidence must be a regular file")
        evaluate_eto_hindcast_evidence(source_path)
        contents = source_path.read_bytes()
        payload = _read_json_object(contents, "ETo input evidence")
        raw_cases = payload.get("cases")
        provenance = payload.get("provenance")
        if not isinstance(raw_cases, list) or not isinstance(provenance, dict):
            raise ValueError("ETo input evidence has an invalid validated shape")
        input_bytes.append(contents)
        available_at = provenance.get("available_at")
        if not isinstance(available_at, str):
            raise ValueError("ETo input evidence provenance must have available_at")
        availability.append(_require_utc_text(available_at, "ETo input evidence provenance available_at"))
        for raw_case in raw_cases:
            if not isinstance(raw_case, dict):
                raise ValueError("ETo input evidence case must be an object")
            case_id = _require_text(raw_case.get("case_id"), "case_id")
            if case_id in case_ids or not case_id.replace("-", "").replace("_", "").isalnum():
                raise ValueError("ETo evidence case_id must be unique safe text")
            case_ids.add(case_id)
            case_root = root / "cases" / case_id
            case_root.mkdir(parents=True)
            copied = json.loads(json.dumps(raw_case, sort_keys=True))
            _rewrite_case_paths(copied, source_root, root, case_id)
            cases.append(copied)
    evidence = {
        "schema_version": 4,
        "evidence_classification": "real_archived",
        "validation_scope": _VALIDATION_SCOPE,
        "provenance": {
            "uri": root.resolve().as_uri(),
            "version": "mlet-eto-evidence-bundle-v1",
            "sha256": _sha256(b"".join(input_bytes)),
            "available_at": _format_utc(max(availability)),
        },
        "cases": cases,
    }
    output = root / "evidence.json"
    _write_new(output, _canonical_json_bytes(evidence))
    evaluate_eto_hindcast_evidence(output)
    return output


def _lead_day_for_date(issue_time: datetime, valid_date: date) -> int:
    for lead_day in range(1, 21):
        if outlook_valid_date(issue_time, lead_day) == valid_date:
            return lead_day
    raise ValueError("AgriMet observation is outside the ETo forecast horizon")


def _require_utc(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must be an explicit UTC datetime")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{label} must be an explicit UTC datetime")
    return value.astimezone(timezone.utc)


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


_VALIDATION_SCOPE = {
    "formal_hindcast_layers": ["eto_mm"],
    "nonforecast_analysis_layers": ["eta_analysis_mm"],
    "unvalidated_projection_layers": [
        "potential_et_c_mm",
        "eta_well_watered_mm",
        "eta_no_irrigation_mm",
    ],
}


def _regular_child(root: Path, name: str) -> Path:
    candidate = root / name
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError(f"forecast_directory must contain regular {name}")
    return candidate


def _rewrite_case_paths(
    case: dict[str, object], source_root: Path, destination_root: Path, case_id: str
) -> None:
    forecast = case.get("forecast")
    target = case.get("target")
    source_receipts = case.get("source_receipt_artifacts")
    holdout = case.get("holdout_receipt")
    if not isinstance(forecast, dict) or not isinstance(target, dict):
        raise ValueError("ETo evidence case has invalid forecast or target descriptor")
    if not isinstance(source_receipts, list) or not isinstance(holdout, dict):
        raise ValueError("ETo evidence case has invalid receipt descriptors")
    forecast["manifest_path"] = _copy_case_file(
        forecast.get("manifest_path"), source_root, destination_root, case_id
    )
    forecast["artifact_path"] = _copy_case_file(
        forecast.get("artifact_path"), source_root, destination_root, case_id
    )
    target["path"] = _copy_case_file(
        target.get("path"), source_root, destination_root, case_id
    )
    for receipt in source_receipts:
        if not isinstance(receipt, dict):
            raise ValueError("ETo evidence source receipt descriptor must be an object")
        receipt["path"] = _copy_case_file(
            receipt.get("path"), source_root, destination_root, case_id
        )
    holdout["path"] = _copy_case_file(
        holdout.get("path"), source_root, destination_root, case_id
    )


def _copy_case_file(
    supplied: object, source_root: Path, destination_root: Path, case_id: str
) -> str:
    if not isinstance(supplied, str) or not supplied or Path(supplied).is_absolute():
        raise ValueError("ETo evidence descriptor path must be a non-empty relative path")
    supplied_path = source_root / supplied
    if supplied_path.is_symlink():
        raise ValueError("ETo evidence descriptor must not be a symlink")
    source = supplied_path.resolve(strict=True)
    try:
        source.relative_to(source_root)
    except ValueError as error:
        raise ValueError("ETo evidence descriptor path escapes its input root") from error
    if not source.is_file() or source.is_symlink():
        raise ValueError("ETo evidence descriptor must name a regular file")
    relative = Path("cases") / case_id / Path(supplied).name
    destination = destination_root / relative
    if destination.exists() or destination.is_symlink():
        raise ValueError("ETo evidence bundle contains colliding artifact names")
    _write_new(destination, source.read_bytes())
    return relative.as_posix()


def _read_json_object(contents: bytes, label: str) -> dict[str, object]:
    try:
        payload = json.loads(contents.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} must be UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _write_new(destination: Path, contents: bytes) -> None:
    with destination.open("xb") as handle:
        handle.write(contents)


def _require_utc_text(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be explicit UTC text")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError(f"{label} must be explicit UTC text") from error
    return _require_utc(parsed, label)
