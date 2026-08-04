"""Load strict indexes for archived GEFS reforecast issues."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class GefsReforecastIssue:
    """Immutable raw and normalized identities for one historical issue."""

    issue_time: datetime
    raw_uri: str
    raw_sha256: str
    daily_artifact_uri: str
    daily_artifact_sha256: str
    transform_version: str


def load_gefs_reforecast_catalog(path: Path) -> tuple[GefsReforecastIssue, ...]:
    """Load one deterministic, checksum-bound reforecast issue catalog."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("GEFS reforecast catalog must be readable UTF-8 JSON") from error
    _require_exact_keys(payload, {"schema_version", "kind", "issues"}, "GEFS catalog")
    assert isinstance(payload, dict)
    if payload["schema_version"] != 1 or payload["kind"] != "mlet.gefs.reforecast-catalog":
        raise ValueError("GEFS reforecast catalog has an unsupported schema")
    raw_issues = payload["issues"]
    if not isinstance(raw_issues, list) or not raw_issues:
        raise ValueError("GEFS reforecast catalog issues must be a non-empty list")
    issues = tuple(_parse_issue(value) for value in raw_issues)
    issue_times = [issue.issue_time for issue in issues]
    if issue_times != sorted(issue_times) or len(issue_times) != len(set(issue_times)):
        raise ValueError("GEFS reforecast catalog issue times must be sorted and unique; duplicate issue found")
    return issues


def _parse_issue(value: object) -> GefsReforecastIssue:
    _require_exact_keys(
        value,
        {
            "issue_time",
            "raw_uri",
            "raw_sha256",
            "daily_artifact_uri",
            "daily_artifact_sha256",
            "transform_version",
        },
        "GEFS catalog issue",
    )
    assert isinstance(value, dict)
    return GefsReforecastIssue(
        issue_time=_parse_utc(value["issue_time"]),
        raw_uri=_require_uri(value["raw_uri"]),
        raw_sha256=_require_sha256(value["raw_sha256"], "raw_sha256"),
        daily_artifact_uri=_require_uri(value["daily_artifact_uri"]),
        daily_artifact_sha256=_require_sha256(
            value["daily_artifact_sha256"], "daily_artifact_sha256"
        ),
        transform_version=_require_text(value["transform_version"], "transform_version"),
    )


def _require_exact_keys(value: object, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} fields must match the schema exactly")


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("GEFS issue_time must be strict UTC ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError("GEFS issue_time must be strict UTC ISO-8601 text") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("GEFS issue_time must be strict UTC ISO-8601 text")
    return parsed.astimezone(timezone.utc)


def _require_uri(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("GEFS catalog URI must be absolute")
    parsed = urlparse(value)
    if not parsed.scheme or (parsed.scheme != "file" and not parsed.netloc):
        raise ValueError("GEFS catalog URI must be absolute")
    return value


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label} must be lowercase SHA-256 hex")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value
