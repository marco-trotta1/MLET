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
import json
import math
import os
from pathlib import Path
from urllib.parse import urlparse


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
        if not isinstance(self.uri, str) or not parsed.scheme or not parsed.netloc:
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
    """Immutable evaluation results and the only promotion decision surface."""

    metrics: tuple[HindcastMetric, ...]
    source_latency: tuple[SourceLatencySummary, ...]
    input_audit: tuple[CaseInputAudit, ...]
    case_count: int
    fixture_non_scientific: bool
    fixture_reason: str | None
    promotion: bool
    promotion_blockers: tuple[str, ...]

    def validation_record(self) -> dict[str, object]:
        """Return the machine-readable release receipt consumed by publishers."""
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
    """Evaluate archived cases without converting a test fixture into evidence."""
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

    source_latency = _summarize_source_latency(source_audit)
    return HindcastReport(
        metrics=metrics,
        source_latency=source_latency,
        input_audit=tuple(input_audit),
        case_count=len(cases),
        fixture_non_scientific=fixture,
        fixture_reason=fixture_reason,
        promotion=not blockers,
        promotion_blockers=tuple(_deduplicate(blockers)),
    )


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


def write_hindcast_validation(report: HindcastReport, destination: Path) -> Path:
    """Write the unambiguous promotion receipt without silently overwriting it."""
    if not isinstance(report, HindcastReport):
        raise ValueError("hindcast validation requires a HindcastReport")
    encoded = (
        json.dumps(report.validation_record(), sort_keys=True, separators=(",", ":"), allow_nan=False)
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
