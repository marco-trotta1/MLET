"""Frozen, non-serving Idaho ET outlook residual-model experiment.

This module evaluates a learned correction beside the physical forecast.  It
never changes a build, map, Helios/Irrigant input, or local promotion status.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
from typing import cast

import numpy as np
import sklearn

from mlet.outlook.residual_model import (
    FEATURES,
    MODEL_RANDOM_SEED,
    ResidualCase,
    ResidualModel,
    fit_residual_model,
    predict_interval,
)
from mlet.outlook.hindcast import evaluate_hindcast_evidence


_AUTHORITY_BLOCKER = "requires_separately_trusted_release_authority"
_FIXTURE_BLOCKER = "software fixture is non-scientific and cannot support an ML claim"
_COVERAGE_TARGET = 0.80
_COVERAGE_TOLERANCE = 0.10
_WORST_SEASON_TOLERANCE_MM = 0.0


@dataclass(frozen=True)
class FrozenSplit:
    """Predeclared temporal and geographic split identifiers and cutoffs."""

    split_id: str
    train_cutoff: datetime
    calibration_cutoff: datetime
    held_out_spatial_blocks: tuple[str, ...]
    held_out_seasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.split_id, str) or not self.split_id:
            raise ValueError("split_id must be non-empty text")
        object.__setattr__(self, "train_cutoff", _parse_utc(self.train_cutoff, "train_cutoff"))
        object.__setattr__(self, "calibration_cutoff", _parse_utc(self.calibration_cutoff, "calibration_cutoff"))
        if self.train_cutoff > self.calibration_cutoff:
            raise ValueError("train_cutoff must not be after calibration_cutoff")
        if not self.held_out_spatial_blocks or not self.held_out_seasons:
            raise ValueError("frozen split needs held-out spatial blocks and seasons")
        if len(set(self.held_out_spatial_blocks)) != len(self.held_out_spatial_blocks):
            raise ValueError("held_out_spatial_blocks must be unique")
        if set(self.held_out_seasons) - {"DJF", "MAM", "JJA", "SON"}:
            raise ValueError("held_out_seasons must use calendar season identifiers")


@dataclass(frozen=True)
class ResidualMetric:
    """A held-out metric reported by lead and season."""

    group: str
    key: str
    sample_count: int
    physical_mae_mm: float | None
    residual_mae_mm: float | None
    coverage_p10_p90: float | None
    interval_width_mm: float | None


@dataclass(frozen=True)
class ResidualReport:
    """A non-promotable experimental candidate, not a product result."""

    evidence_classification: str
    split: FrozenSplit
    metrics: tuple[ResidualMetric, ...]
    blockers: tuple[str, ...]
    data_sha256: str
    model_parameters: dict[str, object]

    @property
    def promotion(self) -> bool:
        """Always false; only a separate authority can assess a candidate."""
        return False


@dataclass(frozen=True)
class ResidualEvaluationReceipt:
    """Hash-bound local candidate for an external, separately trusted review."""

    report: ResidualReport
    evidence_path: Path
    evaluation_digest: str


def evaluate_residual_evidence(path: Path) -> tuple[ResidualReport, ResidualEvaluationReceipt]:
    """Evaluate a frozen archive and construct a permanently false candidate."""
    report, digest = _evaluate(Path(path))
    report = _with_blocker(report, _AUTHORITY_BLOCKER)
    return report, ResidualEvaluationReceipt(
        report=report,
        evidence_path=Path(path).resolve(strict=True),
        evaluation_digest=digest,
    )


def write_residual_markdown(report: ResidualReport, destination: Path) -> Path:
    """Write a human-readable, non-promotable protocol result once."""
    lines = [
        "# Idaho Outlook Residual-Model Experiment",
        "",
        "Promotion: **false**",
        "Status: research candidate only; this does not modify the physics outlook or any Helios/Irrigant input.",
        "",
        "## Frozen experiment",
        "",
        f"- Evidence classification: `{report.evidence_classification}`",
        f"- Split ID: `{report.split.split_id}`",
        f"- Training cutoff: `{_format_utc(report.split.train_cutoff)}`",
        f"- Calibration cutoff: `{_format_utc(report.split.calibration_cutoff)}`",
        f"- Held-out spatial blocks: `{', '.join(report.split.held_out_spatial_blocks)}`",
        f"- Held-out seasons: `{', '.join(report.split.held_out_seasons)}`",
        f"- Evidence SHA-256: `{report.data_sha256}`",
        "",
        "## Release blockers",
        "",
    ]
    lines.extend(f"- {blocker}" for blocker in report.blockers)
    lines.extend([
        "",
        "## Held-out metrics",
        "",
        "| group | key | n | physical p50 MAE (mm/day) | residual p50 MAE (mm/day) | p10-p90 coverage | mean interval width (mm/day) |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    for metric in report.metrics:
        lines.append(
            "| {group} | {key} | {n} | {physical} | {residual} | {coverage} | {width} |".format(
                group=metric.group,
                key=metric.key,
                n=metric.sample_count,
                physical=_number(metric.physical_mae_mm),
                residual=_number(metric.residual_mae_mm),
                coverage=_number(metric.coverage_p10_p90),
                width=_number(metric.interval_width_mm),
            )
        )
    lines.extend([
        "",
        "The learned residual is evaluated beside, never substituted for, the physical ETo/ETc baseline. Fixtures are software checks only, not scientific evidence.",
        "",
    ])
    return _write_new(destination, ("\n".join(lines)).encode("utf-8"))


def write_residual_authority_request(receipt: object, destination: Path) -> Path:
    """Write a false-only request for a separately trusted release authority."""
    if not isinstance(receipt, ResidualEvaluationReceipt):
        raise ValueError("residual authority request requires an evaluation receipt")
    rebuilt, digest = _evaluate(receipt.evidence_path)
    if digest != receipt.evaluation_digest:
        raise ValueError("residual authority request refuses a receipt with a changed digest")
    rebuilt = _with_blocker(rebuilt, _AUTHORITY_BLOCKER)
    payload = {
        "schema_version": 1,
        "kind": "idaho_outlook_residual_release_authority_request",
        "evaluation_digest": digest,
        "candidate_report_sha256": _report_sha256(rebuilt),
        "promotion": False,
        "promotion_blockers": list(rebuilt.blockers),
        "external_release_eligible": rebuilt.blockers == (_AUTHORITY_BLOCKER,),
        "required_external_artifact": "separately_trusted_release_validation_receipt",
    }
    return _write_new(destination, (_canonical_json(payload) + "\n").encode("utf-8"))


def _evaluate(path: Path) -> tuple[ResidualReport, str]:
    source = path.resolve(strict=True)
    raw_bytes = source.read_bytes()
    raw = _load_json(raw_bytes, "residual evidence")
    if not isinstance(raw, dict):
        raise ValueError("residual evidence must be an object")
    # The existing zero-case fixture remains usable for a deterministic CLI
    # smoke test, but can never enter a scientific evaluation.
    if raw.get("schema_version") == 2 and raw.get("evidence_classification") == "software_fixture":
        report = _fixture_placeholder_report(raw_bytes)
        return report, hashlib.sha256(raw_bytes).hexdigest()
    _require_keys(raw, {"schema_version", "evidence_classification", "provenance", "hindcast_evidence", "split", "cases"}, "residual evidence")
    if raw["schema_version"] != 1:
        raise ValueError("residual evidence schema_version must be 1")
    classification = raw["evidence_classification"]
    if classification not in {"software_fixture", "real_archived"}:
        raise ValueError("residual evidence classification must be software_fixture or real_archived")
    _parse_provenance(raw["provenance"], required=classification == "real_archived")
    _verify_hindcast_evidence(
        raw["hindcast_evidence"], source.parent, required=classification == "real_archived"
    )
    split = _parse_split(raw["split"])
    cases_value = raw["cases"]
    if not isinstance(cases_value, list):
        raise ValueError("residual evidence cases must be a list")
    cases = tuple(_parse_case(value) for value in cases_value)
    _validate_split_roles(cases, split)
    blockers: list[str] = []
    if classification == "software_fixture":
        blockers.append(_FIXTURE_BLOCKER)
    metrics: tuple[ResidualMetric, ...] = ()
    train = tuple(case for case in cases if case.role == "train")
    calibration = tuple(case for case in cases if case.role == "calibration")
    test = tuple(case for case in cases if case.role == "test")
    if len(train) < 2:
        blockers.append("at least two leakage-safe training cases are required")
    if not calibration:
        blockers.append("separate calibration cases are required for interval coverage")
    if not test:
        blockers.append("held-out test cases are required")
    if not blockers or blockers == [_FIXTURE_BLOCKER]:
        model = fit_residual_model(train, cutoff=split.train_cutoff)
        calibration_width = _calibration_interval_inflation(model, calibration)
        metrics = _score(model, test, calibration_width)
        blockers.extend(_metric_blockers(metrics))
    report = ResidualReport(
        evidence_classification=cast(str, classification),
        split=split,
        metrics=metrics,
        blockers=tuple(_deduplicate(blockers)),
        data_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        model_parameters={
            "algorithm": "GradientBoostingRegressor(loss=quantile)",
            "quantiles": [0.1, 0.5, 0.9],
            "random_seed": MODEL_RANDOM_SEED,
            "features": list(FEATURES),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "calibration": "symmetric absolute-residual conformal inflation on calibration partition",
        },
    )
    digest = hashlib.sha256(_canonical_json(_report_payload(report)).encode("utf-8")).hexdigest()
    return report, digest


def _fixture_placeholder_report(raw_bytes: bytes) -> ResidualReport:
    split = FrozenSplit(
        split_id="fixture-placeholder-no-split",
        train_cutoff=datetime(1970, 1, 1, tzinfo=timezone.utc),
        calibration_cutoff=datetime(1970, 1, 1, tzinfo=timezone.utc),
        held_out_spatial_blocks=("fixture",),
        held_out_seasons=("DJF",),
    )
    return ResidualReport(
        evidence_classification="software_fixture",
        split=split,
        metrics=(),
        blockers=(_FIXTURE_BLOCKER, "fixture contains no archived residual cases"),
        data_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        model_parameters={"algorithm": "not_fit", "features": list(FEATURES), "random_seed": MODEL_RANDOM_SEED},
    )


def _parse_split(value: object) -> FrozenSplit:
    if not isinstance(value, dict):
        raise ValueError("residual split must be an object")
    _require_keys(value, {"split_id", "train_cutoff", "calibration_cutoff", "held_out_spatial_blocks", "held_out_seasons"}, "residual split")
    blocks = value["held_out_spatial_blocks"]
    seasons = value["held_out_seasons"]
    if not isinstance(blocks, list) or not all(isinstance(item, str) for item in blocks):
        raise ValueError("held_out_spatial_blocks must be a text list")
    if not isinstance(seasons, list) or not all(isinstance(item, str) for item in seasons):
        raise ValueError("held_out_seasons must be a text list")
    return FrozenSplit(
        split_id=cast(str, value["split_id"]),
        train_cutoff=_parse_timestamp(value["train_cutoff"], "train_cutoff"),
        calibration_cutoff=_parse_timestamp(value["calibration_cutoff"], "calibration_cutoff"),
        held_out_spatial_blocks=tuple(blocks),
        held_out_seasons=tuple(seasons),
    )


def _verify_hindcast_evidence(value: object, root: Path, *, required: bool) -> None:
    """Bind a real ML archive to Task 8's reconstructed input-availability gate."""
    if not required:
        if value is not None:
            raise ValueError("software_fixture residual evidence must set hindcast_evidence to null")
        return
    if not isinstance(value, dict):
        raise ValueError("real_archived residual evidence requires hindcast_evidence")
    _require_keys(value, {"path", "sha256"}, "hindcast_evidence")
    relative_path = value["path"]
    digest = value["sha256"]
    if not isinstance(relative_path, str) or not relative_path or Path(relative_path).is_absolute():
        raise ValueError("hindcast_evidence path must be a non-empty relative path")
    if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("hindcast_evidence sha256 must be lowercase hexadecimal")
    evidence_path = (root / relative_path).resolve(strict=True)
    try:
        evidence_path.relative_to(root.resolve(strict=True))
    except ValueError as error:
        raise ValueError("hindcast_evidence path must remain inside the residual archive") from error
    if evidence_path.is_symlink():
        raise ValueError("hindcast_evidence must not be a symlink")
    actual_digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    if actual_digest != digest:
        raise ValueError("hindcast_evidence sha256 does not match its archived bytes")
    hindcast_report, _receipt = evaluate_hindcast_evidence(evidence_path)
    if hindcast_report.fixture_non_scientific:
        raise ValueError("real_archived residual evidence cannot reference a hindcast fixture")
    if any(audit.excluded_after_issue for audit in hindcast_report.input_audit):
        raise ValueError("referenced hindcast has an input available after issue_time")


def _parse_case(value: object) -> ResidualCase:
    if not isinstance(value, dict):
        raise ValueError("residual case must be an object")
    _require_keys(value, {"case_id", "role", "layer", "target_kind", "issue_time", "valid_date", "spatial_block", "season", "feature_available_at", "features", "physical_p50", "target_mm"}, "residual case")
    availability = value["feature_available_at"]
    features = value["features"]
    if not isinstance(availability, dict) or set(availability) != set(FEATURES):
        raise ValueError("feature_available_at must contain exactly FEATURES")
    if not isinstance(features, dict) or set(features) != set(FEATURES):
        raise ValueError("features must contain exactly FEATURES")
    ordered_availability = tuple((name, _parse_timestamp(availability[name], f"feature {name} available_at")) for name in FEATURES)
    try:
        ordered_features = tuple(float(features[name]) for name in FEATURES)
        physical_p50 = float(value["physical_p50"])
        target_mm = float(value["target_mm"])
    except (TypeError, ValueError) as error:
        raise ValueError("residual feature and target values must be numeric") from error
    return ResidualCase(
        case_id=cast(str, value["case_id"]),
        role=cast(str, value["role"]),
        layer=cast(str, value["layer"]),
        target_kind=cast(str, value["target_kind"]),
        issue_time=_parse_timestamp(value["issue_time"], "issue_time"),
        valid_date=cast(str, value["valid_date"]),
        spatial_block=cast(str, value["spatial_block"]),
        season=cast(str, value["season"]),
        feature_available_at=ordered_availability,
        features=ordered_features,
        physical_p50=physical_p50,
        target_mm=target_mm,
    )


def _validate_split_roles(cases: Sequence[ResidualCase], split: FrozenSplit) -> None:
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("residual case_id values must be unique")
    for case in cases:
        held_out = case.spatial_block in split.held_out_spatial_blocks or case.season in split.held_out_seasons
        if case.role == "train":
            if case.issue_time > split.train_cutoff:
                raise ValueError("training case is after frozen train_cutoff")
            if held_out:
                raise ValueError("held-out spatial block or season appears in training")
        elif case.role == "calibration":
            if case.issue_time > split.calibration_cutoff:
                raise ValueError("calibration case is after frozen calibration_cutoff")
            if held_out:
                raise ValueError("held-out spatial block or season appears in calibration")
        elif not held_out:
            raise ValueError("test case must occupy a declared held-out spatial block or season")


def _calibration_interval_inflation(model: ResidualModel, calibration: Sequence[ResidualCase]) -> float:
    if not calibration:
        raise ValueError("residual calibration requires a fitted model and cases")
    residuals: list[float] = []
    for case in calibration:
        predicted = predict_interval(model, case)
        residuals.append(max(predicted.p10 - case.target_mm, case.target_mm - predicted.p90, 0.0))
    return float(np.quantile(np.asarray(residuals, dtype=float), _COVERAGE_TARGET))


def _score(model: ResidualModel, test: Sequence[ResidualCase], inflation: float) -> tuple[ResidualMetric, ...]:
    grouped: dict[tuple[str, str], list[tuple[ResidualCase, float, float, float]]] = defaultdict(list)
    for case in test:
        predicted = predict_interval(model, case)
        p10 = max(0.0, predicted.p10 - inflation)
        p90 = predicted.p90 + inflation
        grouped[("lead_day", str(int(case.features[0])))].append((case, p10, predicted.p50, p90))
        grouped[("season", case.season)].append((case, p10, predicted.p50, p90))
    return tuple(_metric(group, key, values) for (group, key), values in sorted(grouped.items()))


def _metric(group: str, key: str, values: Sequence[tuple[ResidualCase, float, float, float]]) -> ResidualMetric:
    physical = [abs(case.physical_p50 - case.target_mm) for case, _p10, _p50, _p90 in values]
    residual = [abs(p50 - case.target_mm) for case, _p10, p50, _p90 in values]
    coverage = [p10 <= case.target_mm <= p90 for case, p10, _p50, p90 in values]
    widths = [p90 - p10 for _case, p10, _p50, p90 in values]
    return ResidualMetric(
        group=group,
        key=key,
        sample_count=len(values),
        physical_mae_mm=float(np.mean(physical)),
        residual_mae_mm=float(np.mean(residual)),
        coverage_p10_p90=float(np.mean(coverage)),
        interval_width_mm=float(np.mean(widths)),
    )


def _metric_blockers(metrics: Sequence[ResidualMetric]) -> list[str]:
    blockers: list[str] = []
    lead_metrics = [item for item in metrics if item.group == "lead_day"]
    season_metrics = [item for item in metrics if item.group == "season"]
    for item in lead_metrics:
        if item.residual_mae_mm is None or item.physical_mae_mm is None or item.residual_mae_mm >= item.physical_mae_mm:
            blockers.append(f"residual MAE does not improve physical baseline at lead {item.key}")
        if item.coverage_p10_p90 is None or abs(item.coverage_p10_p90 - _COVERAGE_TARGET) > _COVERAGE_TOLERANCE:
            blockers.append(f"p10-p90 coverage outside preregistered tolerance at lead {item.key}")
    observed_leads = {item.key for item in lead_metrics}
    missing_leads = [str(lead) for lead in range(1, 21) if str(lead) not in observed_leads]
    if missing_leads:
        blockers.append(f"missing held-out residual metrics for leads: {', '.join(missing_leads)}")
    for item in season_metrics:
        if item.residual_mae_mm is None or item.physical_mae_mm is None or item.residual_mae_mm - item.physical_mae_mm > _WORST_SEASON_TOLERANCE_MM:
            blockers.append(f"worst-season error degrades in {item.key}")
    if not lead_metrics:
        blockers.append("no held-out lead-day metrics were produced")
    return blockers


def _with_blocker(report: ResidualReport, blocker: str) -> ResidualReport:
    return ResidualReport(
        evidence_classification=report.evidence_classification,
        split=report.split,
        metrics=report.metrics,
        blockers=tuple(_deduplicate([*report.blockers, blocker])),
        data_sha256=report.data_sha256,
        model_parameters=report.model_parameters,
    )


def _report_payload(report: ResidualReport) -> dict[str, object]:
    return {
        "classification": report.evidence_classification,
        "split_id": report.split.split_id,
        "train_cutoff": _format_utc(report.split.train_cutoff),
        "calibration_cutoff": _format_utc(report.split.calibration_cutoff),
        "held_out_spatial_blocks": list(report.split.held_out_spatial_blocks),
        "held_out_seasons": list(report.split.held_out_seasons),
        "metrics": [metric.__dict__ for metric in report.metrics],
        "blockers": list(report.blockers),
        "data_sha256": report.data_sha256,
        "model_parameters": report.model_parameters,
        "promotion": False,
    }


def _report_sha256(report: ResidualReport) -> str:
    return hashlib.sha256(_canonical_json(_report_payload(report)).encode("utf-8")).hexdigest()


def _parse_provenance(value: object, *, required: bool) -> None:
    if not isinstance(value, dict):
        raise ValueError("residual provenance must be an object")
    _require_keys(value, {"uri", "version", "sha256", "available_at"}, "residual provenance")
    uri = value["uri"]
    version = value["version"]
    digest = value["sha256"]
    if not isinstance(uri, str) or not uri or not isinstance(version, str) or not version:
        raise ValueError("residual provenance uri and version must be non-empty text")
    if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("residual provenance sha256 must be lowercase hexadecimal")
    _parse_timestamp(value["available_at"], "provenance available_at")
    if required and ("example." in uri or version.lower() in {"fixture", "unknown"}):
        raise ValueError("real_archived residual evidence requires non-fixture provenance")


def _load_json(encoded: bytes, label: str) -> object:
    try:
        return json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} must be UTF-8 JSON") from error


def _require_keys(value: dict[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields must match the schema exactly")


def _parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be strict UTC ISO-8601 text ending in Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be strict UTC ISO-8601 text ending in Z") from error
    return _parse_utc(parsed, label)


def _parse_utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{label} must be timezone-aware UTC")
    return value


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _deduplicate(items: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _number(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def _write_new(destination: Path, encoded: bytes) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as handle:
        handle.write(encoded)
    return destination
