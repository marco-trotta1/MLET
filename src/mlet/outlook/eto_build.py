"""Build the narrow ETo-only research-candidate artifact."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from mlet.outlook.contracts import SourceRecord, WeatherMember
from mlet.outlook.dates import outlook_valid_dates
from mlet.outlook.eto import summarize_member_groups
from mlet.outlook.eto_contract import VALIDATION_SCOPE, validate_eto_candidate_payload
from mlet.outlook.manifest import RunManifest, build_manifest_from_source_records
from mlet.sources.gefs import (
    GefsDailyArtifactSet,
    load_gefs_daily_members,
    resolve_gefs_daily_artifact,
)


def serialize_eto_outlook(
    members: Sequence[WeatherMember], manifest: RunManifest
) -> bytes:
    """Return canonical bytes for one nonfixture ETo research candidate."""
    if not isinstance(manifest, RunManifest):
        raise ValueError("ETo outlook requires a RunManifest")
    manifest.to_json()
    if not members or any(not isinstance(member, WeatherMember) for member in members):
        raise ValueError("ETo outlook requires WeatherMember values")
    issue_time = manifest.issued_at
    expected_dates = tuple(outlook_valid_dates(issue_time))
    if any(member.issued_at != issue_time for member in members):
        raise ValueError("ETo weather members must match manifest issued_at")
    summaries = summarize_member_groups(members)
    grid_ids = {member.grid_id for member in members}
    expected_keys = {
        (grid_id, valid_date)
        for grid_id in grid_ids
        for valid_date in expected_dates
    }
    if set(summaries) != expected_keys:
        raise ValueError("ETo weather members must cover every grid and lead day")
    locations = _grid_locations(members)
    collections = []
    for lead_day, valid_date in enumerate(expected_dates, start=1):
        features = []
        for grid_id in sorted(grid_ids):
            quantiles = summaries[(grid_id, valid_date)]
            latitude, longitude = locations[grid_id]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [longitude, latitude],
                    },
                    "properties": {
                        "grid_id": grid_id,
                        "valid_date": valid_date.isoformat(),
                        "lead_day": lead_day,
                        "layers": {
                            "eto_mm": {
                                "p10": quantiles.p10,
                                "p50": quantiles.p50,
                                "p90": quantiles.p90,
                            }
                        },
                    },
                }
            )
        collections.append(
            {
                "type": "FeatureCollection",
                "valid_date": valid_date.isoformat(),
                "lead_day": lead_day,
                "features": features,
            }
        )
    payload = {
        "schema_version": 1,
        "run_id": manifest.run_id,
        "issued_at": _format_utc(issue_time),
        "fixture_non_scientific": False,
        "production_status": "research_candidate",
        "promotion_status": "not_promoted",
        "validation_status": "evaluation_pending",
        "validation_scope": VALIDATION_SCOPE,
        "layers": {
            "eto_mm": {
                "units": "mm/day",
                "kind": "forecast_ensemble_quantiles",
                "validation_role": "formal_hindcast_target",
                "definition": "ASCE short-reference ET from weather-ensemble members.",
            }
        },
        "feature_collections": collections,
    }
    validate_eto_candidate_payload(
        payload,
        expected_run_id=manifest.run_id,
        expected_issued_at=issue_time,
    )
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def write_eto_outlook(
    members: Sequence[WeatherMember], manifest: RunManifest, destination: Path
) -> RunManifest:
    """Write one immutable ETo candidate and its hash-bound manifest.

    The caller supplies an existing empty directory. The function refuses to
    replace either artifact. A later archive assembler can publish this pair
    through a descriptor-anchored generation.
    """
    destination = Path(destination)
    if not destination.is_dir() or destination.is_symlink():
        raise ValueError("ETo outlook destination must be an existing real directory")
    outlook_path = destination / "outlook.json"
    manifest_path = destination / "manifest.json"
    if outlook_path.exists() or outlook_path.is_symlink() or manifest_path.exists() or manifest_path.is_symlink():
        raise ValueError("ETo outlook destination already contains an artifact")
    outlook_bytes = serialize_eto_outlook(members, manifest)
    completed = manifest.with_artifact_sha256(
        {"outlook.json": hashlib.sha256(outlook_bytes).hexdigest()}
    )
    _write_new_bytes(outlook_path, outlook_bytes)
    try:
        _write_new_bytes(manifest_path, (completed.to_json() + "\n").encode("utf-8"))
    except Exception:
        outlook_path.unlink(missing_ok=True)
        raise
    return completed


def build_eto_outlook_from_gefs(
    *,
    artifact_set: GefsDailyArtifactSet,
    git_revision: str,
    retrieved_at: str,
    destination: Path,
) -> RunManifest:
    """Build an ETo candidate directly from a verified GEFS daily generation.

    This bridge re-resolves the public GEFS pointer before it reads weather
    rows. The manifest identifies the archived upstream GRIB bytes, while the
    candidate and final manifest identify each other by output hash.
    """
    if not isinstance(artifact_set, GefsDailyArtifactSet):
        raise ValueError("ETo candidate requires a GefsDailyArtifactSet")
    verified = resolve_gefs_daily_artifact(artifact_set.pointer_path)
    if verified != artifact_set:
        raise ValueError("GEFS daily artifact changed before ETo candidate build")
    receipt = _read_gefs_receipt(verified.receipt_path)
    issue_time = _parse_utc_text(receipt["source_issue_at"], "GEFS source_issue_at")
    raw_sha256 = receipt.get("raw_sha256")
    uri = receipt.get("uri")
    if not isinstance(raw_sha256, str) or len(raw_sha256) != 64:
        raise ValueError("GEFS receipt must contain raw_sha256")
    if not isinstance(uri, str) or not uri.startswith("https://"):
        raise ValueError("GEFS receipt must contain an HTTPS source URI")
    retrieved = _parse_utc_text(retrieved_at, "retrieved_at")
    source = SourceRecord(
        name="gefs",
        uri=uri,
        retrieved_at=retrieved,
        sha256=raw_sha256,
        observed_through=None,
    )
    manifest = build_manifest_from_source_records(
        _format_utc(issue_time), (source,), git_revision, _format_utc(retrieved)
    )
    members = load_gefs_daily_members(verified)
    if any(member.issued_at != manifest.issued_at for member in members):
        raise ValueError("GEFS member issue time does not match its source receipt")
    return write_eto_outlook(members, manifest, destination)


def _grid_locations(members: Sequence[WeatherMember]) -> dict[str, tuple[float, float]]:
    locations: dict[str, tuple[float, float]] = {}
    for member in members:
        location = (member.latitude, member.longitude)
        previous = locations.setdefault(member.grid_id, location)
        if previous != location:
            raise ValueError("ETo weather members must retain one location per grid")
    return locations


def _write_new_bytes(destination: Path, contents: bytes) -> None:
    with destination.open("xb") as handle:
        handle.write(contents)


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("ETo outlook issued_at must be UTC")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_gefs_receipt(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("GEFS receipt must be readable UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("GEFS receipt must be a JSON object")
    return payload


def _parse_utc_text(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be explicit UTC ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError(f"{label} must be explicit UTC ISO-8601 text") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must be explicit UTC ISO-8601 text")
    return parsed.astimezone(timezone.utc)
