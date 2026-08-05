"""Evaluate immutable ETo-only outlook evidence.

This module implements the manuscript evaluation scope. It scores only
weather-driven ASCE short-reference ETo. It does not score ETc or ETa layers.
It does not issue a promotion or release decision.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
from urllib.parse import urlparse

from mlet.outlook.dates import idaho_local_date, idaho_local_day_end_utc, outlook_valid_date
from mlet.outlook.eto_contract import validate_eto_candidate_payload
from mlet.outlook.eto_archive import SourceTiming
from mlet.outlook.manifest import RunManifest
from mlet.outlook.spatial import spatial_block_for_grid_id, spatial_fold_for_grid_id


_EVIDENCE_SCHEMA_VERSION = 4
_TARGET_SCHEMA_VERSION = 2
_TARGET_KIND = "independent_asce_short_reference_eto"
_TARGET_ARTIFACT_KIND = "idaho_outlook_eto_hindcast_target"
_SEASONS = {
    12: "DJF",
    1: "DJF",
    2: "DJF",
    3: "MAM",
    4: "MAM",
    5: "MAM",
    6: "JJA",
    7: "JJA",
    8: "JJA",
    9: "SON",
    10: "SON",
    11: "SON",
}
_VALIDATION_SCOPE = {
    "formal_hindcast_layers": ["eto_mm"],
    "nonforecast_analysis_layers": ["eta_analysis_mm"],
    "unvalidated_projection_layers": [
        "potential_et_c_mm",
        "eta_well_watered_mm",
        "eta_no_irrigation_mm",
    ],
}
_BOOTSTRAP_SEED = 20260731
_BOOTSTRAP_REPLICATES = 1_000


@dataclass(frozen=True)
class EtoHindcastMetric:
    """One aggregate ETo score and its paired climatology comparison."""

    group: str
    key: str
    sample_count: int
    mae_mm: float
    rmse_mm: float
    bias_mm: float
    p10_p90_coverage: float
    mean_interval_width_mm: float
    mean_pinball_loss_mm: float
    baseline_mae_mm: float
    mae_improvement_mm: float
    mae_improvement_ci95_low_mm: float | None
    mae_improvement_ci95_high_mm: float | None
    bootstrap_cluster_count: int


@dataclass(frozen=True)
class EtoExclusion:
    """One target date excluded before ETo scoring."""

    case_id: str
    target_id: str
    valid_date: date
    reason: str


@dataclass(frozen=True)
class EtoHindcastReport:
    """An ETo-only diagnostic with explicit completion failures."""

    metrics: tuple[EtoHindcastMetric, ...]
    case_count: int
    target_count: int
    station_count: int
    evidence_sha256: str
    target_sources: tuple[tuple[str, str], ...]
    forecast_revisions: tuple[str, ...]
    exclusions: tuple[EtoExclusion, ...]
    validation_scope: dict[str, list[str]]
    completion_blockers: tuple[str, ...]
    bootstrap_seed: int
    bootstrap_replicates: int
    bootstrap_cluster_definition: str

    @property
    def archive_sha256(self) -> str:
        """Return the digest of the immutable evidence descriptor."""
        return self.evidence_sha256

    @property
    def evaluation_sha256(self) -> str:
        """Return the digest of the canonical evaluation record material."""
        return hashlib.sha256(
            _canonical_json_bytes(_evaluation_payload(self))
        ).hexdigest()

    @property
    def support(self) -> dict[str, object]:
        """Return explicit support counts for every preregistered cell."""
        metric_index = {(metric.group, metric.key): metric for metric in self.metrics}
        cells = []
        for lead_day in range(1, 21):
            for season in ("DJF", "MAM", "JJA", "SON"):
                for fold in range(5):
                    metric = metric_index.get(
                        ("lead_season_spatial_fold", f"{lead_day}:{season}:{fold}")
                    )
                    count = metric.sample_count if metric is not None else 0
                    cells.append(
                        {
                            "lead_day": lead_day,
                            "season": season,
                            "spatial_fold": fold,
                            "sample_count": count,
                            "minimum_required": 30,
                            "supported": count >= 30,
                        }
                    )
        return {
            "minimum_paired_targets": 30,
            "cell_count": len(cells),
            "cells": cells,
        }

    @property
    def claim_safe_prose(self) -> dict[str, str]:
        """Return deterministic prose that preserves the frozen claim boundary."""
        completion = (
            "The preregistered ETo evaluation is complete."
            if not self.completion_blockers
            else "The preregistered ETo evaluation is incomplete."
        )
        return {
            "scope": "MLET formally evaluates eto_mm only.",
            "completion": completion,
            "skill": (
                "Use skillful only when the paired 95% confidence interval for "
                "improvement over climatology excludes zero."
            ),
            "promotion": "This result does not promote an operational forecast.",
        }


@dataclass(frozen=True)
class _EtoRow:
    issue_time: datetime
    lead_day: int
    valid_date: date
    target_id: str
    spatial_block: str
    fold: int
    p10: float
    p50: float
    p90: float
    target_mm: float
    baseline_p50_mm: float


def evaluate_eto_hindcast_evidence(path: Path) -> EtoHindcastReport:
    """Rebuild and score a strict schema-v4 ETo evidence bundle.

    The input bundle must contain regular files below its own directory. Each
    file is hash-bound before it is parsed. The result does not grant a
    validation or promotion status to any product artifact.
    """
    supplied_path = Path(path)
    if supplied_path.is_symlink():
        raise ValueError("ETo hindcast evidence path must not be a symlink")
    evidence_path = supplied_path.resolve(strict=True)
    root = evidence_path.parent
    evidence_bytes = evidence_path.read_bytes()
    evidence = _read_json(evidence_bytes, "ETo hindcast evidence")
    _require_exact_keys(
        evidence,
        {"schema_version", "evidence_classification", "validation_scope", "provenance", "cases"},
        "ETo hindcast evidence",
    )
    if evidence["schema_version"] != _EVIDENCE_SCHEMA_VERSION:
        raise ValueError("ETo hindcast evidence must use schema_version 4")
    _require_validation_scope(evidence["validation_scope"])
    classification = evidence["evidence_classification"]
    if classification not in {"real_archived", "software_fixture"}:
        raise ValueError("evidence_classification must be real_archived or software_fixture")
    _validate_provenance(evidence["provenance"])
    raw_cases = evidence["cases"]
    if not isinstance(raw_cases, list):
        raise ValueError("ETo hindcast cases must be a list")

    rows: list[_EtoRow] = []
    held_folds: set[int] = set()
    held_seasons: set[str] = set()
    target_sources: set[tuple[str, str]] = set()
    forecast_revisions: set[str] = set()
    exclusions: list[EtoExclusion] = []
    blockers: list[str] = []
    case_availability: list[datetime] = []
    for index, raw_case in enumerate(raw_cases):
        (
            case_rows,
            held_fold,
            held_season,
            case_blockers,
            forecast_revision,
            case_exclusions,
            case_available_at,
        ) = _parse_case(
            raw_case, root, index
        )
        rows.extend(case_rows)
        held_folds.add(held_fold)
        held_seasons.add(held_season)
        blockers.extend(case_blockers)
        forecast_revisions.add(forecast_revision)
        exclusions.extend(case_exclusions)
        case_availability.append(case_available_at)
        assert isinstance(raw_case, dict)
        target = raw_case["target"]
        assert isinstance(target, dict)
        target_sources.add((target["uri"], target["source_version"]))  # type: ignore[arg-type]

    provenance = evidence["provenance"]
    assert isinstance(provenance, dict)
    if case_availability:
        expected_available_at = max(case_availability)
        supplied_available_at = _parse_utc(
            provenance["available_at"], "evidence provenance available_at"
        )
        if supplied_available_at != expected_available_at:
            raise ValueError(
                "evidence provenance available_at must equal the latest real source or target availability"
            )

    if not rows:
        blockers.append("no historical ETo targets were supplied")
    if classification != "real_archived":
        blockers.append("software fixture is non-scientific")
    missing_folds = sorted(set(range(5)) - held_folds)
    if missing_folds:
        blockers.append(f"missing preregistered held-out spatial folds: {missing_folds}")
    missing_seasons = sorted(set(_SEASONS.values()) - held_seasons)
    if missing_seasons:
        blockers.append(f"missing preregistered held-out seasons: {missing_seasons}")

    metrics = _summarize(rows)
    metric_index = {(metric.group, metric.key): metric for metric in metrics}
    for lead_day in range(1, 21):
        metric = metric_index.get(("lead_day", str(lead_day)))
        if metric is None or metric.sample_count == 0:
            blockers.append(f"missing ETo support for lead {lead_day}")
    for lead_day in range(1, 21):
        for season in ("DJF", "MAM", "JJA", "SON"):
            for fold in range(5):
                key = f"{lead_day}:{season}:{fold}"
                metric = metric_index.get(("lead_season_spatial_fold", key))
                count = metric.sample_count if metric is not None else 0
                if count < 30:
                    blockers.append(
                        "insufficient ETo support for "
                        f"lead_season_spatial_fold {key}: need 30, found {count}"
                    )
    for metric in metrics:
        if metric.group in {"lead_day", "season", "spatial_fold"} and metric.sample_count < 30:
            blockers.append(
                f"insufficient ETo support for {metric.group} {metric.key}: "
                f"need 30, found {metric.sample_count}"
            )
    return EtoHindcastReport(
        metrics=metrics,
        case_count=len(raw_cases),
        target_count=len(rows),
        station_count=len({row.target_id for row in rows}),
        evidence_sha256=hashlib.sha256(evidence_bytes).hexdigest(),
        target_sources=tuple(sorted(target_sources)),
        forecast_revisions=tuple(sorted(forecast_revisions)),
        exclusions=tuple(sorted(exclusions, key=_exclusion_sort_key)),
        validation_scope=_validation_scope_copy(),
        completion_blockers=tuple(_deduplicate(blockers)),
        bootstrap_seed=_BOOTSTRAP_SEED,
        bootstrap_replicates=_BOOTSTRAP_REPLICATES,
        bootstrap_cluster_definition="issue_date,target_id",
    )


def write_eto_hindcast_markdown(report: EtoHindcastReport, destination: Path) -> Path:
    """Write a local ETo-only diagnostic without a validation claim."""
    if not isinstance(report, EtoHindcastReport):
        raise ValueError("ETo hindcast markdown requires an EtoHindcastReport")
    lines = [
        "# Idaho ETo Hindcast Diagnostic",
        "",
        "This diagnostic evaluates only weather-driven reference ETo.",
        "It does not validate ETc or ETa conditional projections.",
        "",
        f"Historical issue cases: {report.case_count}",
        f"Archive SHA-256: {report.archive_sha256}",
        f"Evaluation SHA-256: {report.evaluation_sha256}",
        f"Forecast revisions: {', '.join(report.forecast_revisions)}",
        "",
        "## Completion checks",
        "",
    ]
    if report.completion_blockers:
        lines.extend(f"- {blocker}" for blocker in report.completion_blockers)
    else:
        lines.append("- The frozen ETo support checks are complete.")
    lines.extend(
        [
            "",
            "## ETo metrics",
            "",
            "| group | key | n | MAE (mm/day) | RMSE (mm/day) | bias (mm/day) | p10-p90 coverage | Mean interval width (mm/day) | Mean pinball loss (mm/day) | baseline MAE (mm/day) | MAE improvement (mm/day) | paired 95% CI (mm/day) |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for metric in report.metrics:
        lines.append(
            "| "
            f"{metric.group} | {metric.key} | {metric.sample_count} | "
            f"{metric.mae_mm:.3f} | {metric.rmse_mm:.3f} | {metric.bias_mm:.3f} | "
            f"{metric.p10_p90_coverage:.3f} | {metric.mean_interval_width_mm:.3f} | "
            f"{metric.mean_pinball_loss_mm:.3f} | {metric.baseline_mae_mm:.3f} | "
            f"{metric.mae_improvement_mm:.3f} | "
            f"{_format_ci(metric.mae_improvement_ci95_low_mm, metric.mae_improvement_ci95_high_mm)} |"
        )
    lines.extend(
        [
            "",
            "The fixed baseline uses every strictly prior year for the same station and day of year.",
            "Spatial fold exclusion applies to learned or tuned components, not this fixed benchmark.",
            f"Excluded target dates: {len(report.exclusions)}.",
            f"Paired bootstrap clusters: {report.bootstrap_cluster_definition}; "
            f"seed {report.bootstrap_seed}; replicates {report.bootstrap_replicates}.",
            "A completed evaluation does not by itself show useful skill.",
            "State a skill claim only where a preregistered confidence interval supports it.",
            "",
        ]
    )
    _write_new_bytes(Path(destination), "\n".join(lines).encode("utf-8"))
    return Path(destination)


def write_eto_hindcast_json(report: EtoHindcastReport, destination: Path) -> Path:
    """Write a machine-readable ETo-only result record."""
    if not isinstance(report, EtoHindcastReport):
        raise ValueError("ETo hindcast JSON requires an EtoHindcastReport")
    payload = {
        "schema_version": 1,
        "kind": "idaho_eto_hindcast_result",
        "case_count": report.case_count,
        "target_count": report.target_count,
        "station_count": report.station_count,
        "evidence_sha256": report.evidence_sha256,
        "archive_sha256": report.archive_sha256,
        "evaluation_sha256": report.evaluation_sha256,
        "target_sources": [
            {"uri": uri, "source_version": source_version}
            for uri, source_version in report.target_sources
        ],
        "source_versions": [
            {"uri": uri, "source_version": source_version}
            for uri, source_version in report.target_sources
        ],
        "forecast_revisions": list(report.forecast_revisions),
        "exclusions": [
            {
                "case_id": exclusion.case_id,
                "target_id": exclusion.target_id,
                "valid_date": exclusion.valid_date.isoformat(),
                "reason": exclusion.reason,
            }
            for exclusion in report.exclusions
        ],
        "support": report.support,
        "claim_safe_prose": report.claim_safe_prose,
        "validation_scope": report.validation_scope,
        "completion_blockers": list(report.completion_blockers),
        "bootstrap": {
            "seed": report.bootstrap_seed,
            "replicates": report.bootstrap_replicates,
            "cluster_definition": report.bootstrap_cluster_definition,
        },
        "metrics": [
            {
                "group": metric.group,
                "key": metric.key,
                "sample_count": metric.sample_count,
                "mae_mm": metric.mae_mm,
                "rmse_mm": metric.rmse_mm,
                "bias_mm": metric.bias_mm,
                "p10_p90_coverage": metric.p10_p90_coverage,
                "mean_interval_width_mm": metric.mean_interval_width_mm,
                "mean_pinball_loss_mm": metric.mean_pinball_loss_mm,
                "baseline_mae_mm": metric.baseline_mae_mm,
                "mae_improvement_mm": metric.mae_improvement_mm,
                "mae_improvement_ci95_low_mm": metric.mae_improvement_ci95_low_mm,
                "mae_improvement_ci95_high_mm": metric.mae_improvement_ci95_high_mm,
                "bootstrap_cluster_count": metric.bootstrap_cluster_count,
            }
            for metric in report.metrics
        ],
    }
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    _write_new_bytes(Path(destination), encoded)
    return Path(destination)


def _parse_case(
    value: object, root: Path, case_index: int
) -> tuple[
    list[_EtoRow],
    int,
    str,
    list[str],
    str,
    tuple[EtoExclusion, ...],
    datetime,
]:
    _require_exact_keys(
        value,
        {"case_id", "issue_time", "forecast", "target", "source_receipt_artifacts", "holdout_receipt"},
        "ETo evidence case",
    )
    assert isinstance(value, dict)
    case_id = _require_text(value["case_id"], "case_id")
    issue_time = _parse_utc(value["issue_time"], "case issue_time")
    forecast = value["forecast"]
    target = value["target"]
    _require_exact_keys(
        forecast,
        {"run_id", "manifest_path", "manifest_sha256", "artifact_path", "artifact_sha256"},
        "forecast receipt",
    )
    _require_exact_keys(
        target,
        {"path", "uri", "source_version", "sha256", "available_at"},
        "target receipt",
    )
    assert isinstance(forecast, dict)
    assert isinstance(target, dict)
    manifest_bytes = _read_evidence_file(root, forecast["manifest_path"], "forecast manifest")
    _require_digest(manifest_bytes, forecast["manifest_sha256"], "forecast manifest")
    manifest = RunManifest.from_json(manifest_bytes.decode("utf-8"))
    if manifest.run_id != forecast["run_id"] or manifest.issued_at != issue_time:
        raise ValueError("forecast receipt does not match its verified manifest")
    forecast_bytes = _read_evidence_file(root, forecast["artifact_path"], "forecast artifact")
    _require_digest(forecast_bytes, forecast["artifact_sha256"], "forecast artifact")
    if dict(manifest.artifact_sha256).get("outlook.json") != forecast["artifact_sha256"]:
        raise ValueError("forecast artifact hash does not match verified manifest outlook.json")
    forecast_payload = _read_json(forecast_bytes, "forecast artifact")
    _validate_forecast(forecast_payload, manifest.run_id, issue_time)
    source_archive_available_at = _validate_source_receipts(
        value["source_receipt_artifacts"], root, manifest, issue_time, case_id
    )

    target_bytes = _read_evidence_file(root, target["path"], "target artifact")
    _require_digest(target_bytes, target["sha256"], "target artifact")
    target_available = _parse_utc(target["available_at"], "target available_at")
    _validate_uri(target["uri"], "target uri")
    _require_text(target["source_version"], "target source_version")
    target_payload = _read_json(target_bytes, "target artifact")
    target_rows, raw_exclusions = _parse_targets(
        target_payload,
        case_id=case_id,
        run_id=manifest.run_id,
        target_uri=target["uri"],
        target_source_version=target["source_version"],
        target_available=target_available,
        issue_time=issue_time,
    )
    forecast_quantiles = _forecast_quantiles(forecast_payload, issue_time)
    rows = _bind_rows(target_rows, forecast_quantiles, issue_time=issue_time)
    exclusions = tuple(
        EtoExclusion(
            case_id=case_id,
            target_id=exclusion["target_id"],
            valid_date=exclusion["valid_date"],
            reason=exclusion["reason"],
        )
        for exclusion in raw_exclusions
    )
    holdout = _read_holdout(value["holdout_receipt"], root, case_id, manifest.run_id)
    held_fold, held_season, blockers = _validate_holdout(
        holdout, rows, issue_time, case_index
    )
    return (
        rows,
        held_fold,
        held_season,
        blockers,
        manifest.git_revision,
        exclusions,
        max(source_archive_available_at, target_available),
    )


def _validate_forecast(payload: object, run_id: str, issue_time: datetime) -> None:
    validate_eto_candidate_payload(
        payload,
        expected_run_id=run_id,
        expected_issued_at=issue_time,
    )


def _validate_source_receipts(
    descriptors: object,
    root: Path,
    manifest: RunManifest,
    issue_time: datetime,
    case_id: str,
) -> datetime:
    if not isinstance(descriptors, list):
        raise ValueError("source_receipt_artifacts must be a list")
    manifest_sources = {source.name: source for source in manifest.sources}
    receipts: dict[str, dict[str, object]] = {}
    for descriptor in descriptors:
        _require_exact_keys(descriptor, {"path", "sha256"}, "source receipt descriptor")
        assert isinstance(descriptor, dict)
        content = _read_evidence_file(root, descriptor["path"], "source receipt")
        _require_digest(content, descriptor["sha256"], "source receipt")
        receipt = _read_json(content, "source receipt")
        _require_exact_keys(
            receipt,
            {
                "schema_version",
                "kind",
                "case_id",
                "run_id",
                "name",
                "uri",
                "source_version",
                "sha256",
                "temporal_role",
                "source_issue_at",
                "archive_available_at",
            },
            "source receipt",
        )
        assert isinstance(receipt, dict)
        if receipt.get("schema_version") != 2 or receipt.get("kind") != "idaho_outlook_hindcast_source_receipt":
            raise ValueError("source receipt has an unsupported schema")
        if receipt.get("case_id") != case_id or receipt.get("run_id") != manifest.run_id:
            raise ValueError("source receipt does not bind its case and run")
        name = _require_text(receipt["name"], "source receipt name")
        if name in receipts:
            raise ValueError("source receipt names must be unique")
        receipts[name] = receipt
    if set(receipts) != set(manifest_sources):
        raise ValueError("source receipts must bind every manifest source exactly once")
    archive_times: list[datetime] = []
    for name, receipt in receipts.items():
        source = manifest_sources[name]
        if receipt["uri"] != source.uri or receipt["sha256"] != source.sha256:
            raise ValueError("source receipt identity does not match verified manifest")
        timing = SourceTiming(
            temporal_role=_require_text(
                receipt["temporal_role"], "source receipt temporal_role"
            ),
            source_issue_at=_parse_utc(
                receipt["source_issue_at"], "source receipt source_issue_at"
            ),
            archive_available_at=_parse_utc(
                receipt["archive_available_at"],
                "source receipt archive_available_at",
            ),
        )
        if timing.source_issue_at != issue_time:
            raise ValueError("source receipt source_issue_at must match case issue_time")
        if timing.archive_available_at != source.retrieved_at:
            raise ValueError(
                "source receipt archive_available_at must match manifest source retrieved_at"
            )
        archive_times.append(timing.archive_available_at)
    return max(archive_times)


def _parse_targets(
    payload: object,
    *,
    case_id: str,
    run_id: str,
    target_uri: object,
    target_source_version: object,
    target_available: datetime,
    issue_time: datetime,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    assert isinstance(payload, dict)
    expected_fields = {"schema_version", "kind", "receipt", "values"}
    fields_with_exclusions = expected_fields | {"exclusions"}
    if set(payload) not in (expected_fields, fields_with_exclusions):
        raise ValueError("target artifact fields must match the ETo-only schema")
    if payload["schema_version"] != _TARGET_SCHEMA_VERSION or payload["kind"] != _TARGET_ARTIFACT_KIND:
        raise ValueError("target artifact has an unsupported ETo-only schema")
    receipt = payload["receipt"]
    _require_exact_keys(
        receipt,
        {"case_id", "run_id", "uri", "source_version", "available_at"},
        "target artifact receipt",
    )
    assert isinstance(receipt, dict)
    if receipt["case_id"] != case_id or receipt["run_id"] != run_id:
        raise ValueError("target artifact receipt does not bind its case and run")
    if receipt["uri"] != target_uri:
        raise ValueError("target artifact receipt URI does not match target descriptor")
    if receipt["source_version"] != target_source_version:
        raise ValueError(
            "target artifact receipt source_version does not match target descriptor"
        )
    if _parse_utc(receipt["available_at"], "target artifact receipt available_at") != target_available:
        raise ValueError("target artifact receipt available_at does not match target descriptor")
    values = payload["values"]
    if not isinstance(values, list) or not values:
        raise ValueError("target artifact values must be a non-empty list")
    expected = {
        "target_id", "grid_id", "latitude", "longitude", "lead_day", "valid_date",
        "target_mm", "baseline_p50_mm", "target_kind",
    }
    seen: set[tuple[str, int]] = set()
    parsed: list[dict[str, object]] = []
    for value in values:
        _require_exact_keys(value, expected, "ETo target value")
        assert isinstance(value, dict)
        target_id = _require_text(value["target_id"], "target_id")
        grid_id = _require_text(value["grid_id"], "grid_id")
        spatial_block_for_grid_id(grid_id)
        lead_day = _require_lead_day(value["lead_day"])
        valid_date = _parse_date(value["valid_date"], "target valid_date")
        if valid_date != outlook_valid_date(issue_time, lead_day):
            raise ValueError("target valid_date does not match issue_time plus lead_day")
        if value["target_kind"] != _TARGET_KIND:
            raise ValueError("target_kind must be independent_asce_short_reference_eto")
        if target_available <= idaho_local_day_end_utc(valid_date):
            raise ValueError("target artifact must become available after its valid date")
        key = (target_id, lead_day)
        if key in seen:
            raise ValueError("target artifact contains a duplicate target and lead")
        seen.add(key)
        parsed.append(
            {
                "target_id": target_id,
                "grid_id": grid_id,
                "latitude": _finite(value["latitude"], "target latitude", -90.0, 90.0),
                "longitude": _finite(value["longitude"], "target longitude", -180.0, 180.0),
                "lead_day": lead_day,
                "valid_date": valid_date,
                "target_mm": _finite(value["target_mm"], "target_mm", 0.0, math.inf),
                "baseline_p50_mm": _finite(value["baseline_p50_mm"], "baseline_p50_mm", 0.0, math.inf),
            }
        )
    exclusions = _parse_exclusions(
        payload.get("exclusions", []),
        issue_time=issue_time,
        seen_values=seen,
    )
    return parsed, exclusions


def _parse_exclusions(
    value: object,
    *,
    issue_time: datetime,
    seen_values: set[tuple[str, int]],
) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ValueError("target artifact exclusions must be a list")
    expected_dates = {
        outlook_valid_date(issue_time, lead_day) for lead_day in range(1, 21)
    }
    seen: set[tuple[str, date]] = set()
    parsed: list[dict[str, object]] = []
    for exclusion in value:
        _require_exact_keys(
            exclusion,
            {"target_id", "valid_date", "reason"},
            "ETo target exclusion",
        )
        assert isinstance(exclusion, dict)
        target_id = _require_text(exclusion["target_id"], "exclusion target_id")
        valid_date = _parse_date(exclusion["valid_date"], "exclusion valid_date")
        if valid_date not in expected_dates:
            raise ValueError("exclusion valid_date must be within the 20-day horizon")
        reason = _require_text(exclusion["reason"], "exclusion reason")
        key = (target_id, valid_date)
        if key in seen:
            raise ValueError("target artifact exclusions must not duplicate target and date")
        seen.add(key)
        lead_day = next(
            lead
            for lead in range(1, 21)
            if outlook_valid_date(issue_time, lead) == valid_date
        )
        if (target_id, lead_day) in seen_values:
            raise ValueError("target artifact exclusion overlaps a target value")
        parsed.append(
            {
                "target_id": target_id,
                "valid_date": valid_date,
                "reason": reason,
            }
        )
    return parsed


def _forecast_quantiles(
    payload: Mapping[str, object], issue_time: datetime
) -> dict[tuple[str, int], tuple[float, float, float]]:
    raw_collections = payload["feature_collections"]
    assert isinstance(raw_collections, list)
    expected_leads = set(range(1, 21))
    results: dict[tuple[str, int], tuple[float, float, float]] = {}
    seen_leads: set[int] = set()
    for collection in raw_collections:
        if not isinstance(collection, dict):
            raise ValueError("forecast feature collection must be an object")
        lead_day = _require_lead_day(collection.get("lead_day"))
        if lead_day in seen_leads:
            raise ValueError("forecast feature collections must not duplicate a lead")
        seen_leads.add(lead_day)
        features = collection.get("features")
        if not isinstance(features, list) or not features:
            raise ValueError("forecast feature collection must contain features")
        for feature in features:
            if not isinstance(feature, dict):
                raise ValueError("forecast feature must be an object")
            properties = feature.get("properties")
            if not isinstance(properties, dict):
                raise ValueError("forecast feature must contain properties")
            grid_id = _require_text(properties.get("grid_id"), "forecast grid_id")
            spatial_block_for_grid_id(grid_id)
            layers = properties.get("layers")
            if not isinstance(layers, dict) or set(layers) != {"eto_mm"}:
                raise ValueError("ETo-only forecast features must contain only eto_mm")
            quantiles = layers["eto_mm"]
            _require_exact_keys(quantiles, {"p10", "p50", "p90"}, "ETo forecast quantiles")
            assert isinstance(quantiles, dict)
            p10 = _finite(quantiles["p10"], "ETo p10", 0.0, math.inf)
            p50 = _finite(quantiles["p50"], "ETo p50", 0.0, math.inf)
            p90 = _finite(quantiles["p90"], "ETo p90", 0.0, math.inf)
            if not p10 <= p50 <= p90:
                raise ValueError("ETo forecast quantiles must be ordered")
            key = (grid_id, lead_day)
            if key in results:
                raise ValueError("forecast contains duplicate grid and lead")
            results[key] = (p10, p50, p90)
    if seen_leads != expected_leads:
        raise ValueError("ETo forecast must contain exactly leads 1 through 20")
    return results


def _bind_rows(
    targets: Sequence[Mapping[str, object]],
    quantiles: Mapping[tuple[str, int], tuple[float, float, float]],
    *,
    issue_time: datetime,
) -> list[_EtoRow]:
    rows: list[_EtoRow] = []
    for target in targets:
        grid_id = target["grid_id"]
        lead_day = target["lead_day"]
        assert isinstance(grid_id, str) and isinstance(lead_day, int)
        try:
            p10, p50, p90 = quantiles[(grid_id, lead_day)]
        except KeyError as error:
            raise ValueError("target does not match an ETo forecast grid and lead") from error
        latitude = target["latitude"]
        longitude = target["longitude"]
        assert isinstance(latitude, float) and isinstance(longitude, float)
        spatial_block = spatial_block_for_grid_id(grid_id)
        rows.append(
            _EtoRow(
                issue_time=issue_time,
                lead_day=lead_day,
                valid_date=target["valid_date"],  # type: ignore[arg-type]
                target_id=target["target_id"],  # type: ignore[arg-type]
                spatial_block=spatial_block,
                fold=spatial_fold_for_grid_id(grid_id),
                p10=p10,
                p50=p50,
                p90=p90,
                target_mm=target["target_mm"],  # type: ignore[arg-type]
                baseline_p50_mm=target["baseline_p50_mm"],  # type: ignore[arg-type]
            )
        )
    return rows


def _read_holdout(descriptor: object, root: Path, case_id: str, run_id: str) -> dict[str, object]:
    _require_exact_keys(descriptor, {"path", "sha256"}, "holdout receipt descriptor")
    assert isinstance(descriptor, dict)
    content = _read_evidence_file(root, descriptor["path"], "holdout receipt")
    _require_digest(content, descriptor["sha256"], "holdout receipt")
    payload = _read_json(content, "holdout receipt")
    _require_exact_keys(
        payload,
        {
            "schema_version", "kind", "case_id", "run_id", "uri", "source_version", "sha256",
            "available_at", "held_out_fold", "training_folds", "held_out_season", "training_seasons",
            "training_cutoff", "calibration_cutoff",
        },
        "holdout receipt",
    )
    assert isinstance(payload, dict)
    if payload["schema_version"] != 1 or payload["kind"] != "idaho_outlook_hindcast_holdout_receipt":
        raise ValueError("holdout receipt has an unsupported schema")
    if payload["case_id"] != case_id or payload["run_id"] != run_id:
        raise ValueError("holdout receipt does not bind its case and run")
    return payload


def _validate_holdout(
    holdout: Mapping[str, object], rows: Sequence[_EtoRow], issue_time: datetime, case_index: int
) -> tuple[int, str, list[str]]:
    held_fold = holdout["held_out_fold"]
    held_season = holdout["held_out_season"]
    training_folds = holdout["training_folds"]
    training_seasons = holdout["training_seasons"]
    if type(held_fold) is not int or held_fold not in range(5):
        raise ValueError("held_out_fold must be an integer from 0 through 4")
    if held_season not in set(_SEASONS.values()):
        raise ValueError("held_out_season is invalid")
    if not isinstance(training_folds, list) or not all(type(item) is int for item in training_folds):
        raise ValueError("training_folds must be a list of integers")
    if not isinstance(training_seasons, list) or not all(item in set(_SEASONS.values()) for item in training_seasons):
        raise ValueError("training_seasons are invalid")
    training_cutoff = _parse_utc(holdout["training_cutoff"], "training_cutoff")
    calibration_cutoff = _parse_utc(holdout["calibration_cutoff"], "calibration_cutoff")
    blockers: list[str] = []
    if held_fold in training_folds:
        blockers.append(f"case {case_index} held-out spatial fold is present in training")
    if held_season in training_seasons:
        blockers.append(f"case {case_index} held-out season is present in training")
    if training_cutoff > issue_time or calibration_cutoff > issue_time:
        blockers.append(f"case {case_index} training or calibration cutoff is after issue_time")
    for row in rows:
        if row.fold != held_fold:
            blockers.append(f"case {case_index} target fold does not match recomputed grid fold")
        if _SEASONS[row.valid_date.month] != held_season:
            blockers.append(f"case {case_index} target date is outside declared held-out season")
        if row.valid_date <= idaho_local_date(training_cutoff) or row.valid_date <= idaho_local_date(calibration_cutoff):
            blockers.append(f"case {case_index} training cutoff reaches held-out target")
    return held_fold, held_season, _deduplicate(blockers)


def _summarize(rows: Sequence[_EtoRow]) -> tuple[EtoHindcastMetric, ...]:
    groups: dict[tuple[str, str], list[_EtoRow]] = defaultdict(list)
    for row in rows:
        groups[("lead_day", str(row.lead_day))].append(row)
        groups[("season", _SEASONS[row.valid_date.month])].append(row)
        groups[("spatial_fold", str(row.fold))].append(row)
        groups[
            (
                "lead_season_spatial_fold",
                f"{row.lead_day}:{_SEASONS[row.valid_date.month]}:{row.fold}",
            )
        ].append(row)
    return tuple(
        _summarize_group(group, key, grouped_rows)
        for (group, key), grouped_rows in sorted(groups.items())
    )


def _summarize_group(group: str, key: str, rows: Sequence[_EtoRow]) -> EtoHindcastMetric:
    count = len(rows)
    errors = [row.p50 - row.target_mm for row in rows]
    baseline_errors = [row.baseline_p50_mm - row.target_mm for row in rows]
    improvement_values = [
        abs(baseline_error) - abs(error)
        for error, baseline_error in zip(errors, baseline_errors)
    ]
    coverage = [row.p10 <= row.target_mm <= row.p90 for row in rows]
    widths = [row.p90 - row.p10 for row in rows]
    pinball = [
        _pinball_loss(row.p10, row.target_mm, 0.1)
        + _pinball_loss(row.p50, row.target_mm, 0.5)
        + _pinball_loss(row.p90, row.target_mm, 0.9)
        for row in rows
    ]
    mae = sum(abs(error) for error in errors) / count
    baseline_mae = sum(abs(error) for error in baseline_errors) / count
    ci_low, ci_high, cluster_count = _bootstrap_improvement_ci(
        group, key, rows, improvement_values
    )
    return EtoHindcastMetric(
        group=group,
        key=key,
        sample_count=count,
        mae_mm=mae,
        rmse_mm=math.sqrt(sum(error * error for error in errors) / count),
        bias_mm=sum(errors) / count,
        p10_p90_coverage=sum(coverage) / count,
        mean_interval_width_mm=sum(widths) / count,
        mean_pinball_loss_mm=sum(pinball) / (count * 3),
        baseline_mae_mm=baseline_mae,
        mae_improvement_mm=baseline_mae - mae,
        mae_improvement_ci95_low_mm=ci_low,
        mae_improvement_ci95_high_mm=ci_high,
        bootstrap_cluster_count=cluster_count,
    )


def _bootstrap_improvement_ci(
    group: str,
    key: str,
    rows: Sequence[_EtoRow],
    improvement_values: Sequence[float],
) -> tuple[float | None, float | None, int]:
    clusters: dict[tuple[date, str], list[float]] = defaultdict(list)
    for row, improvement in zip(rows, improvement_values):
        clusters[(idaho_local_date(row.issue_time), row.target_id)].append(improvement)
    cluster_values = tuple(
        (sum(values), len(values))
        for _cluster, values in sorted(clusters.items(), key=lambda item: item[0])
    )
    cluster_count = len(cluster_values)
    if cluster_count < 2:
        return None, None, cluster_count
    seed_bytes = hashlib.sha256(
        f"{_BOOTSTRAP_SEED}:{group}:{key}".encode("utf-8")
    ).digest()[:8]
    generator = random.Random(int.from_bytes(seed_bytes, byteorder="big"))
    distribution: list[float] = []
    for _replicate in range(_BOOTSTRAP_REPLICATES):
        total = 0.0
        count = 0
        for _cluster in range(cluster_count):
            cluster_sum, cluster_size = cluster_values[generator.randrange(cluster_count)]
            total += cluster_sum
            count += cluster_size
        distribution.append(total / count)
    distribution.sort()
    return (
        _percentile(distribution, 0.025),
        _percentile(distribution, 0.975),
        cluster_count,
    )


def _percentile(values: Sequence[float], probability: float) -> float:
    if not values or not 0.0 <= probability <= 1.0:
        raise ValueError("percentile requires non-empty values and a probability in [0, 1]")
    position = (len(values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] + fraction * (values[upper] - values[lower])


def _pinball_loss(prediction: float, target: float, quantile: float) -> float:
    error = target - prediction
    return quantile * error if error >= 0.0 else (1.0 - quantile) * -error


def _format_ci(low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "n/a"
    return f"[{low:.3f}, {high:.3f}]"


def _evaluation_payload(report: EtoHindcastReport) -> dict[str, object]:
    """Return the canonical fields bound by the evaluation digest."""
    return {
        "archive_sha256": report.archive_sha256,
        "case_count": report.case_count,
        "target_count": report.target_count,
        "station_count": report.station_count,
        "target_sources": [
            {"uri": uri, "source_version": source_version}
            for uri, source_version in report.target_sources
        ],
        "forecast_revisions": list(report.forecast_revisions),
        "exclusions": [
            {
                "case_id": exclusion.case_id,
                "target_id": exclusion.target_id,
                "valid_date": exclusion.valid_date.isoformat(),
                "reason": exclusion.reason,
            }
            for exclusion in report.exclusions
        ],
        "validation_scope": report.validation_scope,
        "completion_blockers": list(report.completion_blockers),
        "bootstrap": {
            "seed": report.bootstrap_seed,
            "replicates": report.bootstrap_replicates,
            "cluster_definition": report.bootstrap_cluster_definition,
        },
        "metrics": [_metric_payload(metric) for metric in report.metrics],
    }


def _metric_payload(metric: EtoHindcastMetric) -> dict[str, object]:
    return {
        "group": metric.group,
        "key": metric.key,
        "sample_count": metric.sample_count,
        "mae_mm": metric.mae_mm,
        "rmse_mm": metric.rmse_mm,
        "bias_mm": metric.bias_mm,
        "p10_p90_coverage": metric.p10_p90_coverage,
        "mean_interval_width_mm": metric.mean_interval_width_mm,
        "mean_pinball_loss_mm": metric.mean_pinball_loss_mm,
        "baseline_mae_mm": metric.baseline_mae_mm,
        "mae_improvement_mm": metric.mae_improvement_mm,
        "mae_improvement_ci95_low_mm": metric.mae_improvement_ci95_low_mm,
        "mae_improvement_ci95_high_mm": metric.mae_improvement_ci95_high_mm,
        "bootstrap_cluster_count": metric.bootstrap_cluster_count,
    }


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _exclusion_sort_key(exclusion: EtoExclusion) -> tuple[str, str, str, str]:
    return (
        exclusion.case_id,
        exclusion.target_id,
        exclusion.valid_date.isoformat(),
        exclusion.reason,
    )


def _validation_scope_copy() -> dict[str, list[str]]:
    return {name: list(layers) for name, layers in _VALIDATION_SCOPE.items()}


def _require_validation_scope(value: object) -> None:
    if value != _VALIDATION_SCOPE:
        raise ValueError("validation_scope must define the frozen ETo-only boundary")


def _validate_provenance(value: object) -> None:
    _require_exact_keys(value, {"uri", "version", "sha256", "available_at"}, "evidence provenance")
    assert isinstance(value, dict)
    _validate_uri(value["uri"], "evidence provenance uri")
    _require_text(value["version"], "evidence provenance version")
    _require_digest_text(value["sha256"], "evidence provenance sha256")
    _parse_utc(value["available_at"], "evidence provenance available_at")


def _read_evidence_file(root: Path, supplied: object, label: str) -> bytes:
    if not isinstance(supplied, str) or not supplied or Path(supplied).is_absolute():
        raise ValueError(f"{label} path must be a non-empty relative path")
    supplied_path = root / supplied
    if supplied_path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    candidate = supplied_path.resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} path escapes the evidence bundle") from error
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError(f"{label} must name a regular evidence file")
    return candidate.read_bytes()


def _write_new_bytes(destination: Path, contents: bytes) -> None:
    if destination.exists() or destination.is_symlink():
        raise ValueError("ETo hindcast output must not already exist")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ValueError("ETo hindcast output parent must be a real directory")
    with destination.open("xb") as handle:
        handle.write(contents)


def _read_json(content: bytes, label: str) -> object:
    try:
        return json.loads(content.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} must be duplicate-key-free UTF-8 JSON") from error


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _require_exact_keys(value: object, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} fields must match the schema exactly")


def _require_digest(content: bytes, supplied: object, label: str) -> None:
    _require_digest_text(supplied, f"{label} sha256")
    assert isinstance(supplied, str)
    if hashlib.sha256(content).hexdigest() != supplied:
        raise ValueError(f"{label} sha256 does not match artifact bytes")


def _require_digest_text(value: object, label: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label} must be lowercase SHA-256 hex")


def _parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be strict UTC ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError(f"{label} must be strict UTC ISO-8601 text") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must be strict UTC ISO-8601 text")
    return parsed.astimezone(timezone.utc)


def _parse_date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be ISO date text")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} must be ISO date text") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must be ISO date text")
    return parsed


def _require_lead_day(value: object) -> int:
    if type(value) is not int or value not in range(1, 21):
        raise ValueError("lead_day must be an integer from 1 through 20")
    return value


def _finite(value: object, label: str, lower: float, upper: float) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or not lower <= result <= upper:
        raise ValueError(f"{label} is outside its valid range")
    return result


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _validate_uri(value: object, label: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an absolute URI")
    parsed = urlparse(value)
    if not parsed.scheme or (parsed.scheme != "file" and not parsed.netloc):
        raise ValueError(f"{label} must be an absolute URI")


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _deduplicate(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))
