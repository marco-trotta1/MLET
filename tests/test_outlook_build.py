"""Software-only integration checks for the immutable outlook artifact."""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path

import pytest

from mlet.cli import main
from mlet.outlook.build import build_outlook, resolve_published_run
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
    assert payload["fixture_non_scientific"] is True
    assert payload["production_status"] == "non_production_fixture"
    assert payload["promotion_status"] == "not_promoted"
    assert payload["validation_status"] == "not_validated"
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
    assert result.run_dir == resolve_published_run(tmp_path, result.run_id)
    assert not result.run_dir.is_symlink()
    assert result.run_dir.name.startswith(f".{result.run_id}.building-")
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


def test_build_outlook_exclusive_claim_does_not_clobber_a_concurrent_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run-id directory appearing after staging must win without replacement."""
    original_symlink = os.symlink
    sentinel = b"concurrent publisher owns this directory"

    def claim_run_id_then_link(
        target: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        link_name: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        target_is_directory: bool = False,
        *,
        dir_fd: int | None = None,
    ) -> None:
        del target_is_directory, dir_fd
        run_dir = Path(link_name)
        run_dir.mkdir()
        (run_dir / "owner.txt").write_bytes(sentinel)
        original_symlink(target, link_name)

    monkeypatch.setattr("mlet.outlook.build.os.symlink", claim_run_id_then_link)

    with pytest.raises(ValueError, match="already exists"):
        build_outlook(
            weather_path=WEATHER_FIXTURE,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=tmp_path,
        )

    published = next(path for path in tmp_path.iterdir() if not path.name.startswith("."))
    assert published.is_dir()
    assert (published / "owner.txt").read_bytes() == sentinel
    assert not list(tmp_path.glob(".*.building-*"))


def test_failed_publication_fsync_removes_only_its_own_link_and_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A post-claim durability failure leaves the run id available for retry."""
    from mlet.outlook import build as outlook_build

    original_fsync_directory = outlook_build._fsync_directory

    def fail_after_public_claim(directory: Path) -> None:
        if directory == tmp_path and any(path.is_symlink() for path in tmp_path.iterdir()):
            raise OSError("injected publication root fsync failure")
        original_fsync_directory(directory)

    monkeypatch.setattr(
        "mlet.outlook.build._fsync_directory", fail_after_public_claim
    )

    with pytest.raises(OSError, match="publication root fsync failure"):
        build_outlook(
            weather_path=WEATHER_FIXTURE,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=tmp_path,
        )

    assert not [path for path in tmp_path.iterdir() if not path.name.startswith(".")]
    assert not list(tmp_path.glob(".*.building-*"))

    monkeypatch.setattr("mlet.outlook.build._fsync_directory", original_fsync_directory)
    retry = build_outlook(
        weather_path=WEATHER_FIXTURE,
        state_path=STATE_FIXTURE,
        crop_path=CROP_FIXTURE,
        out_dir=tmp_path,
    )
    assert retry.run_dir == resolve_published_run(tmp_path, retry.run_id)


def test_failed_publication_fsync_never_removes_a_replaced_public_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recovery leaves another publisher's replacement untouched."""
    from mlet.outlook import build as outlook_build

    original_fsync_directory = outlook_build._fsync_directory
    sentinel = b"another publisher owns this run id"

    def replace_claim_then_fail(directory: Path) -> None:
        if directory == tmp_path:
            claimed_links = [path for path in tmp_path.iterdir() if path.is_symlink()]
            if claimed_links:
                claimed_link = claimed_links[0]
                claimed_link.unlink()
                claimed_link.mkdir()
                (claimed_link / "owner.txt").write_bytes(sentinel)
                raise OSError("injected replacement publication fsync failure")
        original_fsync_directory(directory)

    monkeypatch.setattr(
        "mlet.outlook.build._fsync_directory", replace_claim_then_fail
    )

    with pytest.raises(OSError, match="replacement publication fsync failure"):
        build_outlook(
            weather_path=WEATHER_FIXTURE,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=tmp_path,
        )

    replacement = next(path for path in tmp_path.iterdir() if not path.name.startswith("."))
    assert replacement.is_dir()
    assert (replacement / "owner.txt").read_bytes() == sentinel
    assert not list(tmp_path.glob(".*.building-*"))


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        ("absolute_target", "must be relative"),
        ("escape_target", "escapes its immutable generation root"),
        ("dangling", "does not exist"),
        ("generation_symlink", "regular files only"),
        ("hash_mismatch", "hash mismatch"),
        ("manifest_run_id", "run_id does not match stable link"),
    ],
)
def test_resolve_published_run_rejects_tampered_or_unsafe_artifacts(
    tmp_path: Path, tamper: str, message: str
) -> None:
    result = build_outlook(
        weather_path=WEATHER_FIXTURE,
        state_path=STATE_FIXTURE,
        crop_path=CROP_FIXTURE,
        out_dir=tmp_path,
    )
    stable_link = tmp_path / result.run_id
    generation = result.run_dir

    if tamper == "absolute_target":
        stable_link.unlink()
        stable_link.symlink_to(generation, target_is_directory=True)
    elif tamper == "escape_target":
        stable_link.unlink()
        stable_link.symlink_to("../outside", target_is_directory=True)
    elif tamper == "dangling":
        generation.rename(tmp_path / "removed-generation")
    elif tamper == "generation_symlink":
        (generation / "unsafe-link").symlink_to("outlook.json")
    elif tamper == "hash_mismatch":
        (generation / "outlook.json").write_text("tampered\n", encoding="utf-8")
    elif tamper == "manifest_run_id":
        alternate_weather = tmp_path / "alternate-weather.jsonl"
        alternate_weather.write_bytes(WEATHER_FIXTURE.read_bytes())
        alternate = build_outlook(
            weather_path=alternate_weather,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=tmp_path / "alternate-output",
        )
        assert alternate.run_id != result.run_id
        (generation / "manifest.json").write_bytes(
            (alternate.run_dir / "manifest.json").read_bytes()
        )
    else:
        raise AssertionError(f"unrecognized tamper case: {tamper}")

    with pytest.raises(ValueError, match=message):
        resolve_published_run(tmp_path, result.run_id)


def test_resolve_published_run_rejects_a_symlinked_output_ancestor(tmp_path: Path) -> None:
    real_root = tmp_path / "real-output"
    result = build_outlook(
        weather_path=WEATHER_FIXTURE,
        state_path=STATE_FIXTURE,
        crop_path=CROP_FIXTURE,
        out_dir=real_root,
    )
    linked_root = tmp_path / "linked-output"
    linked_root.symlink_to(real_root, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinked ancestor"):
        resolve_published_run(linked_root, result.run_id)


def test_build_outlook_refuses_to_write_through_a_symlinked_ancestor(
    tmp_path: Path,
) -> None:
    real_root = tmp_path / "real-output"
    real_root.mkdir()
    linked_root = tmp_path / "linked-output"
    linked_root.symlink_to(real_root, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinked ancestor"):
        build_outlook(
            weather_path=WEATHER_FIXTURE,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=linked_root / "outlooks",
        )

    assert not (real_root / "outlooks").exists()
