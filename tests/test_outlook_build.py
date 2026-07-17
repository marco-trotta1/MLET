"""Software-only integration checks for the immutable outlook artifact."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from mlet.cli import main
from mlet.outlook.build import build_outlook
from mlet.outlook.manifest import RunManifest


WEATHER_FIXTURE = Path("examples/outlook/weather_members.jsonl")
STATE_FIXTURE = Path("examples/outlook/state.jsonl")
CROP_FIXTURE = Path("examples/outlook/crop_grid.jsonl")


def test_build_outlook_writes_twenty_days_for_each_fixture_cell(tmp_path: Path) -> None:
    result = build_outlook(
        weather_path=WEATHER_FIXTURE,
        state_path=STATE_FIXTURE,
        crop_path=CROP_FIXTURE,
        out_dir=tmp_path,
    )

    assert result.day_count == 20
    payload = json.loads((tmp_path / result.run_id / "outlook.json").read_text())
    assert {
        "eto_mm",
        "potential_et_c_mm",
        "eta_well_watered_mm",
        "eta_no_irrigation_mm",
    } <= payload["layers"].keys()
    assert "actual_et_forecast" not in payload["layers"]
    first_feature = payload["feature_collections"][0]["features"][0]
    assert first_feature["properties"]["layers"]["eta_no_irrigation_mm"] is None

    run_dir = tmp_path / result.run_id
    assert {path.name for path in run_dir.iterdir()} == {
        "manifest.json",
        "outlook.json",
        "summary.json",
        "validation.json",
    }
    manifest = RunManifest.from_json((run_dir / "manifest.json").read_text())
    assert manifest.run_id == result.run_id
    assert all(
        hashlib.sha256((run_dir / filename).read_bytes()).hexdigest() == digest
        for filename, digest in manifest.artifact_sha256
    )


def test_build_outlook_cli_prints_immutable_run_location(
    tmp_path: Path, capsys
) -> None:
    assert (
        main(
            [
                "build-outlook",
                "--weather",
                str(WEATHER_FIXTURE),
                "--state",
                str(STATE_FIXTURE),
                "--crop",
                str(CROP_FIXTURE),
                "--out",
                str(tmp_path),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "run_id: " in output
    assert "out: " in output


def test_direct_unprovenanced_jsonl_cannot_be_recast_as_an_operational_build(
    tmp_path: Path,
) -> None:
    weather_rows = [json.loads(line) for line in WEATHER_FIXTURE.read_text().splitlines()]
    weather_rows[0]["fixture_non_scientific"] = False
    unsafe_weather = tmp_path / "weather.jsonl"
    unsafe_weather.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in weather_rows),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest-backed source adapters"):
        build_outlook(
            weather_path=unsafe_weather,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=tmp_path / "out",
        )


def test_build_outlook_never_replaces_an_existing_run_directory(tmp_path: Path) -> None:
    first = build_outlook(
        weather_path=WEATHER_FIXTURE,
        state_path=STATE_FIXTURE,
        crop_path=CROP_FIXTURE,
        out_dir=tmp_path,
    )
    manifest_before = (first.run_dir / "manifest.json").read_bytes()

    with pytest.raises(ValueError, match="already exists"):
        build_outlook(
            weather_path=WEATHER_FIXTURE,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=tmp_path,
        )

    assert (first.run_dir / "manifest.json").read_bytes() == manifest_before
