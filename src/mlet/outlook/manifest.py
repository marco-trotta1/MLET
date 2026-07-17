"""Deterministic run receipts for the Idaho regional ET outlook."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Mapping

from mlet.outlook.contracts import SourceRecord


_SCHEMA_VERSION = 1


def _parse_utc_timestamp(value: str) -> datetime:
    """Parse a caller-supplied UTC timestamp without consulting a clock."""
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamps must be explicit UTC ISO-8601 values ending in Z")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("timestamps must be explicit UTC ISO-8601 values ending in Z") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("timestamps must be explicit UTC ISO-8601 values ending in Z")
    return parsed.astimezone(timezone.utc)


def _format_utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("timestamps must be explicit UTC ISO-8601 values ending in Z")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _source_payload(source: SourceRecord) -> dict[str, str | None]:
    return {
        "name": source.name,
        "uri": source.uri,
        "retrieved_at": _format_utc_timestamp(source.retrieved_at),
        "sha256": source.sha256,
        "observed_through": (
            source.observed_through.isoformat()
            if source.observed_through is not None
            else None
        ),
    }


@dataclass(frozen=True)
class RunManifest:
    """A content-addressed receipt for one forecast or hindcast run."""

    schema_version: int
    run_id: str
    issued_at: datetime
    retrieved_at: datetime
    git_revision: str
    sources: tuple[SourceRecord, ...]

    def _payload_without_run_id(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "issued_at": _format_utc_timestamp(self.issued_at),
            "retrieved_at": _format_utc_timestamp(self.retrieved_at),
            "git_revision": self.git_revision,
            "sources": [_source_payload(source) for source in self.sources],
        }

    def to_json(self) -> str:
        """Return canonical JSON suitable for an immutable run receipt."""
        payload = self._payload_without_run_id()
        payload["run_id"] = self.run_id
        return _canonical_json(payload)

    @classmethod
    def from_json(cls, value: str) -> RunManifest:
        """Restore and validate a receipt without deriving any system time."""
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("manifest must be valid JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("manifest must be a JSON object")

        try:
            source_payloads = payload["sources"]
            if not isinstance(source_payloads, list):
                raise TypeError("sources must be a list")
            sources = tuple(_source_from_payload(item) for item in source_payloads)
            manifest = cls(
                schema_version=_required_int(payload, "schema_version"),
                run_id=_required_str(payload, "run_id"),
                issued_at=_parse_utc_timestamp(_required_str(payload, "issued_at")),
                retrieved_at=_parse_utc_timestamp(_required_str(payload, "retrieved_at")),
                git_revision=_required_str(payload, "git_revision"),
                sources=sources,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("manifest does not satisfy the run receipt schema") from error

        if [source.name for source in sources] != sorted(source.name for source in sources):
            raise ValueError("manifest sources must be sorted by name")
        expected_run_id = _run_id(manifest._payload_without_run_id())
        if manifest.run_id != expected_run_id:
            raise ValueError("manifest run_id does not match its canonical content")
        return manifest


def build_manifest(
    issued_at: str,
    source_paths: Mapping[str, Path],
    git_revision: str,
    retrieved_at: str,
) -> RunManifest:
    """Build a deterministic receipt from caller-supplied times and input bytes."""
    issued_datetime = _parse_utc_timestamp(issued_at)
    retrieved_datetime = _parse_utc_timestamp(retrieved_at)
    if not isinstance(git_revision, str) or not git_revision:
        raise ValueError("git_revision must be a non-empty string")

    sources = tuple(
        SourceRecord(
            name=name,
            uri=path.resolve().as_uri(),
            retrieved_at=retrieved_datetime,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            observed_through=None,
        )
        for name, path in sorted(source_paths.items())
    )
    provisional = RunManifest(
        schema_version=_SCHEMA_VERSION,
        run_id="",
        issued_at=issued_datetime,
        retrieved_at=retrieved_datetime,
        git_revision=git_revision,
        sources=sources,
    )
    return RunManifest(
        schema_version=provisional.schema_version,
        run_id=_run_id(provisional._payload_without_run_id()),
        issued_at=provisional.issued_at,
        retrieved_at=provisional.retrieved_at,
        git_revision=provisional.git_revision,
        sources=provisional.sources,
    )


def _source_from_payload(value: object) -> SourceRecord:
    if not isinstance(value, dict):
        raise TypeError("source record must be an object")
    observed_through = value.get("observed_through")
    if observed_through is not None:
        if not isinstance(observed_through, str):
            raise TypeError("observed_through must be a date or null")
        observed_date = date.fromisoformat(observed_through)
    else:
        observed_date = None
    return SourceRecord(
        name=_required_str(value, "name"),
        uri=_required_str(value, "uri"),
        retrieved_at=_parse_utc_timestamp(_required_str(value, "retrieved_at")),
        sha256=_required_str(value, "sha256"),
        observed_through=observed_date,
    )


def _required_str(payload: Mapping[str, object], name: str) -> str:
    value = payload[name]
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _required_int(payload: Mapping[str, object], name: str) -> int:
    value = payload[name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    return value


def _run_id(payload_without_run_id: Mapping[str, object]) -> str:
    digest = hashlib.sha256(_canonical_json(payload_without_run_id).encode("utf-8"))
    return digest.hexdigest()[:16]
