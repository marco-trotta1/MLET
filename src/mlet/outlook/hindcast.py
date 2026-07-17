"""Leakage-safe, preregistered rolling hindcast contracts for the outlook.

This module is intentionally a release gate rather than a model-selection
tool.  A report can describe incomplete archived evidence, but it can promote
an outlook only when every frozen layer and lead has auditable, no-lookahead
validation coverage.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import base64
import hashlib
import json
import math
import os
from pathlib import Path
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from mlet.outlook.manifest import RunManifest


PUBLISHED_LAYERS = (
    "eto_mm",
    "eta_well_watered_mm",
    "eta_no_irrigation_mm",
)
_TARGET_KIND_BY_LAYER = {
    "eto_mm": "independent_asce_short_reference_eto",
    "eta_analysis_mm": "independent_observed_eta_analysis",
    "eta_well_watered_mm": "declared_well_watered_scenario_target",
    "eta_no_irrigation_mm": "declared_no_irrigation_scenario_target",
}
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
_ATTESTATION_PROTOCOL = b"MLET-IDAHO-OUTLOOK-HINDCAST-ATTESTATION\x00\x01"


@dataclass(frozen=True)
class _PinnedPromotionAuthority:
    """Committed, verification-only release-authority configuration."""

    key_id: str
    algorithm: str
    public_key: bytes


def _load_pinned_promotion_authority() -> _PinnedPromotionAuthority:
    """Load the repository-pinned public verification key, never a signer."""
    path = Path(__file__).with_name("promotion_authority.json")
    try:
        raw = _load_json_bytes(path.read_bytes(), "promotion authority configuration")
    except OSError as error:
        raise RuntimeError("committed promotion authority configuration is unavailable") from error
    _require_exact_keys(
        raw,
        {"schema_version", "algorithm", "key_id", "public_key_base64"},
        "promotion authority configuration",
    )
    assert isinstance(raw, dict)
    key_id = raw["key_id"]
    encoded = raw["public_key_base64"]
    if raw["schema_version"] != 1 or raw["algorithm"] != "ed25519" or not isinstance(key_id, str) or not key_id.strip() or not isinstance(encoded, str):
        raise RuntimeError("committed promotion authority configuration is invalid")
    try:
        public_key = base64.b64decode(encoded, validate=True)
        Ed25519PublicKey.from_public_bytes(public_key)
    except (ValueError, TypeError) as error:
        raise RuntimeError("committed promotion authority public key is invalid") from error
    return _PinnedPromotionAuthority(key_id=key_id, algorithm="ed25519", public_key=public_key)


@dataclass(frozen=True)
class AvailableRecord:
    """An immutable input receipt whose historical availability is auditable."""

    name: str
    available_at: datetime
    source_version: str
    sha256: str
    uri: str

    def __post_init__(self) -> None:
        _require_text(self.name, "source name")
        object.__setattr__(self, "available_at", _require_strict_utc(self.available_at, "available_at"))
        _require_text(self.source_version, "source_version")
        if not isinstance(self.sha256, str) or len(self.sha256) != 64:
            raise ValueError("source sha256 must be a 64-character hexadecimal digest")
        try:
            int(self.sha256, 16)
        except ValueError as error:
            raise ValueError("source sha256 must be a 64-character hexadecimal digest") from error
        parsed = urlparse(self.uri)
        if not isinstance(self.uri, str) or not parsed.scheme or (not parsed.netloc and parsed.scheme != "file"):
            raise ValueError("source uri must be an absolute URI")


@dataclass(frozen=True)
class HindcastRow:
    """One quantified forecast/scenario result and its independently named target."""

    layer: str
    lead_day: int
    valid_date: date
    spatial_block: str
    p10: float
    p50: float
    p90: float
    target_mm: float
    target_kind: str
    target_available_at: datetime

    def __post_init__(self) -> None:
        if self.layer not in _TARGET_KIND_BY_LAYER:
            raise ValueError(f"hindcast layer is not recognized: {self.layer!r}")
        if isinstance(self.lead_day, bool) or not isinstance(self.lead_day, int) or not 1 <= self.lead_day <= 20:
            raise ValueError("hindcast lead_day must be an integer from 1 through 20")
        if not isinstance(self.valid_date, date) or isinstance(self.valid_date, datetime):
            raise ValueError("hindcast valid_date must be a calendar date")
        _require_text(self.spatial_block, "spatial_block")
        p10 = _finite_nonnegative(self.p10, "p10")
        p50 = _finite_nonnegative(self.p50, "p50")
        p90 = _finite_nonnegative(self.p90, "p90")
        if p10 > p50 or p50 > p90:
            raise ValueError("hindcast p10, p50, and p90 must be ordered")
        target = _finite_nonnegative(self.target_mm, "target_mm")
        expected_target = _TARGET_KIND_BY_LAYER[self.layer]
        if self.target_kind != expected_target:
            if self.layer.startswith("eta_") and "scenario" in expected_target:
                raise ValueError(
                    "conditional ETa rows require their declared scenario target; "
                    "they cannot be labelled as observed actual ET"
                )
            raise ValueError(
                f"hindcast target_kind for {self.layer} must be {expected_target!r}"
            )
        available_at = _require_strict_utc(self.target_available_at, "target_available_at")
        object.__setattr__(self, "p10", p10)
        object.__setattr__(self, "p50", p50)
        object.__setattr__(self, "p90", p90)
        object.__setattr__(self, "target_mm", target)
        object.__setattr__(self, "target_available_at", available_at)


@dataclass(frozen=True)
class HindcastCase:
    """One archived forecast issue and every score eligible for that issue."""

    issue_time: datetime
    records: tuple[AvailableRecord, ...]
    rows: tuple[HindcastRow, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "issue_time", _require_strict_utc(self.issue_time, "issue_time"))
        if not isinstance(self.records, tuple) or any(not isinstance(item, AvailableRecord) for item in self.records):
            raise ValueError("hindcast records must be a tuple of AvailableRecord")
        if not isinstance(self.rows, tuple) or any(not isinstance(item, HindcastRow) for item in self.rows):
            raise ValueError("hindcast rows must be a tuple of HindcastRow")
        for row in self.rows:
            if row.valid_date != self.issue_time.date().fromordinal(
                self.issue_time.date().toordinal() + row.lead_day
            ):
                raise ValueError("hindcast valid_date must equal issue date plus lead_day")
            valid_day_end = datetime.combine(
                row.valid_date, time.max, tzinfo=timezone.utc
            )
            if row.target_available_at <= valid_day_end:
                raise ValueError(
                    "hindcast target_available_at must be later than valid_date"
                )


@dataclass(frozen=True)
class HindcastMetric:
    """A transparent aggregate, including the sample count needed to interpret it."""

    layer: str
    group: str
    key: str
    sample_count: int
    mae_mm: float | None
    rmse_mm: float | None
    bias_mm: float | None
    p10_p90_coverage: float | None
    mean_interval_width_mm: float | None


@dataclass(frozen=True)
class SourceLatencySummary:
    """Source availability audit for a whole hindcast report."""

    source_name: str
    record_count: int
    late_record_count: int
    max_latency_days: float | None


@dataclass(frozen=True)
class CaseInputAudit:
    """Per-issue source-selection evidence retained alongside aggregate metrics."""

    case_index: int
    issue_time: datetime
    selected_records: tuple[AvailableRecord, ...]
    excluded_after_issue: tuple[AvailableRecord, ...]

    @property
    def selected_source_names(self) -> tuple[str, ...]:
        """Stable source names selected by the issue-time cutoff."""
        return tuple(record.name for record in self.selected_records)

    @property
    def excluded_after_issue_names(self) -> tuple[str, ...]:
        """Stable source names that were available too late for the case."""
        return tuple(record.name for record in self.excluded_after_issue)


@dataclass(frozen=True)
class HindcastReport:
    """Aggregate statistics only.

    This public value deliberately is *not* a publication authority.  It is
    useful for exploratory summaries and tests, but a caller can construct it
    (or rows feeding it), so :func:`write_hindcast_validation` refuses it.
    Only the private, hash-bound receipt made by
    :func:`evaluate_hindcast_evidence` may assert a promotion decision.
    """

    metrics: tuple[HindcastMetric, ...]
    source_latency: tuple[SourceLatencySummary, ...]
    input_audit: tuple[CaseInputAudit, ...]
    case_count: int
    fixture_non_scientific: bool
    fixture_reason: str | None
    promotion_blockers: tuple[str, ...]

    @property
    def promotion(self) -> bool:
        """Diagnostic status derived from blockers, never publication authority."""
        return not self.promotion_blockers

    def validation_record(self) -> dict[str, object]:
        """Return a non-authoritative diagnostic record, never a release receipt."""
        return {
            "schema_version": 1,
            "kind": "idaho_outlook_hindcast_validation",
            "fixture_non_scientific": self.fixture_non_scientific,
            "fixture_reason": self.fixture_reason,
            "case_count": self.case_count,
            "promotion": self.promotion,
            "promotion_blockers": list(self.promotion_blockers),
            "metrics": [
                {
                    "layer": metric.layer,
                    "group": metric.group,
                    "key": metric.key,
                    "sample_count": metric.sample_count,
                    "mae_mm": metric.mae_mm,
                    "rmse_mm": metric.rmse_mm,
                    "bias_mm": metric.bias_mm,
                    "p10_p90_coverage": metric.p10_p90_coverage,
                    "mean_interval_width_mm": metric.mean_interval_width_mm,
                }
                for metric in self.metrics
            ],
            "input_audit": [
                {
                    "case_index": audit.case_index,
                    "issue_time": _format_utc(audit.issue_time),
                    "selected_records": [_receipt_record(record) for record in audit.selected_records],
                    "excluded_after_issue": [
                        _receipt_record(record) for record in audit.excluded_after_issue
                    ],
                }
                for audit in self.input_audit
            ],
            "source_latency": [
                {
                    "source_name": item.source_name,
                    "record_count": item.record_count,
                    "late_record_count": item.late_record_count,
                    "max_latency_days": item.max_latency_days,
                }
                for item in self.source_latency
            ],
        }


@dataclass(frozen=True)
class EvaluationReceipt:
    """Content-bound evaluation result whose promotion needs external authority.

    This type is deliberately not a security boundary.  It is public data that
    can be reconstructed by any caller.  ``write_hindcast_validation`` checks
    a separately held external Ed25519 attestation before it will serialize a
    true promotion.  This repository contains only the pinned public key.
    """

    report: HindcastReport
    evidence_path: Path
    evaluation_digest: str
    case_sha256: tuple[str, ...]
    attestation: dict[str, object] | None


def select_inputs_as_of(
    records: Sequence[AvailableRecord], *, issue_time: datetime
) -> list[AvailableRecord]:
    """Select only immutable inputs that were demonstrably available at issue time."""
    cutoff = _require_strict_utc(issue_time, "issue_time")
    if any(not isinstance(record, AvailableRecord) for record in records):
        raise ValueError("records must contain AvailableRecord values")
    return [record for record in records if record.available_at <= cutoff]


def run_hindcast(
    cases: Sequence[HindcastCase], *, fixture_reason: str | None = None
) -> HindcastReport:
    """Aggregate typed rows without granting a publication decision.

    This helper intentionally cannot promote.  Promotable rows must be parsed
    from byte-verified forecast and target artifacts by
    :func:`evaluate_hindcast_evidence`; accepting caller supplied rows here
    would make a perfect inline table indistinguishable from a real hindcast.
    """
    return _aggregate_hindcast(cases, fixture_reason=fixture_reason, verified=False)


def _aggregate_hindcast(
    cases: Sequence[HindcastCase], *, fixture_reason: str | None, verified: bool
) -> HindcastReport:
    """Aggregate rows after the caller's evidence boundary has been selected."""
    if any(not isinstance(case, HindcastCase) for case in cases):
        raise ValueError("cases must contain HindcastCase values")
    fixture = fixture_reason is not None
    if fixture_reason is not None:
        _require_text(fixture_reason, "fixture_reason")

    grouped: dict[tuple[str, str, str], list[HindcastRow]] = defaultdict(list)
    source_audit: dict[str, list[tuple[AvailableRecord, datetime]]] = defaultdict(list)
    input_audit: list[CaseInputAudit] = []
    blockers: list[str] = []
    for case_index, case in enumerate(cases):
        eligible = select_inputs_as_of(case.records, issue_time=case.issue_time)
        excluded = tuple(
            record for record in case.records if record.available_at > case.issue_time
        )
        input_audit.append(
            CaseInputAudit(
                case_index=case_index,
                issue_time=case.issue_time,
                selected_records=tuple(eligible),
                excluded_after_issue=excluded,
            )
        )
        if not eligible:
            blockers.append(f"case {case_index} has no auditable source available at issue_time")
        for record in case.records:
            source_audit[record.name].append((record, case.issue_time))
            if record.available_at > case.issue_time:
                blockers.append(
                    f"case {case_index} source {record.name!r} was available after issue_time"
                )
        for row in case.rows:
            grouped[(row.layer, "lead_day", str(row.lead_day))].append(row)
            grouped[(row.layer, "month", f"{row.valid_date.month:02d}")].append(row)
            grouped[(row.layer, "season", _SEASONS[row.valid_date.month])].append(row)
            grouped[(row.layer, "spatial_block", row.spatial_block)].append(row)

    metrics = tuple(
        _summarize_rows(layer, group, key, rows)
        for (layer, group, key), rows in sorted(grouped.items())
    )
    metric_index = {(metric.layer, metric.group, metric.key): metric for metric in metrics}
    for layer in PUBLISHED_LAYERS:
        for lead_day in range(1, 21):
            metric = metric_index.get((layer, "lead_day", str(lead_day)))
            if metric is None or metric.sample_count == 0:
                blockers.append(f"missing {layer} sample count for published lead {lead_day}")
            elif metric.p10_p90_coverage is None:
                blockers.append(f"missing {layer} p10-p90 coverage for published lead {lead_day}")
    if not cases:
        blockers.append("no historical forecast issues were supplied")
    if fixture:
        blockers.insert(0, f"software fixture is non-scientific: {fixture_reason}")
    if not verified:
        blockers.insert(
            0,
            "standalone hindcast rows are aggregation-only; no verified evidence receipt was supplied",
        )

    source_latency = _summarize_source_latency(source_audit)
    return HindcastReport(
        metrics=metrics,
        source_latency=source_latency,
        input_audit=tuple(input_audit),
        case_count=len(cases),
        fixture_non_scientific=fixture,
        fixture_reason=fixture_reason,
        promotion_blockers=tuple(_deduplicate(blockers)),
    )


def evaluate_hindcast_evidence(path: Path) -> tuple[HindcastReport, EvaluationReceipt]:
    """Evaluate a version-3 archived-evidence bundle.

    The evaluator can make a transparent non-promotable report without a key.
    A true promotion additionally needs an external Ed25519 attestation over
    the exact evidence digest and the independently reconstructed report
    digest.  The verifier has only its committed public key.
    """
    report, digest, case_hashes, attestation = _evaluate_evidence_bundle(path)
    authority_error = _verify_promotion_attestation(attestation, digest, report)
    if authority_error is not None:
        report = _with_blockers(report, [authority_error])
    return report, EvaluationReceipt(
        report=report,
        evidence_path=Path(path).resolve(strict=True),
        evaluation_digest=digest,
        case_sha256=case_hashes,
        attestation=attestation,
    )


def build_promotion_attestation_request(path: Path) -> dict[str, object]:
    """Prepare a verification request for an external release authority.

    This helper performs no signing and has no private-key configuration.  The
    authority signs :func:`_attestation_message` outside MLET, then embeds the
    returned signature with these exact fields in the evidence bundle.
    """
    report, digest, _case_hashes, _attestation = _evaluate_evidence_bundle(path)
    if not report.promotion:
        raise ValueError("cannot request an attestation for a hindcast that fails the frozen release gates")
    return {
        "schema_version": 1,
        "algorithm": _PINNED_PROMOTION_AUTHORITY.algorithm,
        "key_id": _PINNED_PROMOTION_AUTHORITY.key_id,
        "evaluation_digest": digest,
        "report_sha256": _report_sha256(report),
    }


def _evaluate_evidence_bundle(
    path: Path,
) -> tuple[HindcastReport, str, tuple[str, ...], dict[str, object] | None]:
    """Reconstruct a report and canonical digest without consulting authority."""
    evidence_path = Path(path).resolve(strict=True)
    root = evidence_path.parent
    raw = _load_json_bytes(evidence_path.read_bytes(), "hindcast evidence")
    if not isinstance(raw, dict) or raw.get("schema_version") != 3:
        raise ValueError("hindcast evidence must be a schema_version 3 object")
    _require_exact_keys(
        raw,
        {
            "schema_version", "evidence_classification", "provenance", "cases",
            "promotion_attestation",
        },
        "hindcast evidence",
    )
    classification = raw["evidence_classification"]
    if type(classification) is not str or classification not in {"real_archived", "software_fixture"}:
        raise ValueError("evidence_classification must be real_archived or software_fixture")
    provenance = raw["provenance"]
    _parse_real_provenance(provenance, required=classification == "real_archived")
    raw_cases = raw["cases"]
    if not isinstance(raw_cases, list):
        raise ValueError("hindcast evidence cases must be a list")
    cases: list[HindcastCase] = []
    case_hashes: list[str] = []
    case_material: list[dict[str, object]] = []
    blockers: list[str] = []
    for index, raw_case in enumerate(raw_cases):
        case, digest, material, case_blockers, held_fold, held_season = _parse_verified_case(raw_case, root, index)
        cases.append(case)
        case_hashes.append(digest)
        case_material.append(material)
        blockers.extend(case_blockers)
        # A one-fold or one-season score is a diagnostic, not the frozen
        # geographically and seasonally held-out validation protocol.
        if index == 0:
            held_folds: set[int] = set()
            held_seasons: set[str] = set()
        held_folds.add(held_fold)
        held_seasons.add(held_season)
    if raw_cases:
        missing_folds = sorted(set(range(5)) - held_folds)
        missing_seasons = sorted(set(_SEASONS.values()) - held_seasons)
        if missing_folds:
            blockers.append(f"missing preregistered held-out spatial folds: {missing_folds}")
        if missing_seasons:
            blockers.append(f"missing preregistered held-out seasons: {missing_seasons}")
    fixture_reason = None
    if classification != "real_archived":
        fixture_reason = "evidence classification is software_fixture"
    report = _aggregate_hindcast(tuple(cases), fixture_reason=fixture_reason, verified=True)
    if blockers:
        report = HindcastReport(
            metrics=report.metrics,
            source_latency=report.source_latency,
            input_audit=report.input_audit,
            case_count=report.case_count,
            fixture_non_scientific=report.fixture_non_scientific,
            fixture_reason=report.fixture_reason,
            promotion_blockers=tuple(_deduplicate([*report.promotion_blockers, *blockers])),
        )
    digest = hashlib.sha256(
        _canonical_json(
            {
                "schema_version": 1,
                "evidence_classification": classification,
                "provenance": raw["provenance"],
                "cases": case_material,
            }
        ).encode("utf-8")
    ).hexdigest()
    attestation = raw["promotion_attestation"]
    if attestation is not None and not isinstance(attestation, dict):
        raise ValueError("promotion_attestation must be an object or null")
    return report, digest, tuple(case_hashes), attestation


def load_hindcast_cases(path: Path) -> tuple[tuple[HindcastCase, ...], str | None]:
    """Load a strict, audit-friendly JSON hindcast receipt.

    Fixtures must set ``fixture_non_scientific`` to true and give a non-empty
    note.  The returned reason is intentionally passed to :func:`run_hindcast`
    so that an empty fixture cannot accidentally look like an evidence set.
    """
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("hindcast cases must be a schema_version 1 object")
    fixture = payload.get("fixture_non_scientific", False)
    if not isinstance(fixture, bool):
        raise ValueError("fixture_non_scientific must be boolean")
    note = payload.get("note")
    if fixture:
        _require_text(note, "fixture note")
        fixture_reason = str(note)
    elif note is not None and not isinstance(note, str):
        raise ValueError("hindcast note must be text when provided")
    else:
        fixture_reason = None
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("hindcast cases must be a list")
    return tuple(_parse_case(item) for item in raw_cases), fixture_reason


def write_hindcast_validation(receipt: object, destination: Path) -> Path:
    """Write a validation record, independently rejecting unauthorised truth.

    This verifier never trusts Python object identity or a private attribute:
    a caller-made receipt/report may be written only as non-promotable.  A
    requested true promotion must carry a valid externally signed attestation
    over both the canonical evidence digest and the exact report bytes.
    """
    if not isinstance(receipt, EvaluationReceipt):
        raise ValueError("hindcast validation requires an evaluation receipt")
    _validate_evaluation_receipt(receipt)
    if receipt.report.promotion:
        authority_error = _verify_promotion_attestation(
            receipt.attestation, receipt.evaluation_digest, receipt.report
        )
        if authority_error is not None:
            raise ValueError(f"hindcast validation refuses unauthorised promotion: {authority_error}")
        rebuilt, rebuilt_digest, rebuilt_cases, _attestation = _evaluate_evidence_bundle(
            receipt.evidence_path
        )
        if (
            rebuilt_digest != receipt.evaluation_digest
            or rebuilt_cases != receipt.case_sha256
            or _canonical_json(rebuilt.validation_record())
            != _canonical_json(receipt.report.validation_record())
        ):
            raise ValueError("hindcast validation refuses a receipt not reconstructed from evidence")
    encoded = (
        json.dumps(_receipt_payload(receipt), sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    return _write_new_bytes(Path(destination), encoded)


def render_hindcast_markdown(report: HindcastReport) -> str:
    """Render a human-readable report that preserves the claim boundary."""
    if not isinstance(report, HindcastReport):
        raise ValueError("hindcast markdown requires a HindcastReport")
    lines = [
        "# Idaho Outlook Hindcast Validation",
        "",
        f"Promotion: **{'true' if report.promotion else 'false'}**",
        f"Historical issue cases: {report.case_count}",
        "",
    ]
    if report.fixture_non_scientific:
        lines.extend(
            [
                "## Software-fixture status",
                "",
                "This is a deterministic software fixture, not a hindcast or scientific validation result.",
                f"Reason: {report.fixture_reason}",
                "",
            ]
        )
    lines.extend(["## Promotion gate", ""])
    if report.promotion_blockers:
        lines.extend(f"- {blocker}" for blocker in report.promotion_blockers)
    else:
        lines.append("- All frozen no-lookahead, lead coverage, and interval coverage gates passed.")
    lines.extend(
        [
            "",
            "## Lead-day metrics",
            "",
            "| layer | lead day | n | MAE (mm/day) | RMSE (mm/day) | bias (mm/day) | p10–p90 coverage | mean interval width (mm/day) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for metric in report.metrics:
        if metric.group == "lead_day":
            lines.append(_metric_row(metric))
    lines.extend(
        [
            "",
            "## Coverage and stratification",
            "",
            "| layer | stratum | key | n | p10–p90 coverage |",
            "|---|---|---|---:|---:|",
        ]
    )
    for metric in report.metrics:
        if metric.group != "lead_day":
            lines.append(
                f"| {metric.layer} | {metric.group} | {metric.key} | {metric.sample_count} | {_format_metric(metric.p10_p90_coverage)} |"
            )
    lines.extend(
        [
            "",
            "## Source latency audit",
            "",
            "| source | records | late at issue | maximum input age (days) |",
            "|---|---:|---:|---:|",
        ]
    )
    for source in report.source_latency:
        lines.append(
            f"| {source.source_name} | {source.record_count} | {source.late_record_count} | {_format_metric(source.max_latency_days)} |"
        )
    lines.extend(
        [
            "",
            "Conditional ETa scenarios retain their declared assumptions and are not scored or described as generic observed actual ET.",
            "",
        ]
    )
    return "\n".join(lines)


def write_hindcast_markdown(report: HindcastReport, destination: Path) -> Path:
    """Write one report atomically enough to prevent silent receipt replacement."""
    return _write_new_bytes(Path(destination), render_hindcast_markdown(report).encode("utf-8"))


def _parse_case(value: object) -> HindcastCase:
    if not isinstance(value, dict):
        raise ValueError("each hindcast case must be an object")
    raw_issue = value.get("issue_time", value.get("issued_at"))
    issue_time = _parse_utc(raw_issue, "case issue_time")
    raw_records = value.get("records", value.get("sources", []))
    if not isinstance(raw_records, list):
        raise ValueError("case records must be a list")
    records = tuple(_parse_record(item) for item in raw_records)
    raw_rows = value.get("rows", [])
    if not isinstance(raw_rows, list):
        raise ValueError("case rows must be a list")
    rows = tuple(_parse_row(item) for item in raw_rows)
    return HindcastCase(issue_time=issue_time, records=records, rows=rows)


def _parse_record(value: object) -> AvailableRecord:
    if not isinstance(value, dict):
        raise ValueError("each source record must be an object")
    return AvailableRecord(
        name=value.get("name"),
        available_at=_parse_utc(value.get("available_at"), "source available_at"),
        source_version=value.get("source_version"),
        sha256=value.get("sha256"),
        uri=value.get("uri"),
    )


def _parse_row(value: object) -> HindcastRow:
    if not isinstance(value, dict):
        raise ValueError("each hindcast row must be an object")
    raw_date = value.get("valid_date")
    if not isinstance(raw_date, str):
        raise ValueError("hindcast valid_date must be ISO text")
    try:
        valid_date = date.fromisoformat(raw_date)
    except ValueError as error:
        raise ValueError("hindcast valid_date must be ISO text") from error
    return HindcastRow(
        layer=value.get("layer"),
        lead_day=value.get("lead_day"),
        valid_date=valid_date,
        spatial_block=value.get("spatial_block"),
        p10=value.get("p10"),
        p50=value.get("p50"),
        p90=value.get("p90"),
        target_mm=value.get("target_mm"),
        target_kind=value.get("target_kind"),
        target_available_at=_parse_utc(value.get("target_available_at"), "target_available_at"),
    )


def _parse_verified_case(
    value: object, root: Path, case_index: int
) -> tuple[HindcastCase, str, dict[str, object], list[str], int, str]:
    if not isinstance(value, dict):
        raise ValueError("each evidence case must be an object")
    _require_exact_keys(
        value,
        {
            "case_id", "issue_time", "forecast", "target", "source_receipt_artifacts",
            "holdout_receipt", "scenario_receipt_artifacts",
        },
        "evidence case",
    )
    case_id = _require_text(value["case_id"], "case_id")
    issue = _parse_utc(value["issue_time"], "case issue_time")
    forecast = value["forecast"]
    target = value["target"]
    if not isinstance(forecast, dict) or not isinstance(target, dict):
        raise ValueError("evidence case forecast and target must be objects")
    _require_exact_keys(
        forecast, {"run_id", "manifest_path", "manifest_sha256", "artifact_path", "artifact_sha256"},
        "forecast receipt",
    )
    _require_exact_keys(
        target, {"path", "uri", "source_version", "sha256", "available_at"},
        "target receipt",
    )
    manifest_bytes = _read_evidence_file(root, forecast["manifest_path"], "forecast manifest")
    _require_digest(manifest_bytes, forecast["manifest_sha256"], "forecast manifest")
    manifest = RunManifest.from_json(manifest_bytes.decode("utf-8"))
    if forecast["run_id"] != manifest.run_id:
        raise ValueError("forecast run_id does not match its verified manifest")
    if manifest.issued_at != issue:
        raise ValueError("forecast manifest issued_at must equal case issue_time")
    forecast_bytes = _read_evidence_file(root, forecast["artifact_path"], "forecast artifact")
    _require_digest(forecast_bytes, forecast["artifact_sha256"], "forecast artifact")
    manifest_hashes = dict(manifest.artifact_sha256)
    if manifest_hashes.get("outlook.json") != forecast["artifact_sha256"]:
        raise ValueError("forecast artifact hash does not match verified manifest outlook.json")
    forecast_payload = _load_json_bytes(forecast_bytes, "forecast artifact")
    if not isinstance(forecast_payload, dict):
        raise ValueError("forecast artifact must be a JSON object")
    if forecast_payload.get("run_id") != manifest.run_id:
        raise ValueError("forecast artifact run_id does not match manifest")
    if forecast_payload.get("issued_at") != _format_utc(issue):
        raise ValueError("forecast artifact issued_at does not match case issue_time")
    forecast_blockers = _forecast_classification_blockers(forecast_payload, case_index)
    target_bytes = _read_evidence_file(root, target["path"], "target artifact")
    _require_digest(target_bytes, target["sha256"], "target artifact")
    target_available = _parse_utc(target["available_at"], "target available_at")
    AvailableRecord(
        name="target_artifact", available_at=target_available,
        source_version=target["source_version"], sha256=target["sha256"], uri=target["uri"],
    )
    target_payload = _load_json_bytes(target_bytes, "target artifact")
    _bind_target_receipt(target_payload, target, target_available, case_id, manifest.run_id)
    rows = _rows_from_verified_artifacts(
        forecast_payload, target_payload, issue, target_available, case_index
    )
    source_receipts, source_hashes = _parse_and_bind_source_receipt_artifacts(
        value["source_receipt_artifacts"], root, manifest, issue, case_id
    )
    holdout, holdout_hash = _read_receipt_artifact(
        root, value["holdout_receipt"], "idaho_outlook_hindcast_holdout_receipt", case_id,
        manifest.run_id, "holdout receipt",
    )
    blockers, held_fold, held_season = _validate_holdout(holdout, rows, issue, case_index)
    scenario_receipts, scenario_hashes = _read_scenario_receipt_artifacts(
        value["scenario_receipt_artifacts"], root, issue, rows, case_index, case_id,
        manifest.run_id,
    )
    del scenario_receipts
    blockers = [*forecast_blockers, *blockers]
    material: dict[str, object] = {
        "case_id": case_id,
        "run_id": manifest.run_id,
        "issue_time": _format_utc(issue),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "forecast_sha256": hashlib.sha256(forecast_bytes).hexdigest(),
        "target_sha256": hashlib.sha256(target_bytes).hexdigest(),
        "source_receipt_sha256": source_hashes,
        "holdout_receipt_sha256": holdout_hash,
        "scenario_receipt_sha256": scenario_hashes,
    }
    digest = hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()
    return (
        HindcastCase(issue_time=issue, records=source_receipts, rows=rows), digest,
        material, blockers, held_fold, held_season,
    )


def _rows_from_verified_artifacts(
    forecast: object, target: object, issue: datetime, target_available: datetime, case_index: int
) -> tuple[HindcastRow, ...]:
    if not isinstance(forecast, dict) or not isinstance(target, dict):
        raise ValueError("forecast and target artifacts must be JSON objects")
    collections = forecast.get("feature_collections")
    if not isinstance(collections, list):
        raise ValueError("forecast artifact must contain feature_collections")
    quantiles: dict[tuple[str, int, str], tuple[float, float, float]] = {}
    for collection in collections:
        if not isinstance(collection, dict):
            raise ValueError("forecast feature collection must be an object")
        lead = collection.get("lead_day")
        features = collection.get("features")
        if isinstance(lead, bool) or not isinstance(lead, int) or not isinstance(features, list):
            raise ValueError("forecast feature collection must contain lead_day and features")
        for feature in features:
            try:
                props = feature["properties"]
                grid_id = props["grid_id"]
                layers = props["layers"]
            except (TypeError, KeyError) as error:
                raise ValueError("forecast feature lacks properties/grid_id/layers") from error
            if not isinstance(grid_id, str) or not isinstance(layers, dict):
                raise ValueError("forecast feature has invalid grid_id or layers")
            for layer in PUBLISHED_LAYERS:
                q = layers.get(layer)
                if not isinstance(q, dict):
                    raise ValueError(f"forecast artifact lacks {layer} quantiles")
                values = tuple(q.get(name) for name in ("p10", "p50", "p90"))
                if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in values):
                    raise ValueError("forecast quantiles must be numeric")
                quantiles[(layer, lead, grid_id)] = (float(values[0]), float(values[1]), float(values[2]))
    _require_exact_keys(target, {"schema_version", "kind", "receipt", "values"}, "target artifact")
    if target.get("schema_version") != 1 or target.get("kind") != "idaho_outlook_hindcast_target":
        raise ValueError("target artifact must be a versioned idaho_outlook_hindcast_target")
    entries = target.get("values")
    if not isinstance(entries, list):
        raise ValueError("target artifact values must be a list")
    rows: list[HindcastRow] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("target artifact value must be an object")
        _require_exact_keys(entry, {"layer", "lead_day", "valid_date", "grid_id", "target_mm", "target_kind"}, "target value")
        valid_text = entry["valid_date"]
        if not isinstance(valid_text, str):
            raise ValueError("target valid_date must be ISO text")
        valid = date.fromisoformat(valid_text)
        layer, lead, grid = entry["layer"], entry["lead_day"], entry["grid_id"]
        if not isinstance(layer, str) or isinstance(lead, bool) or not isinstance(lead, int) or not isinstance(grid, str):
            raise ValueError("target value layer, lead_day, and grid_id are invalid")
        q = quantiles.get((layer, lead, grid))
        if q is None:
            raise ValueError("target value does not identity-match a forecast artifact quantile")
        rows.append(HindcastRow(
            layer=layer, lead_day=lead, valid_date=valid, spatial_block=grid,
            p10=q[0], p50=q[1], p90=q[2], target_mm=entry["target_mm"],
            target_kind=entry["target_kind"], target_available_at=target_available,
        ))
    if not rows:
        raise ValueError(f"case {case_index} target artifact contains no values")
    return tuple(rows)


def _bind_target_receipt(
    target_payload: object, target_receipt: dict[object, object], available_at: datetime,
    case_id: str, run_id: str,
) -> None:
    """Require availability/version/URI claims to be inside hashed target bytes."""
    if not isinstance(target_payload, dict):
        raise ValueError("target artifact must be an object")
    receipt = target_payload.get("receipt")
    if not isinstance(receipt, dict):
        raise ValueError("target artifact must embed its immutable receipt")
    _require_exact_keys(
        receipt, {"case_id", "run_id", "uri", "source_version", "available_at"},
        "target artifact receipt",
    )
    if (
        receipt["case_id"] != case_id
        or receipt["run_id"] != run_id
        or receipt["uri"] != target_receipt["uri"]
        or receipt["source_version"] != target_receipt["source_version"]
        or receipt["available_at"] != _format_utc(available_at)
    ):
        raise ValueError("target receipt does not match immutable target artifact")


def _summarize_rows(
    layer: str, group: str, key: str, rows: Sequence[HindcastRow]
) -> HindcastMetric:
    errors = [row.p50 - row.target_mm for row in rows]
    coverage = [row.p10 <= row.target_mm <= row.p90 for row in rows]
    widths = [row.p90 - row.p10 for row in rows]
    count = len(rows)
    return HindcastMetric(
        layer=layer,
        group=group,
        key=key,
        sample_count=count,
        mae_mm=sum(abs(error) for error in errors) / count if count else None,
        rmse_mm=math.sqrt(sum(error * error for error in errors) / count) if count else None,
        bias_mm=sum(errors) / count if count else None,
        p10_p90_coverage=sum(coverage) / count if count else None,
        mean_interval_width_mm=sum(widths) / count if count else None,
    )


def _parse_and_bind_source_receipt_artifacts(
    value: object, root: Path, manifest: RunManifest, issue: datetime, case_id: str,
) -> tuple[tuple[AvailableRecord, ...], list[str]]:
    if not isinstance(value, list):
        raise ValueError("source_receipt_artifacts must be a list")
    records: list[AvailableRecord] = []
    artifact_hashes: list[str] = []
    for descriptor in value:
        payload, artifact_hash = _read_receipt_artifact(
            root, descriptor, "idaho_outlook_hindcast_source_receipt", case_id, manifest.run_id,
            "source receipt artifact",
        )
        _require_exact_keys(
            payload,
            {
                "schema_version", "kind", "case_id", "run_id", "name", "uri",
                "source_version", "sha256", "available_at",
            },
            "source receipt artifact",
        )
        records.append(_parse_record(payload))
        artifact_hashes.append(artifact_hash)
    records_tuple = tuple(records)
    manifest_sources = {source.name: source for source in manifest.sources}
    if {record.name for record in records_tuple} != set(manifest_sources) or len(records_tuple) != len(manifest_sources):
        raise ValueError("source receipts must bind every manifest source exactly once")
    for record in records_tuple:
        source = manifest_sources[record.name]
        if record.sha256 != source.sha256 or record.uri != source.uri:
            raise ValueError("source receipt identity does not match verified manifest source")
        if record.available_at > issue:
            raise ValueError("source receipt was available after case issue_time")
    return records_tuple, sorted(artifact_hashes)


def _validate_holdout(value: object, rows: Sequence[HindcastRow], issue: datetime, index: int) -> tuple[list[str], int, str]:
    if not isinstance(value, dict):
        raise ValueError("holdout must be an object")
    _require_exact_keys(
        value,
        {
            "schema_version", "kind", "case_id", "run_id", "uri", "source_version", "sha256",
            "available_at", "spatial_block", "fold", "held_out_fold", "training_folds",
            "held_out_season", "training_seasons", "training_cutoff", "calibration_cutoff",
        },
        "holdout",
    )
    block = value["spatial_block"]
    fold, held = value["fold"], value["held_out_fold"]
    if not isinstance(block, str) or isinstance(fold, bool) or not isinstance(fold, int) or isinstance(held, bool) or not isinstance(held, int):
        raise ValueError("holdout spatial_block and folds are invalid")
    training_folds = value["training_folds"]
    seasons = value["training_seasons"]
    held_season = value["held_out_season"]
    if not isinstance(training_folds, list) or not all(isinstance(item, int) and not isinstance(item, bool) for item in training_folds):
        raise ValueError("training_folds must be integer list")
    if not isinstance(seasons, list) or not all(item in set(_SEASONS.values()) for item in seasons) or held_season not in set(_SEASONS.values()):
        raise ValueError("holdout seasons are invalid")
    training_cutoff = _parse_utc(value["training_cutoff"], "training_cutoff")
    calibration_cutoff = _parse_utc(value["calibration_cutoff"], "calibration_cutoff")
    blockers: list[str] = []
    if fold != held or held in training_folds:
        blockers.append(f"case {index} held-out spatial fold is present in training")
    if training_cutoff > issue or calibration_cutoff > issue:
        blockers.append(f"case {index} training or calibration cutoff is after issue_time")
    if held_season in seasons:
        blockers.append(f"case {index} held-out season is present in training")
    for row in rows:
        if row.spatial_block != block:
            blockers.append(f"case {index} target grid is outside declared held-out spatial block")
        if _SEASONS[row.valid_date.month] != held_season:
            blockers.append(f"case {index} target date is outside declared held-out season")
        if row.valid_date <= training_cutoff.date() or row.valid_date <= calibration_cutoff.date():
            blockers.append(f"case {index} training or calibration cutoff reaches held-out target")
    return _deduplicate(blockers), held, held_season


def _read_scenario_receipt_artifacts(
    value: object, root: Path, issue: datetime, rows: Sequence[HindcastRow], index: int,
    case_id: str, run_id: str,
) -> tuple[dict[str, AvailableRecord], dict[str, str]]:
    if not isinstance(value, dict):
        raise ValueError("scenario_receipt_artifacts must be an object")
    expected = {"water", "crop", "precip", "soil"}
    if set(value) != expected:
        raise ValueError("scenario_receipt_artifacts must contain water, crop, precip, and soil receipts")
    requires_scenarios = any(row.layer.startswith("eta_") for row in rows)
    records: dict[str, AvailableRecord] = {}
    hashes: dict[str, str] = {}
    for name in sorted(expected):
        payload, artifact_hash = _read_receipt_artifact(
            root, value[name], "idaho_outlook_hindcast_scenario_receipt", case_id, run_id,
            f"scenario receipt {name}",
        )
        _require_exact_keys(
            payload,
            {
                "schema_version", "kind", "case_id", "run_id", "name", "uri",
                "source_version", "sha256", "available_at",
            },
            f"scenario receipt {name}",
        )
        if payload["name"] != name:
            raise ValueError(f"scenario receipt {name} has the wrong name")
        receipt = _parse_record(payload)
        if receipt.available_at > issue:
            raise ValueError(f"case {index} scenario assumption {name} was available after issue_time")
        if requires_scenarios and not receipt.sha256:
            raise ValueError(f"case {index} scenario assumption {name} lacks immutable identity")
        records[name] = receipt
        hashes[name] = artifact_hash
    return records, hashes


def _read_evidence_file(root: Path, supplied: object, label: str) -> bytes:
    if not isinstance(supplied, str) or not supplied or Path(supplied).is_absolute():
        raise ValueError(f"{label} path must be a non-empty relative path")
    candidate = (root / supplied).resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} path escapes the evidence bundle") from error
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError(f"{label} must name a regular evidence file")
    return candidate.read_bytes()


def _read_receipt_artifact(
    root: Path, descriptor: object, kind: str, case_id: str, run_id: str, label: str,
) -> tuple[dict[str, object], str]:
    """Read a separately hashed receipt; inline declarations are never evidence."""
    _require_exact_keys(descriptor, {"path", "sha256"}, f"{label} descriptor")
    assert isinstance(descriptor, dict)
    content = _read_evidence_file(root, descriptor["path"], label)
    _require_digest(content, descriptor["sha256"], label)
    payload = _load_json_bytes(content, label)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    required_base = {
        "schema_version", "kind", "case_id", "run_id", "uri", "source_version", "sha256",
        "available_at",
    }
    if not required_base.issubset(payload):
        raise ValueError(f"{label} lacks immutable receipt fields")
    if payload.get("schema_version") != 1 or payload.get("kind") != kind:
        raise ValueError(f"{label} has an unsupported receipt schema")
    if payload.get("case_id") != case_id or payload.get("run_id") != run_id:
        raise ValueError(f"{label} does not link to its case and run")
    try:
        AvailableRecord(
            name=str(payload.get("name", kind)), uri=payload["uri"],
            source_version=payload["source_version"], sha256=payload["sha256"],
            available_at=_parse_utc(payload["available_at"], f"{label} available_at"),
        )
    except ValueError as error:
        raise ValueError(f"{label} has invalid immutable receipt fields: {error}") from error
    return payload, hashlib.sha256(content).hexdigest()


def _forecast_classification_blockers(forecast: dict[object, object], case_index: int) -> list[str]:
    """Treat every non-exact production/validated state as non-promotable."""
    fixture = forecast.get("fixture_non_scientific")
    publication = forecast.get("publication_classification")
    validation = forecast.get("validation_status")
    blockers: list[str] = []
    if type(fixture) is not bool:
        blockers.append(f"case {case_index} forecast fixture_non_scientific is missing or non-boolean")
    elif fixture:
        blockers.append(f"case {case_index} forecast is a software fixture")
    if publication != "production":
        blockers.append(f"case {case_index} forecast publication_classification is not production")
    if validation != "validated":
        blockers.append(f"case {case_index} forecast validation_status is not validated")
    return blockers


def _require_digest(content: bytes, supplied: object, label: str) -> None:
    if not isinstance(supplied, str) or len(supplied) != 64 or any(ch not in "0123456789abcdef" for ch in supplied):
        raise ValueError(f"{label} sha256 must be lowercase SHA-256 hex")
    if hashlib.sha256(content).hexdigest() != supplied:
        raise ValueError(f"{label} sha256 does not match artifact bytes")


def _load_json_bytes(content: bytes, label: str) -> object:
    try:
        return json.loads(content.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} must be valid duplicate-key-free UTF-8 JSON") from error


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = item
    return result


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _require_exact_keys(value: object, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} fields must match the schema exactly")


def _parse_real_provenance(value: object, *, required: bool) -> None:
    if not isinstance(value, dict):
        raise ValueError("evidence provenance must be an object")
    _require_exact_keys(value, {"uri", "version", "sha256", "available_at"}, "evidence provenance")
    try:
        record = AvailableRecord(
            name="evidence_provenance", uri=value["uri"], source_version=value["version"],
            sha256=value["sha256"], available_at=_parse_utc(value["available_at"], "provenance available_at"),
        )
    except ValueError as error:
        raise ValueError(f"evidence provenance is invalid: {error}") from error
    if required and (record.uri.startswith("https://example.") or record.source_version.lower() in {"fixture", "unknown"}):
        raise ValueError("real_archived evidence requires verified non-fixture provenance")


def _receipt_payload(receipt: EvaluationReceipt) -> dict[str, object]:
    payload = receipt.report.validation_record()
    payload.update({
        "schema_version": 3,
        "kind": "idaho_outlook_hindcast_evaluation_receipt",
        "evaluation_digest": receipt.evaluation_digest,
        "case_sha256": list(receipt.case_sha256),
        "promotion_attestation": receipt.attestation,
        "publication_authority": "externally_attested_ed25519_evaluation",
    })
    return payload


def _validate_evaluation_receipt(receipt: EvaluationReceipt) -> None:
    if not isinstance(receipt.evidence_path, Path):
        raise ValueError("evaluation receipt evidence path is invalid")
    if len(receipt.evaluation_digest) != 64 or any(ch not in "0123456789abcdef" for ch in receipt.evaluation_digest):
        raise ValueError("evaluation receipt digest is invalid")
    if len(receipt.case_sha256) != receipt.report.case_count:
        raise ValueError("evaluation receipt case hashes do not match the report")
    if any(len(item) != 64 or any(ch not in "0123456789abcdef" for ch in item) for item in receipt.case_sha256):
        raise ValueError("evaluation receipt case hash is invalid")
    if receipt.attestation is not None and not isinstance(receipt.attestation, dict):
        raise ValueError("evaluation receipt attestation is invalid")


def _with_blockers(report: HindcastReport, blockers: Iterable[str]) -> HindcastReport:
    """Return the same diagnostic aggregates with deduplicated gate failures."""
    return HindcastReport(
        metrics=report.metrics,
        source_latency=report.source_latency,
        input_audit=report.input_audit,
        case_count=report.case_count,
        fixture_non_scientific=report.fixture_non_scientific,
        fixture_reason=report.fixture_reason,
        promotion_blockers=tuple(_deduplicate([*report.promotion_blockers, *blockers])),
    )


def _report_sha256(report: HindcastReport) -> str:
    return hashlib.sha256(_canonical_json(report.validation_record()).encode("utf-8")).hexdigest()


def _verify_promotion_attestation(
    value: dict[str, object] | None, evaluation_digest: str, report: HindcastReport,
) -> str | None:
    """Return a gate failure or verify the attested content with the external key."""
    if not report.promotion:
        return "hindcast metrics or evidence gates did not qualify for promotion"
    if value is None:
        return "promotion requires an external attestation"
    expected = {"schema_version", "algorithm", "key_id", "evaluation_digest", "report_sha256", "signature"}
    if set(value) != expected:
        return "promotion attestation schema is invalid"
    if (
        value.get("schema_version") != 1
        or value.get("algorithm") != _PINNED_PROMOTION_AUTHORITY.algorithm
        or value.get("key_id") != _PINNED_PROMOTION_AUTHORITY.key_id
        or value.get("evaluation_digest") != evaluation_digest
        or value.get("report_sha256") != _report_sha256(report)
    ):
        return "promotion attestation does not bind the verified evaluation"
    signature_value = value.get("signature")
    if not isinstance(signature_value, str):
        return "promotion attestation signature is invalid"
    try:
        signature = base64.b64decode(signature_value, validate=True)
        Ed25519PublicKey.from_public_bytes(_PINNED_PROMOTION_AUTHORITY.public_key).verify(
            signature, _attestation_message(evaluation_digest, _report_sha256(report))
        )
    except (ValueError, TypeError, InvalidSignature):
        return "promotion attestation signature is invalid"
    return None


def _attestation_message(evaluation_digest: str, report_digest: str) -> bytes:
    """Return the fixed binary protocol that an external authority signs.

    The payload contains two 32-byte SHA-256 values and a versioned prefix;
    it never delegates protocol meaning to mutable JSON ``kind`` text.
    """
    if not _is_sha256(evaluation_digest) or not _is_sha256(report_digest):
        raise ValueError("attestation message requires SHA-256 digests")
    return _ATTESTATION_PROTOCOL + bytes.fromhex(evaluation_digest) + bytes.fromhex(report_digest)


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


# This is evaluated from a committed file when the verifier imports.  There is
# deliberately no environment variable, CLI option, or runtime key selection.
_PINNED_PROMOTION_AUTHORITY = _load_pinned_promotion_authority()


def _summarize_source_latency(
    audit: dict[str, list[tuple[AvailableRecord, datetime]]]
) -> tuple[SourceLatencySummary, ...]:
    result: list[SourceLatencySummary] = []
    for source_name, entries in sorted(audit.items()):
        late = [record for record, issue_time in entries if record.available_at > issue_time]
        eligible_age_days = [
            (issue_time - record.available_at).total_seconds() / 86400.0
            for record, issue_time in entries
            if record.available_at <= issue_time
        ]
        result.append(
            SourceLatencySummary(
                source_name=source_name,
                record_count=len(entries),
                late_record_count=len(late),
                max_latency_days=max(eligible_age_days) if eligible_age_days else None,
            )
        )
    return tuple(result)


def _write_new_bytes(destination: Path, encoded: bytes) -> Path:
    destination = Path(destination)
    parent = destination.parent
    if destination.name == "" or not parent.is_dir() or parent.is_symlink():
        raise ValueError("hindcast output parent must be an existing real directory")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(destination, flags, 0o644)
    except FileExistsError as error:
        raise ValueError(f"hindcast output already exists: {destination}") from error
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return destination


def _parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be strict UTC ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be strict UTC ISO-8601 text") from error
    return _require_strict_utc(parsed, label)


def _require_strict_utc(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is not timezone.utc:
        raise ValueError(f"{label} must be a strict UTC timestamp")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _finite_nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite non-negative number")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return number


def _deduplicate(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _metric_row(metric: HindcastMetric) -> str:
    return (
        f"| {metric.layer} | {metric.key} | {metric.sample_count} | "
        f"{_format_metric(metric.mae_mm)} | {_format_metric(metric.rmse_mm)} | "
        f"{_format_metric(metric.bias_mm)} | {_format_metric(metric.p10_p90_coverage)} | "
        f"{_format_metric(metric.mean_interval_width_mm)} |"
    )


def _format_metric(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def _receipt_record(record: AvailableRecord) -> dict[str, str]:
    return {
        "name": record.name,
        "available_at": _format_utc(record.available_at),
        "source_version": record.source_version,
        "sha256": record.sha256,
        "uri": record.uri,
    }


def _format_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
