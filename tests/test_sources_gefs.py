"""Software-only tests for the imported GEFS daily-artifact boundary."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import socket
import stat

import pytest

from mlet.sources.gefs import (
    fetch_gefs,
    materialize_gefs_daily_artifact,
    normalize_gefs_rows,
    resolve_gefs_daily_artifact,
)


ISSUED_AT = "2026-07-16T00:00:00Z"
IDAHO_BBOX = (-117.25, 42.0, -111.0, 49.0)
VARIABLES = [
    "precip_mm",
    "solar_mj_m2_day",
    "tmax_c",
    "tmin_c",
    "vapor_pressure_kpa",
    "wind_m_s",
]


def _gefs_rows() -> list[dict[str, object]]:
    """Return synthetic, non-scientific rows for deterministic software tests."""
    rows: list[dict[str, object]] = []
    issue_date = date(2026, 7, 16)
    for member_index in range(3):
        for lead_day in range(1, 21):
            rows.append(
                {
                    "grid_id": "fixture-idaho-grid",
                    "latitude": 43.6,
                    "longitude": -116.2,
                    "elevation_m": 824.0,
                    "member_id": f"fixture-member-{member_index:02d}",
                    "valid_date": (issue_date + timedelta(days=lead_day)).isoformat(),
                    "tmax_c": 30.0 + member_index,
                    "tmin_c": 12.0 + member_index,
                    "vapor_pressure_kpa": 1.2,
                    "wind_m_s": 2.0,
                    "solar_mj_m2_day": 25.0,
                    "precip_mm": 0.5,
                }
            )
    return rows


def _normalized_bytes(rows: list[dict[str, object]]) -> bytes:
    payloads: list[dict[str, object]] = []
    for member in normalize_gefs_rows(rows, issued_at=ISSUED_AT):
        payload = asdict(member)
        payload["issued_at"] = ISSUED_AT
        payload["valid_date"] = member.valid_date.isoformat()
        payloads.append(payload)
    return "".join(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        for payload in payloads
    ).encode("utf-8")


def _write_daily_artifact(path: Path, rows: list[dict[str, object]]) -> bytes:
    normalized = _normalized_bytes(rows)
    artifact = {
        "artifact_type": "mlet.gefs.daily-artifact",
        "schema_version": 1,
        "provenance": {
            "idaho_bbox": list(IDAHO_BBOX),
            "source_issue_at": ISSUED_AT,
            "transform": {
                "name": "noaa-gefs-grib-to-daily-asce-input",
                "version": "1",
            },
            "upstream_raw_sha256": hashlib.sha256(b"fixture-grib-bytes").hexdigest(),
            "upstream_uri": "https://example.test/archived-gefs.grib2",
            "variables": VARIABLES,
        },
        "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
        "rows": rows,
    }
    artifact_bytes = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    path.write_bytes(artifact_bytes)
    return artifact_bytes


def _resolved_bytes(pointer: Path) -> tuple[bytes, bytes, bytes]:
    artifact_set = resolve_gefs_daily_artifact(pointer)
    return (
        artifact_set.raw_path.read_bytes(),
        artifact_set.normalized_path.read_bytes(),
        artifact_set.receipt_path.read_bytes(),
    )


def test_gefs_normalizer_requires_twenty_distinct_daily_leads() -> None:
    members = normalize_gefs_rows(_gefs_rows(), issued_at=ISSUED_AT)

    assert len(members) == 60
    for member_id in {member.member_id for member in members}:
        leads = {
            member.valid_date
            for member in members
            if member.grid_id == "fixture-idaho-grid" and member.member_id == member_id
        }
        assert len(leads) == 20


def test_gefs_normalizer_rejects_missing_required_radiation() -> None:
    rows = _gefs_rows()
    del rows[0]["solar_mj_m2_day"]

    with pytest.raises(ValueError, match="solar_mj_m2_day"):
        normalize_gefs_rows(rows, issued_at=ISSUED_AT)


def test_gefs_normalizer_rejects_duplicate_member_grid_day() -> None:
    rows = _gefs_rows()
    rows.append(rows[0].copy())

    with pytest.raises(ValueError, match="duplicate"):
        normalize_gefs_rows(rows, issued_at=ISSUED_AT)


def test_gefs_normalizer_rejects_missing_daily_lead_for_one_member() -> None:
    rows = _gefs_rows()
    rows.pop()

    with pytest.raises(ValueError, match="exactly 20 daily leads"):
        normalize_gefs_rows(rows, issued_at=ISSUED_AT)


def test_gefs_normalizer_rejects_non_finite_or_unsafe_weather_values() -> None:
    rows = _gefs_rows()
    rows[0]["wind_m_s"] = float("inf")

    with pytest.raises(ValueError, match="finite"):
        normalize_gefs_rows(rows, issued_at=ISSUED_AT)


def test_weather_fixture_is_conspicuously_non_scientific_and_complete() -> None:
    fixture_path = Path("examples/outlook/weather_members.jsonl")
    rows = [json.loads(line) for line in fixture_path.read_text().splitlines()]

    assert all(row["fixture_non_scientific"] is True for row in rows)
    assert len(normalize_gefs_rows(rows, issued_at=ISSUED_AT)) == 60


def test_fetch_gefs_refuses_live_grib_without_attempting_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempted = False

    def deny_network(*args: object, **kwargs: object) -> object:
        nonlocal attempted
        attempted = True
        raise AssertionError("network access must not be attempted")

    monkeypatch.setattr(socket, "create_connection", deny_network)

    with pytest.raises(NotImplementedError, match="GRIB decoder"):
        fetch_gefs(date(2026, 7, 16), IDAHO_BBOX, tmp_path / "weather.jsonl")

    assert attempted is False


def test_imported_daily_artifact_caches_exact_parsed_bytes_and_publishes_hashes(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "fixture.daily-artifact.json"
    artifact_bytes = _write_daily_artifact(artifact_path, _gefs_rows())
    pointer = tmp_path / "weather_members.gefs"

    output = materialize_gefs_daily_artifact(artifact_path, pointer)

    assert output == resolve_gefs_daily_artifact(pointer)
    assert output.pointer_path == pointer
    assert pointer.is_symlink()
    assert output.raw_path.parent == output.normalized_path.parent
    assert output.raw_path.parent == output.receipt_path.parent
    assert output.raw_path.is_relative_to(tmp_path / "data" / "cache")
    assert len(output.normalized_path.read_text().splitlines()) == 60
    receipt = json.loads(output.receipt_path.read_text())
    assert receipt["raw_sha256"] == hashlib.sha256(artifact_bytes).hexdigest()
    assert receipt["normalized_sha256"] == hashlib.sha256(
        output.normalized_path.read_bytes()
    ).hexdigest()
    assert receipt["upstream_raw_sha256"] == hashlib.sha256(b"fixture-grib-bytes").hexdigest()
    assert receipt["source_issue_at"] == ISSUED_AT
    assert receipt["idaho_bbox"] == list(IDAHO_BBOX)
    assert receipt["variables"] == VARIABLES
    assert receipt["artifact_schema_version"] == 1
    assert receipt["transform"] == {
        "name": "noaa-gefs-grib-to-daily-asce-input",
        "version": "1",
    }
    assert output.raw_path.read_bytes() == artifact_bytes
    for member_path in (
        output.raw_path,
        output.normalized_path,
        output.receipt_path,
    ):
        assert stat.S_IMODE(member_path.stat().st_mode) & (
            stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
        ) == 0


def test_new_cache_hierarchy_is_durably_linked_bottom_up_before_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_path = tmp_path / "fixture.daily-artifact.json"
    _write_daily_artifact(artifact_path, _gefs_rows())
    pointer = tmp_path / "weather_members.gefs"

    from mlet.sources import gefs

    original_fsync_directory = gefs._fsync_directory
    fsynced_directories: list[Path] = []

    def record_fsync(directory: Path) -> None:
        fsynced_directories.append(directory)
        original_fsync_directory(directory)

    monkeypatch.setattr("mlet.sources.gefs._fsync_directory", record_fsync)

    materialize_gefs_daily_artifact(artifact_path, pointer)

    cache_root = tmp_path / "data" / "cache" / "gefs-daily-artifacts"
    assert fsynced_directories[:6] == [
        tmp_path / "data",
        tmp_path,
        tmp_path / "data" / "cache",
        tmp_path / "data",
        cache_root,
        tmp_path / "data" / "cache",
    ]


@pytest.mark.parametrize(
    "durability_root",
    (Path("data"), Path("data") / "cache"),
)
def test_new_cache_root_fsync_failure_prevents_generation_and_pointer_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    durability_root: Path,
) -> None:
    artifact_path = tmp_path / "fixture.daily-artifact.json"
    _write_daily_artifact(artifact_path, _gefs_rows())
    pointer = tmp_path / "weather_members.gefs"

    from mlet.sources import gefs

    original_fsync_directory = gefs._fsync_directory
    failed = False

    def fail_new_root_fsync(directory: Path) -> None:
        nonlocal failed
        if directory == tmp_path / durability_root and not failed:
            failed = True
            raise OSError("injected cache-root fsync failure")
        original_fsync_directory(directory)

    monkeypatch.setattr("mlet.sources.gefs._fsync_directory", fail_new_root_fsync)

    with pytest.raises(OSError, match="cache-root fsync failure"):
        materialize_gefs_daily_artifact(artifact_path, pointer)

    assert failed is True
    assert pointer.is_symlink() is False
    assert not (tmp_path / "data" / "cache" / "gefs-daily-artifacts").exists()


def test_preexisting_cache_hierarchy_requires_no_creation_fsync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_root = tmp_path / "data" / "cache" / "gefs-daily-artifacts"
    cache_root.mkdir(parents=True)

    from mlet.sources import gefs

    fsynced_directories: list[Path] = []

    def record_fsync(directory: Path) -> None:
        fsynced_directories.append(directory)

    monkeypatch.setattr("mlet.sources.gefs._fsync_directory", record_fsync)

    assert gefs._prepare_cache_directory(tmp_path) == cache_root
    assert fsynced_directories == []


def test_read_only_member_metadata_is_fsynced_before_staging_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_path = tmp_path / "fixture.daily-artifact.json"
    _write_daily_artifact(artifact_path, _gefs_rows())
    pointer = tmp_path / "weather_members.gefs"

    from mlet.sources import gefs

    original_set_read_only = gefs._set_read_only
    original_fsync_file = gefs._fsync_file
    original_fsync_directory = gefs._fsync_directory
    events: list[tuple[str, str]] = []
    member_names = {
        "canonical-artifact.json",
        "weather_members.jsonl",
        "receipt.json",
    }

    def record_set_read_only(path: Path) -> None:
        events.append(("chmod", path.name))
        original_set_read_only(path)

    def record_fsync_file(path: Path) -> None:
        events.append(("fsync-file", path.name))
        original_fsync_file(path)

    def record_fsync_directory(directory: Path) -> None:
        if directory.name.startswith(".gefs-"):
            events.append(("fsync-directory", "staging"))
        original_fsync_directory(directory)

    monkeypatch.setattr("mlet.sources.gefs._set_read_only", record_set_read_only)
    monkeypatch.setattr("mlet.sources.gefs._fsync_file", record_fsync_file)
    monkeypatch.setattr("mlet.sources.gefs._fsync_directory", record_fsync_directory)

    materialize_gefs_daily_artifact(artifact_path, pointer)

    staging_fsync_index = events.index(("fsync-directory", "staging"))
    for member_name in member_names:
        chmod_index = events.index(("chmod", member_name))
        file_fsync_index = events.index(("fsync-file", member_name))
        assert chmod_index < file_fsync_index < staging_fsync_index


def test_member_fsync_failure_after_read_only_mode_prevents_pointer_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_path = tmp_path / "fixture.daily-artifact.json"
    _write_daily_artifact(artifact_path, _gefs_rows())
    pointer = tmp_path / "weather_members.gefs"

    from mlet.sources import gefs

    original_fsync_file = gefs._fsync_file
    failed = False

    def fail_receipt_fsync(path: Path) -> None:
        nonlocal failed
        if path.name == "receipt.json" and not failed:
            failed = True
            raise OSError("injected member fsync failure")
        original_fsync_file(path)

    monkeypatch.setattr("mlet.sources.gefs._fsync_file", fail_receipt_fsync)

    with pytest.raises(OSError, match="member fsync failure"):
        materialize_gefs_daily_artifact(artifact_path, pointer)

    assert failed is True
    assert pointer.is_symlink() is False
    assert not list((tmp_path / "data" / "cache" / "gefs-daily-artifacts").iterdir())


def test_imported_daily_artifact_rejects_mismatched_declared_normalized_hash(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "fixture.daily-artifact.json"
    _write_daily_artifact(artifact_path, _gefs_rows())
    payload = json.loads(artifact_path.read_text())
    payload["normalized_sha256"] = "0" * 64
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="normalized_sha256"):
        materialize_gefs_daily_artifact(artifact_path, tmp_path / "weather_members.gefs")


def test_materializer_rejects_a_symlinked_pointer_parent_before_writing(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "fixture.daily-artifact.json"
    _write_daily_artifact(artifact_path, _gefs_rows())
    controlled_parent = tmp_path / "controlled"
    controlled_parent.mkdir()
    unsafe_parent = tmp_path / "unsafe-parent"
    unsafe_parent.symlink_to(controlled_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="must not traverse symlinks"):
        materialize_gefs_daily_artifact(artifact_path, unsafe_parent / "weather_members.gefs")

    assert list(controlled_parent.iterdir()) == []


def test_imported_daily_artifact_has_no_visible_set_when_initial_pointer_publish_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_path = tmp_path / "fixture.daily-artifact.json"
    _write_daily_artifact(artifact_path, _gefs_rows())
    pointer = tmp_path / "weather_members.gefs"

    from mlet.sources import gefs

    original_replace = gefs.os.replace
    failed = False

    def fail_pointer_publish(source: Path | str, target: Path | str) -> None:
        nonlocal failed
        if Path(target) == pointer and not failed:
            failed = True
            raise OSError("injected pointer publication failure")
        original_replace(source, target)

    monkeypatch.setattr("mlet.sources.gefs.os.replace", fail_pointer_publish)

    with pytest.raises(OSError, match="injected pointer publication failure"):
        materialize_gefs_daily_artifact(artifact_path, pointer)

    assert failed is True
    assert not pointer.exists()
    assert pointer.is_symlink() is False
    with pytest.raises(ValueError, match="pointer"):
        resolve_gefs_daily_artifact(pointer)

    generations = list((tmp_path / "data" / "cache" / "gefs-daily-artifacts").iterdir())
    assert len(generations) == 1
    assert {entry.name for entry in generations[0].iterdir()} == {
        "canonical-artifact.json",
        "receipt.json",
        "weather_members.jsonl",
    }


def test_imported_daily_artifact_preserves_previous_completed_set_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_artifact = tmp_path / "first.daily-artifact.json"
    first_raw_bytes = _write_daily_artifact(first_artifact, _gefs_rows())
    pointer = tmp_path / "weather_members.gefs"
    first_set = materialize_gefs_daily_artifact(first_artifact, pointer)
    previous_raw, previous_normalized, previous_receipt = _resolved_bytes(pointer)
    assert previous_raw == first_raw_bytes

    revised_rows = _gefs_rows()
    revised_rows[0]["tmax_c"] = 31.5
    revised_artifact = tmp_path / "revised.daily-artifact.json"
    revised_raw_bytes = _write_daily_artifact(revised_artifact, revised_rows)

    from mlet.sources import gefs

    original_replace = gefs.os.replace
    failed = False

    def fail_pointer_publish(source: Path | str, target: Path | str) -> None:
        nonlocal failed
        if Path(target) == pointer and not failed:
            failed = True
            raise OSError("injected pointer publication failure")
        original_replace(source, target)

    monkeypatch.setattr("mlet.sources.gefs.os.replace", fail_pointer_publish)

    with pytest.raises(OSError, match="injected pointer publication failure"):
        materialize_gefs_daily_artifact(revised_artifact, pointer)

    assert failed is True
    assert _resolved_bytes(pointer) == (
        previous_raw,
        previous_normalized,
        previous_receipt,
    )
    assert json.loads(previous_receipt)["raw_sha256"] == hashlib.sha256(previous_raw).hexdigest()
    assert json.loads(previous_receipt)["normalized_sha256"] == hashlib.sha256(
        previous_normalized
    ).hexdigest()

    published_generations = list(
        (tmp_path / "data" / "cache" / "gefs-daily-artifacts").iterdir()
    )
    assert len(published_generations) == 2

    monkeypatch.setattr("mlet.sources.gefs.os.replace", original_replace)
    revised_set = materialize_gefs_daily_artifact(revised_artifact, pointer)
    assert revised_set.generation_id != first_set.generation_id
    assert _resolved_bytes(pointer)[0] == revised_raw_bytes
