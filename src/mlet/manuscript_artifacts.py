"""Generate deterministic, claim-safe Phase 2 manuscript artifacts."""

from __future__ import annotations

import hashlib
import html
import json
import math
from pathlib import Path


_RESULT_FIELDS = {
    "schema_version",
    "kind",
    "evidence_status",
    "station_count",
    "provenance",
    "field_withheld",
    "h2",
}
_EVIDENCE_STATUS_TEXT = {
    "reproduced": (
        "Independent reproduction completed from the checksum-verified Phase 2 source archives."
    ),
    "historical_report_reproduction_pending": (
        "Historical report; independent reproduction is pending."
    ),
}
_ETO_RESULT_FIELDS = {
    "schema_version",
    "kind",
    "case_count",
    "target_count",
    "station_count",
    "evidence_sha256",
    "target_sources",
    "validation_scope",
    "completion_blockers",
    "bootstrap",
    "metrics",
}
_ETO_COMPLETE_RESULT_FIELDS = _ETO_RESULT_FIELDS | {
    "archive_sha256",
    "evaluation_sha256",
    "forecast_revisions",
    "source_versions",
    "exclusions",
    "support",
    "claim_safe_prose",
}
_ETO_LEGACY_RESULT_FIELDS = _ETO_RESULT_FIELDS - {"bootstrap"}
_ETO_METRIC_FIELDS = {
    "group",
    "key",
    "sample_count",
    "mae_mm",
    "rmse_mm",
    "bias_mm",
    "p10_p90_coverage",
    "mean_interval_width_mm",
    "mean_pinball_loss_mm",
    "baseline_mae_mm",
    "mae_improvement_mm",
    "mae_improvement_ci95_low_mm",
    "mae_improvement_ci95_high_mm",
    "bootstrap_cluster_count",
}
_ETO_LEGACY_METRIC_FIELDS = _ETO_METRIC_FIELDS - {
    "mae_improvement_ci95_low_mm",
    "mae_improvement_ci95_high_mm",
    "bootstrap_cluster_count",
}
_ETO_VALIDATION_SCOPE = {
    "formal_hindcast_layers": ["eto_mm"],
    "nonforecast_analysis_layers": ["eta_analysis_mm"],
    "unvalidated_projection_layers": [
        "potential_et_c_mm",
        "eta_well_watered_mm",
        "eta_no_irrigation_mm",
    ],
}


def build_phase2_artifacts(result_path: Path, destination: Path) -> None:
    """Create Markdown, CSV, and SVG only from one strict result record.

    The generator does not read network state, notebooks, clocks, or random
    state. It refuses to overwrite outputs so a reviewer can compare generated
    bytes with committed artifacts.
    """
    result = _load_result(Path(result_path))
    output_root = Path(destination)
    if not output_root.is_dir() or output_root.is_symlink():
        raise ValueError("manuscript artifact destination must be a real directory")
    models = _models(result)
    h2 = _h2(result)
    status = result["evidence_status"]
    assert isinstance(status, str)

    table_directory = output_root / "tables"
    figure_directory = output_root / "figures"
    _create_new_directory(table_directory)
    _create_new_directory(figure_directory)
    _write_new(
        table_directory / "phase2_model_comparison.csv", _csv_bytes(models)
    )
    _write_new(
        figure_directory / "phase2_model_comparison.svg", _svg_bytes(models)
    )
    _write_new(
        output_root / "phase2_openet_value.md",
        _markdown_bytes(
            models,
            h2,
            _EVIDENCE_STATUS_TEXT[status],
            int(result["station_count"]),
        ),
    )


def build_eto_hindcast_artifacts(result_path: Path, destination: Path) -> None:
    """Create deterministic ETo tables and figures from a complete result record.

    This function creates manuscript inputs only after the frozen evaluator
    reports no completion blocker. It does not turn the result into a promotion
    or a claim about conditional ETc or ETa layers.
    """
    result = _load_eto_hindcast_result(Path(result_path))
    output_root = Path(destination)
    if not output_root.is_dir() or output_root.is_symlink():
        raise ValueError("manuscript artifact destination must be a real directory")
    table_directory = _create_or_require_directory(output_root / "tables")
    figure_directory = _create_or_require_directory(output_root / "figures")
    lead_metrics = _metrics_for(result, "lead_day", tuple(str(index) for index in range(1, 21)))
    season_metrics = _metrics_for(result, "season", ("DJF", "MAM", "JJA", "SON"))
    spatial_metrics = _metrics_for(result, "spatial_fold", tuple(str(index) for index in range(5)))
    _write_new(table_directory / "eto_skill_by_lead.csv", _eto_csv_bytes(lead_metrics))
    _write_new(table_directory / "eto_skill_by_season.csv", _eto_csv_bytes(season_metrics))
    _write_new(
        table_directory / "eto_skill_by_spatial_fold.csv",
        _eto_csv_bytes(spatial_metrics),
    )
    _write_new(
        figure_directory / "eto_error_by_lead.svg",
        _line_svg_bytes(
            "ETo error by lead day",
            lead_metrics,
            (("MAE", "mae_mm", "#245d77"), ("RMSE", "rmse_mm", "#b04a3c")),
        ),
    )
    _write_new(
        figure_directory / "eto_coverage_by_lead.svg",
        _line_svg_bytes(
            "ETo p10-p90 coverage by lead day",
            lead_metrics,
            (("Coverage", "p10_p90_coverage", "#245d77"),),
        ),
    )
    _write_new(
        figure_directory / "eto_bias_by_season.svg",
        _bar_svg_bytes("ETo bias by season", season_metrics, "bias_mm"),
    )
    _write_new(
        output_root / "idaho_eto_hindcast.md",
        _eto_markdown_bytes(result, lead_metrics, season_metrics, spatial_metrics),
    )


def _load_eto_hindcast_result(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicates)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("ETo hindcast result must be duplicate-key-free UTF-8 JSON") from error
    if not isinstance(payload, dict) or set(payload) not in (
        _ETO_COMPLETE_RESULT_FIELDS,
        _ETO_RESULT_FIELDS,
        _ETO_LEGACY_RESULT_FIELDS,
    ):
        raise ValueError("ETo hindcast result fields must match the schema exactly")
    if payload["schema_version"] != 1 or payload["kind"] != "idaho_eto_hindcast_result":
        raise ValueError("ETo hindcast result has an unsupported schema")
    for name in ("case_count", "target_count", "station_count"):
        if type(payload[name]) is not int or payload[name] < 1:
            raise ValueError(f"ETo hindcast result {name} must be a positive integer")
    if not _is_digest(payload["evidence_sha256"]):
        raise ValueError("ETo hindcast result must contain an evidence SHA-256")
    if payload["validation_scope"] != _ETO_VALIDATION_SCOPE:
        raise ValueError("ETo hindcast result must retain the frozen validation scope")
    blockers = payload["completion_blockers"]
    if not isinstance(blockers, list) or any(not isinstance(item, str) for item in blockers):
        raise ValueError("ETo hindcast completion_blockers must be a text list")
    if blockers:
        raise ValueError("ETo hindcast result is incomplete and cannot make manuscript artifacts")
    if set(payload) in (_ETO_COMPLETE_RESULT_FIELDS, _ETO_RESULT_FIELDS):
        _validate_bootstrap(payload["bootstrap"])
    if set(payload) == _ETO_COMPLETE_RESULT_FIELDS:
        _validate_eto_provenance(payload)
    target_sources = payload["target_sources"]
    if not isinstance(target_sources, list) or not target_sources:
        raise ValueError("ETo hindcast target_sources must be a non-empty list")
    for source in target_sources:
        if not isinstance(source, dict) or set(source) != {"uri", "source_version"}:
            raise ValueError("ETo hindcast target source fields must match the schema exactly")
        if not isinstance(source["uri"], str) or not source["uri"]:
            raise ValueError("ETo hindcast target source URI must be non-empty text")
        if not isinstance(source["source_version"], str) or not source["source_version"]:
            raise ValueError("ETo hindcast target source version must be non-empty text")
    _validate_eto_metrics(payload["metrics"])
    return payload


def _validate_eto_provenance(payload: dict[str, object]) -> None:
    for name in ("archive_sha256", "evaluation_sha256"):
        if not _is_digest(payload[name]):
            raise ValueError(f"ETo hindcast {name} must be a SHA-256 digest")
    if payload["archive_sha256"] != payload["evidence_sha256"]:
        raise ValueError("ETo hindcast archive_sha256 must match evidence_sha256")
    revisions = payload["forecast_revisions"]
    if not isinstance(revisions, list) or not revisions or any(
        not isinstance(item, str) or not item for item in revisions
    ):
        raise ValueError("ETo hindcast forecast_revisions must be a non-empty text list")
    source_versions = payload["source_versions"]
    if not isinstance(source_versions, list) or not source_versions:
        raise ValueError("ETo hindcast source_versions must be a non-empty list")
    for source in source_versions:
        if not isinstance(source, dict) or set(source) != {"uri", "source_version"}:
            raise ValueError("ETo hindcast source version fields must match the schema exactly")
        if not isinstance(source["uri"], str) or not source["uri"]:
            raise ValueError("ETo hindcast source version URI must be non-empty text")
        if not isinstance(source["source_version"], str) or not source["source_version"]:
            raise ValueError("ETo hindcast source version must be non-empty text")
    if source_versions != payload["target_sources"]:
        raise ValueError("ETo hindcast source_versions must match target_sources")
    exclusions = payload["exclusions"]
    if not isinstance(exclusions, list):
        raise ValueError("ETo hindcast exclusions must be a list")
    for exclusion in exclusions:
        if not isinstance(exclusion, dict) or set(exclusion) != {
            "case_id",
            "target_id",
            "valid_date",
            "reason",
        }:
            raise ValueError("ETo hindcast exclusion fields must match the schema exactly")
        if any(
            not isinstance(exclusion[name], str) or not exclusion[name]
            for name in ("case_id", "target_id", "valid_date", "reason")
        ):
            raise ValueError("ETo hindcast exclusions must contain non-empty text")
    support = payload["support"]
    if not isinstance(support, dict) or set(support) != {
        "minimum_paired_targets",
        "cell_count",
        "cells",
    }:
        raise ValueError("ETo hindcast support fields must match the schema exactly")
    if type(support["minimum_paired_targets"]) is not int or support["minimum_paired_targets"] < 1:
        raise ValueError("ETo hindcast support minimum must be positive")
    if support["cell_count"] != 400:
        raise ValueError("ETo hindcast support must contain 400 lead-season-fold cells")
    cells = support["cells"]
    if not isinstance(cells, list) or len(cells) != 400:
        raise ValueError("ETo hindcast support cells must contain 400 entries")
    identities = set()
    for cell in cells:
        if not isinstance(cell, dict) or set(cell) != {
            "lead_day",
            "season",
            "spatial_fold",
            "sample_count",
            "minimum_required",
            "supported",
        }:
            raise ValueError("ETo hindcast support cell fields must match the schema exactly")
        if type(cell["lead_day"]) is not int or cell["lead_day"] not in range(1, 21):
            raise ValueError("ETo hindcast support lead_day is invalid")
        if cell["season"] not in {"DJF", "MAM", "JJA", "SON"}:
            raise ValueError("ETo hindcast support season is invalid")
        if type(cell["spatial_fold"]) is not int or cell["spatial_fold"] not in range(5):
            raise ValueError("ETo hindcast support spatial_fold is invalid")
        if type(cell["sample_count"]) is not int or cell["sample_count"] < 0:
            raise ValueError("ETo hindcast support sample_count is invalid")
        if cell["minimum_required"] != support["minimum_paired_targets"]:
            raise ValueError("ETo hindcast support minimums must agree")
        if type(cell["supported"]) is not bool:
            raise ValueError("ETo hindcast support supported flag must be boolean")
        identity = (cell["lead_day"], cell["season"], cell["spatial_fold"])
        if identity in identities:
            raise ValueError("ETo hindcast support cells must be unique")
        identities.add(identity)
        if cell["supported"] != (
            cell["sample_count"] >= cell["minimum_required"]
        ):
            raise ValueError("ETo hindcast support supported flag is inconsistent")
    expected_identities = {
        (lead_day, season, fold)
        for lead_day in range(1, 21)
        for season in ("DJF", "MAM", "JJA", "SON")
        for fold in range(5)
    }
    if identities != expected_identities:
        raise ValueError("ETo hindcast support cells must cover every lead, season, and fold")
    prose = payload["claim_safe_prose"]
    if not isinstance(prose, dict) or set(prose) != {
        "scope",
        "completion",
        "skill",
        "promotion",
    }:
        raise ValueError("ETo hindcast claim_safe_prose fields must match the schema exactly")
    if any(not isinstance(value, str) or not value for value in prose.values()):
        raise ValueError("ETo hindcast claim_safe_prose values must be non-empty text")
    expected_digest = _eto_evaluation_digest(payload)
    if payload["evaluation_sha256"] != expected_digest:
        raise ValueError("ETo hindcast evaluation_sha256 does not match the result record")


def _eto_evaluation_digest(payload: dict[str, object]) -> str:
    material = {
        "archive_sha256": payload["archive_sha256"],
        "case_count": payload["case_count"],
        "target_count": payload["target_count"],
        "station_count": payload["station_count"],
        "target_sources": payload["target_sources"],
        "forecast_revisions": payload["forecast_revisions"],
        "exclusions": payload["exclusions"],
        "validation_scope": payload["validation_scope"],
        "completion_blockers": payload["completion_blockers"],
        "bootstrap": payload["bootstrap"],
        "metrics": payload["metrics"],
    }
    encoded = (
        json.dumps(material, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_eto_metrics(value: object) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("ETo hindcast metrics must be a non-empty list")
    seen = set()
    for metric in value:
        if not isinstance(metric, dict) or (
            set(metric) != _ETO_METRIC_FIELDS
            and set(metric) != _ETO_LEGACY_METRIC_FIELDS
        ):
            raise ValueError("ETo hindcast metric fields must match the schema exactly")
        group = metric["group"]
        key = metric["key"]
        if not isinstance(group, str) or not group or not isinstance(key, str) or not key:
            raise ValueError("ETo hindcast metric group and key must be non-empty text")
        identity = (group, key)
        if identity in seen:
            raise ValueError("ETo hindcast metrics must not duplicate group and key")
        seen.add(identity)
        if type(metric["sample_count"]) is not int or metric["sample_count"] < 1:
            raise ValueError("ETo hindcast metric sample_count must be positive")
        metric_fields = set(metric)
        for name in metric_fields - {
            "group",
            "key",
            "sample_count",
            "bootstrap_cluster_count",
            "mae_improvement_ci95_low_mm",
            "mae_improvement_ci95_high_mm",
        }:
            if type(metric[name]) not in (int, float) or not math.isfinite(float(metric[name])):
                raise ValueError(f"ETo hindcast metric {name} must be finite")
        if "bootstrap_cluster_count" in metric:
            if type(metric["bootstrap_cluster_count"]) is not int or metric["bootstrap_cluster_count"] < 1:
                raise ValueError("ETo hindcast bootstrap_cluster_count must be positive")
        for name in ("mae_improvement_ci95_low_mm", "mae_improvement_ci95_high_mm"):
            if name in metric and metric[name] is not None and (
                type(metric[name]) not in (int, float)
                or not math.isfinite(float(metric[name]))
            ):
                raise ValueError(f"ETo hindcast {name} must be finite or null")
        if not 0.0 <= float(metric["p10_p90_coverage"]) <= 1.0:
            raise ValueError("ETo hindcast coverage must be in [0, 1]")


def _validate_bootstrap(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {"seed", "replicates", "cluster_definition"}:
        raise ValueError("ETo hindcast bootstrap fields must match the schema exactly")
    if type(value["seed"]) is not int:
        raise ValueError("ETo hindcast bootstrap seed must be an integer")
    if type(value["replicates"]) is not int or value["replicates"] < 1:
        raise ValueError("ETo hindcast bootstrap replicates must be positive")
    if value["cluster_definition"] != "issue_date,target_id":
        raise ValueError("ETo hindcast bootstrap cluster definition is unsupported")


def _metrics_for(
    result: dict[str, object],
    group: str,
    expected_keys: tuple[str, ...],
) -> list[dict[str, object]]:
    raw_metrics = result["metrics"]
    assert isinstance(raw_metrics, list)
    by_key = {
        metric["key"]: metric
        for metric in raw_metrics
        if isinstance(metric, dict) and metric["group"] == group
    }
    if set(by_key) != set(expected_keys):
        raise ValueError(f"ETo hindcast result must contain every {group} metric")
    return [by_key[key] for key in expected_keys]


def _eto_csv_bytes(metrics: list[dict[str, object]]) -> bytes:
    columns = (
        "key,sample_count,mae_mm,rmse_mm,bias_mm,p10_p90_coverage,"
        "mean_interval_width_mm,mean_pinball_loss_mm,baseline_mae_mm,"
        "mae_improvement_mm,mae_improvement_ci95_low_mm,"
        "mae_improvement_ci95_high_mm,bootstrap_cluster_count\n"
    )
    lines = [columns]
    for metric in metrics:
        lines.append(
            f"{metric['key']},{metric['sample_count']},{float(metric['mae_mm']):.6f},"
            f"{float(metric['rmse_mm']):.6f},{float(metric['bias_mm']):.6f},"
            f"{float(metric['p10_p90_coverage']):.6f},"
            f"{float(metric['mean_interval_width_mm']):.6f},"
            f"{float(metric['mean_pinball_loss_mm']):.6f},"
            f"{float(metric['baseline_mae_mm']):.6f},"
            f"{float(metric['mae_improvement_mm']):.6f},"
            f"{_format_optional_float(metric.get('mae_improvement_ci95_low_mm'))},"
            f"{_format_optional_float(metric.get('mae_improvement_ci95_high_mm'))},"
            f"{metric.get('bootstrap_cluster_count', '')}\n"
        )
    return "".join(lines).encode("utf-8")


def _eto_markdown_bytes(
    result: dict[str, object],
    lead_metrics: list[dict[str, object]],
    season_metrics: list[dict[str, object]],
    spatial_metrics: list[dict[str, object]],
) -> bytes:
    lines = [
        "# Idaho ETo hindcast results",
        "",
        "This result evaluates weather-driven reference ETo only.",
        "It does not validate ETc or ETa conditional projections.",
        "",
        f"Historical issue cases: {result['case_count']}",
        f"Paired station-day targets: {result['target_count']}",
        f"Stations: {result['station_count']}",
        "",
        "## Skill by lead day",
        "",
        "| lead day | n | MAE (mm/day) | RMSE (mm/day) | bias (mm/day) | coverage | width (mm/day) | pinball loss (mm/day) | baseline MAE (mm/day) | MAE improvement (mm/day) | paired 95% CI (mm/day) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(_metric_markdown_row(metric) for metric in lead_metrics)
    lines.extend(["", "## Skill by season", ""])
    lines.extend(_compact_metric_table(season_metrics))
    lines.extend(["", "## Skill by spatial block", ""])
    lines.extend(_compact_metric_table(spatial_metrics))
    lines.extend(
        [
            "",
            "The baseline is station and day-of-year climatology.",
            "The paired bootstrap resamples issue-date and station clusters.",
            "This result reports measured performance. It does not make a promotion decision.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def _metric_markdown_row(metric: dict[str, object]) -> str:
    return (
        f"| {metric['key']} | {metric['sample_count']} | {float(metric['mae_mm']):.3f} | "
        f"{float(metric['rmse_mm']):.3f} | {float(metric['bias_mm']):.3f} | "
        f"{float(metric['p10_p90_coverage']):.3f} | "
        f"{float(metric['mean_interval_width_mm']):.3f} | "
        f"{float(metric['mean_pinball_loss_mm']):.3f} | "
        f"{float(metric['baseline_mae_mm']):.3f} | "
        f"{float(metric['mae_improvement_mm']):.3f} | "
        f"{_format_ci(metric.get('mae_improvement_ci95_low_mm'), metric.get('mae_improvement_ci95_high_mm'))} |"
    )


def _compact_metric_table(metrics: list[dict[str, object]]) -> list[str]:
    lines = [
        "| group | n | MAE (mm/day) | bias (mm/day) | coverage | MAE improvement (mm/day) | paired 95% CI (mm/day) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(
        f"| {metric['key']} | {metric['sample_count']} | {float(metric['mae_mm']):.3f} | "
        f"{float(metric['bias_mm']):.3f} | {float(metric['p10_p90_coverage']):.3f} | "
        f"{float(metric['mae_improvement_mm']):.3f} | "
        f"{_format_ci(metric.get('mae_improvement_ci95_low_mm'), metric.get('mae_improvement_ci95_high_mm'))} |"
        for metric in metrics
    )
    return lines


def _format_optional_float(value: object) -> str:
    if value is None:
        return ""
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ValueError("optional ETo metric value must be finite or null")
    return f"{float(value):.6f}"


def _format_ci(low: object, high: object) -> str:
    if low is None or high is None:
        return "n/a"
    return f"[{_format_optional_float(low)}, {_format_optional_float(high)}]"


def _line_svg_bytes(
    title: str,
    metrics: list[dict[str, object]],
    series: tuple[tuple[str, str, str], ...],
) -> bytes:
    width = 720
    height = 320
    left = 56
    right = 24
    top = 36
    bottom = 44
    values = [float(metric[field]) for _, field, _ in series for metric in metrics]
    minimum = min(0.0, min(values))
    maximum = max(values)
    span = maximum - minimum or 1.0
    points = []
    labels = []
    for series_index, (name, field, color) in enumerate(series):
        coordinates = []
        for index, metric in enumerate(metrics):
            x = left + index * (width - left - right) / max(1, len(metrics) - 1)
            y = top + (maximum - float(metric[field])) * (height - top - bottom) / span
            coordinates.append(f"{x:.2f},{y:.2f}")
            if series_index == 0:
                labels.append(
                    f'<text x="{x:.2f}" y="{height - 18}" text-anchor="middle">{html.escape(str(metric["key"]))}</text>'
                )
        points.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{" ".join(coordinates)}"/>'
            f'<text x="{left + series_index * 170}" y="{20}" fill="{color}">{html.escape(name)}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><title>{html.escape(title)}</title>'
        '<style>text{font-family:Arial,sans-serif;font-size:11px}</style>'
        f'<text x="{left}" y="{top - 12}">{html.escape(title)}</text>'
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#000"/>'
        + "".join(points)
        + "".join(labels)
        + "</svg>\n"
    ).encode("utf-8")


def _bar_svg_bytes(title: str, metrics: list[dict[str, object]], field: str) -> bytes:
    width = 720
    height = 320
    left = 56
    right = 24
    top = 36
    bottom = 44
    values = [float(metric[field]) for metric in metrics]
    maximum = max(0.0, max(values))
    minimum = min(0.0, min(values))
    span = maximum - minimum or 1.0
    zero_y = top + maximum * (height - top - bottom) / span
    bar_width = (width - left - right) / len(metrics) * 0.6
    bars = []
    for index, metric in enumerate(metrics):
        center = left + (index + 0.5) * (width - left - right) / len(metrics)
        value_y = top + (maximum - float(metric[field])) * (height - top - bottom) / span
        y = min(value_y, zero_y)
        bar_height = abs(zero_y - value_y)
        color = "#245d77" if float(metric[field]) >= 0.0 else "#b04a3c"
        bars.extend(
            [
                f'<rect x="{center - bar_width / 2:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{bar_height:.2f}" fill="{color}"/>',
                f'<text x="{center:.2f}" y="{height - 18}" text-anchor="middle">{html.escape(str(metric["key"]))}</text>',
            ]
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><title>{html.escape(title)}</title>'
        '<style>text{font-family:Arial,sans-serif;font-size:11px}</style>'
        f'<text x="{left}" y="{top - 12}">{html.escape(title)}</text>'
        f'<line x1="{left}" y1="{zero_y:.2f}" x2="{width - right}" y2="{zero_y:.2f}" stroke="#000"/>'
        + "".join(bars)
        + "</svg>\n"
    ).encode("utf-8")


def _load_result(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicates)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("Phase 2 result must be duplicate-key-free UTF-8 JSON") from error
    if not isinstance(payload, dict) or set(payload) != _RESULT_FIELDS:
        raise ValueError("Phase 2 result fields must match the schema exactly")
    if payload["schema_version"] != 1 or payload["kind"] != "mlet.phase2-openet-value-result":
        raise ValueError("Phase 2 result has an unsupported schema")
    if payload["evidence_status"] not in _EVIDENCE_STATUS_TEXT:
        raise ValueError("Phase 2 result evidence_status is unsupported")
    if type(payload["station_count"]) is not int or payload["station_count"] < 1:
        raise ValueError("Phase 2 result station_count must be a positive integer")
    provenance = payload["provenance"]
    if not isinstance(provenance, dict) or set(provenance) != {
        "data_manifest_sha256", "git_revision", "seed"
    }:
        raise ValueError("Phase 2 provenance fields must match the schema exactly")
    if not _is_digest(provenance["data_manifest_sha256"]):
        raise ValueError("Phase 2 provenance must contain a SHA-256 data manifest")
    if not isinstance(provenance["git_revision"], str) or not provenance["git_revision"]:
        raise ValueError("Phase 2 provenance must contain a git revision")
    if type(provenance["seed"]) is not int:
        raise ValueError("Phase 2 provenance seed must be an integer")
    return payload


def _models(result: dict[str, object]) -> list[dict[str, object]]:
    field_withheld = result["field_withheld"]
    if not isinstance(field_withheld, dict) or set(field_withheld) != {"models"}:
        raise ValueError("Phase 2 field_withheld fields must match the schema exactly")
    values = field_withheld["models"]
    if not isinstance(values, list) or not values:
        raise ValueError("Phase 2 field_withheld models must be a non-empty list")
    expected = {"name", "mae_mm", "rmse_mm", "bias_mm", "sample_count"}
    models = []
    names: set[str] = set()
    for value in values:
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("Phase 2 model fields must match the schema exactly")
        name = value["name"]
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("Phase 2 model names must be unique non-empty text")
        names.add(name)
        for field in ("mae_mm", "rmse_mm", "bias_mm"):
            if type(value[field]) not in (int, float) or not math.isfinite(float(value[field])):
                raise ValueError(f"Phase 2 {field} must be finite")
        if type(value["sample_count"]) is not int or value["sample_count"] < 1:
            raise ValueError("Phase 2 sample_count must be a positive integer")
        models.append(value)
    return sorted(models, key=lambda model: str(model["name"]))


def _h2(result: dict[str, object]) -> dict[str, object]:
    h2 = result["h2"]
    expected = {
        "best_openet_free_model",
        "mae_reduction_fraction",
        "mae_delta_mm",
        "ci95_mm",
    }
    if not isinstance(h2, dict) or set(h2) != expected:
        raise ValueError("Phase 2 H2 fields must match the schema exactly")
    if not isinstance(h2["best_openet_free_model"], str):
        raise ValueError("Phase 2 H2 best model must be text")
    for field in ("mae_reduction_fraction", "mae_delta_mm"):
        if type(h2[field]) not in (int, float) or not math.isfinite(float(h2[field])):
            raise ValueError(f"Phase 2 H2 {field} must be finite")
    ci = h2["ci95_mm"]
    if (
        not isinstance(ci, list)
        or len(ci) != 2
        or any(type(value) not in (int, float) or not math.isfinite(float(value)) for value in ci)
        or float(ci[0]) > float(ci[1])
    ):
        raise ValueError("Phase 2 H2 ci95_mm must contain two ordered finite values")
    return h2


def _csv_bytes(models: list[dict[str, object]]) -> bytes:
    lines = ["model,mae_mm,rmse_mm,bias_mm,sample_count\n"]
    for model in models:
        lines.append(
            f"{model['name']},{float(model['mae_mm']):.3f},"
            f"{float(model['rmse_mm']):.3f},{float(model['bias_mm']):.3f},"
            f"{model['sample_count']}\n"
        )
    return "".join(lines).encode("utf-8")


def _markdown_bytes(
    models: list[dict[str, object]],
    h2: dict[str, object],
    status_text: str,
    station_count: int,
) -> bytes:
    lines = [
        "# Phase 2 — OpenET-value results",
        "",
        status_text,
        "",
        "## Station-held-out model comparison",
        "",
        f"Station count: {station_count}",
        "",
        "| model | MAE (mm/day) | RMSE (mm/day) | bias (mm/day) | n |",
        "|---|---:|---:|---:|---:|",
    ]
    for model in models:
        lines.append(
            f"| {model['name']} | {float(model['mae_mm']):.3f} | "
            f"{float(model['rmse_mm']):.3f} | {float(model['bias_mm']):.3f} | "
            f"{model['sample_count']} |"
        )
    lines.extend(
        [
            "",
            "## OpenET value comparison",
            "",
            f"Best OpenET-free model: {h2['best_openet_free_model']}",
            f"MAE reduction: {100.0 * float(h2['mae_reduction_fraction']):.1f}%",
            f"MAE delta: {float(h2['mae_delta_mm']):.3f} mm/day; "
            f"95% CI [{float(h2['ci95_mm'][0]):.3f}, {float(h2['ci95_mm'][1]):.3f}] mm/day.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def _svg_bytes(models: list[dict[str, object]]) -> bytes:
    maximum = max(float(model["mae_mm"]) for model in models)
    scale = 460.0 / maximum if maximum else 0.0
    rows = []
    for index, model in enumerate(models):
        y = 48 + index * 32
        width = float(model["mae_mm"]) * scale
        label = html.escape(str(model["name"]), quote=True)
        rows.extend(
            [
                f'<text x="10" y="{y + 15}">{label}</text>',
                f'<rect x="180" y="{y}" width="{width:.3f}" height="20" fill="#245d77"/>',
                f'<text x="{190 + width:.3f}" y="{y + 15}">{float(model["mae_mm"]):.3f}</text>',
            ]
        )
    height = 64 + len(models) * 32
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="700" height="{height}" '
        'viewBox="0 0 700 '
        f'{height}"><title>Phase 2 field-withheld MAE</title><style>'
        'text{font-family:Arial,sans-serif;font-size:12px}</style>'
        '<text x="10" y="20">Field-withheld MAE (mm/day)</text>'
        + "".join(rows)
        + "</svg>\n"
    ).encode("utf-8")


def _create_new_directory(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("manuscript artifact output directory already exists")
    path.mkdir()


def _create_or_require_directory(path: Path) -> Path:
    if path.is_symlink():
        raise ValueError("manuscript artifact output directory must not be a symlink")
    if path.exists():
        if not path.is_dir():
            raise ValueError("manuscript artifact output path must be a directory")
        return path
    path.mkdir()
    return path


def _write_new(path: Path, contents: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("manuscript artifact output already exists")
    with path.open("xb") as handle:
        handle.write(contents)


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result
