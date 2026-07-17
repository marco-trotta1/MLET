"""Software-only integration checks for the immutable outlook artifact."""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path

import pytest

from mlet.cli import main
from mlet.outlook.build import build_outlook, read_published_run, resolve_published_run
from mlet.outlook.manifest import RunManifest


WEATHER_FIXTURE = Path("examples/outlook/weather_members.jsonl")
STATE_FIXTURE = Path("examples/outlook/state.jsonl")
CROP_FIXTURE = Path("examples/outlook/crop_grid.jsonl")


def _private_generation(result: object) -> Path:
    """Test-only access to the private target; it is not a public API."""
    output_root = getattr(result, "output_root")
    run_id = getattr(result, "run_id")
    assert isinstance(output_root, Path)
    assert isinstance(run_id, str)
    return output_root / os.readlink(output_root / run_id)


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
    published = read_published_run(tmp_path, result.run_id)
    assert resolve_published_run(tmp_path, result.run_id) == published
    assert published.run_id == result.run_id
    assert json.loads(published.artifact_bytes("outlook.json")) == payload
    assert result.output_root == tmp_path
    assert not hasattr(result, "run_dir")
    assert all(
        hashlib.sha256(published.artifact_bytes(filename)).hexdigest() == digest
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
    assert "out_root: " in output
    assert "read: use mlet.outlook.build.read_published_run" in output


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
    generation = _private_generation(first)
    manifest_before = (generation / "manifest.json").read_bytes()

    with pytest.raises(ValueError, match="already exists"):
        build_outlook(
            weather_path=WEATHER_FIXTURE,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=tmp_path,
        )

    assert (generation / "manifest.json").read_bytes() == manifest_before


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
        del target_is_directory
        assert isinstance(link_name, str)
        assert dir_fd is not None
        os.mkdir(link_name, dir_fd=dir_fd)
        run_fd = os.open(link_name, os.O_RDONLY | os.O_DIRECTORY, dir_fd=dir_fd)
        owner_fd = os.open(
            "owner.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600,
            dir_fd=run_fd,
        )
        try:
            os.write(owner_fd, sentinel)
        finally:
            os.close(owner_fd)
            os.close(run_fd)
        original_symlink(target, link_name, dir_fd=dir_fd)

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
    # A failed publish keeps the private generation rather than recursively
    # deleting by a mutable pathname that could have been replaced.
    assert list(tmp_path.glob(".*.building-*"))


def test_builder_rejects_a_detectable_private_generation_replacement_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A symlink substitution before the first generation FD is rejected."""
    from mlet.outlook import build as outlook_build

    original_open = outlook_build._open_child_directory
    original_open_root = outlook_build._open_output_root
    opened_root_fds: list[int] = []
    moved_name: str | None = None
    replacement_name: str | None = None

    def capture_root(path: Path, *, create: bool):
        opened = original_open_root(path, create=create)
        opened_root_fds.append(opened.fd)
        return opened

    def replace_private_generation(parent_fd: int, name: str) -> int:
        nonlocal moved_name, replacement_name
        if name.startswith(".") and ".building-" in name and moved_name is None:
            moved_name = f"{name}.original"
            replacement_name = name
            os.rename(name, moved_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            os.symlink("/definitely-not-a-generation", name, dir_fd=parent_fd)
        return original_open(parent_fd, name)

    monkeypatch.setattr(
        "mlet.outlook.build._open_child_directory", replace_private_generation
    )
    monkeypatch.setattr("mlet.outlook.build._open_output_root", capture_root)

    with pytest.raises(ValueError, match="symlinked ancestor"):
        build_outlook(
            weather_path=WEATHER_FIXTURE,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=tmp_path,
        )

    assert moved_name is not None
    assert replacement_name is not None
    assert (tmp_path / moved_name).is_dir()
    assert (tmp_path / replacement_name).is_symlink()
    assert len(opened_root_fds) == 1
    with pytest.raises(OSError):
        os.fstat(opened_root_fds[0])


@pytest.mark.parametrize("mode", [0o775, 0o777])
def test_build_outlook_rejects_group_or_world_writable_output_root(
    tmp_path: Path, mode: int
) -> None:
    unsafe_root = tmp_path / f"unsafe-{mode:o}"
    unsafe_root.mkdir()
    unsafe_root.chmod(mode)

    with pytest.raises(ValueError, match="trusted output root without group/other write"):
        build_outlook(
            weather_path=WEATHER_FIXTURE,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=unsafe_root,
        )


def test_build_outlook_rejects_an_untrusted_output_root_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the effective user (or safe root-owned ancestors) may own a root."""
    actual_uid = os.geteuid()
    monkeypatch.setattr("mlet.outlook.build.os.geteuid", lambda: actual_uid + 1)

    with pytest.raises(ValueError, match="owned by the effective user or root"):
        build_outlook(
            weather_path=WEATHER_FIXTURE,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=tmp_path,
        )


def test_reader_rejects_a_group_writable_output_root(tmp_path: Path) -> None:
    result = build_outlook(
        weather_path=WEATHER_FIXTURE,
        state_path=STATE_FIXTURE,
        crop_path=CROP_FIXTURE,
        out_dir=tmp_path,
    )
    tmp_path.chmod(0o775)

    with pytest.raises(ValueError, match="trusted output root without group/other write"):
        read_published_run(tmp_path, result.run_id)


def test_trusted_root_rejects_observable_darwin_acl_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Darwin ACL marker is rejected even when mode bits look private."""
    from mlet.outlook import build as outlook_build

    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    monkeypatch.setattr(outlook_build.sys, "platform", "darwin")
    monkeypatch.setattr(
        outlook_build,
        "_darwin_acl_xattr_names",
        lambda fd: ("com.apple.acl.text",),
    )
    try:
        with pytest.raises(ValueError, match="without ACL metadata: com.apple.acl.text"):
            outlook_build._require_trusted_directory_fd(descriptor)
    finally:
        os.close(descriptor)


def test_trusted_root_fails_closed_when_darwin_acl_query_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed Darwin ACL query cannot silently reduce the trust check to modes."""
    from mlet.outlook import build as outlook_build

    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    monkeypatch.setattr(outlook_build.sys, "platform", "darwin")

    def fail_acl_query(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise OSError("injected xattr query failure")

    monkeypatch.setattr(outlook_build.subprocess, "run", fail_acl_query)
    try:
        with pytest.raises(OSError, match="cannot inspect Darwin ACL metadata"):
            outlook_build._require_trusted_directory_fd(descriptor)
    finally:
        os.close(descriptor)


def test_trusted_root_rejects_observable_linux_posix_acl_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Linux POSIX ACL marker is rejected even when mode bits look private."""
    from mlet.outlook import build as outlook_build

    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    monkeypatch.setattr(outlook_build.sys, "platform", "linux")
    monkeypatch.setattr(
        outlook_build.os,
        "listxattr",
        lambda fd: ("system.posix_acl_access",),
        raising=False,
    )
    try:
        with pytest.raises(
            ValueError, match="without ACL metadata: system.posix_acl_access"
        ):
            outlook_build._require_trusted_directory_fd(descriptor)
    finally:
        os.close(descriptor)


def test_trusted_root_fails_closed_when_acl_inspection_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A supported ACL platform never silently falls back to mode bits alone."""
    from mlet.outlook import build as outlook_build

    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    monkeypatch.setattr(outlook_build.sys, "platform", "linux")
    monkeypatch.delattr(outlook_build.os, "listxattr", raising=False)
    try:
        with pytest.raises(OSError, match="trust boundary is unsupported: cannot inspect Linux ACL"):
            outlook_build._require_trusted_directory_fd(descriptor)
    finally:
        os.close(descriptor)


def test_trusted_root_rejects_platform_without_acl_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unknown POSIX platforms are not treated as a verified trust boundary."""
    from mlet.outlook import build as outlook_build

    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    monkeypatch.setattr(outlook_build.sys, "platform", "freebsd13")
    try:
        with pytest.raises(OSError, match="trust boundary is unsupported: ACL inspection"):
            outlook_build._require_trusted_directory_fd(descriptor)
    finally:
        os.close(descriptor)


def test_build_outlook_closes_output_root_fd_when_private_creation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The root descriptor is closed even if generation allocation aborts."""
    from mlet.outlook import build as outlook_build

    original_open_root = outlook_build._open_output_root
    opened_fds: list[int] = []

    def capture_root(path: Path, *, create: bool):
        opened = original_open_root(path, create=create)
        opened_fds.append(opened.fd)
        return opened

    def fail_private_generation(root_fd: int, run_id: str):
        del root_fd, run_id
        raise RuntimeError("injected private creation failure")

    monkeypatch.setattr("mlet.outlook.build._open_output_root", capture_root)
    monkeypatch.setattr(
        "mlet.outlook.build._create_private_generation", fail_private_generation
    )

    with pytest.raises(RuntimeError, match="injected private creation failure"):
        build_outlook(
            weather_path=WEATHER_FIXTURE,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=tmp_path,
        )

    assert len(opened_fds) == 1
    with pytest.raises(OSError):
        os.fstat(opened_fds[0])


def test_build_outlook_closes_root_and_generation_fds_when_publish_collides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run-id collision closes both pinned descriptors before it propagates."""
    from mlet.outlook import build as outlook_build

    build_outlook(
        weather_path=WEATHER_FIXTURE,
        state_path=STATE_FIXTURE,
        crop_path=CROP_FIXTURE,
        out_dir=tmp_path,
    )

    original_open_root = outlook_build._open_output_root
    original_create = outlook_build._create_private_generation
    opened_fds: list[int] = []

    def capture_root(path: Path, *, create: bool):
        opened = original_open_root(path, create=create)
        opened_fds.append(opened.fd)
        return opened

    def capture_generation(root_fd: int, run_id: str):
        generation = original_create(root_fd, run_id)
        opened_fds.append(generation.fd)
        return generation

    monkeypatch.setattr("mlet.outlook.build._open_output_root", capture_root)
    monkeypatch.setattr("mlet.outlook.build._create_private_generation", capture_generation)

    with pytest.raises(ValueError, match="already exists"):
        build_outlook(
            weather_path=WEATHER_FIXTURE,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=tmp_path,
        )

    assert len(opened_fds) == 2
    for descriptor in opened_fds:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_build_outlook_preserves_primary_error_and_closes_every_directory_fd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Close errors cannot hide a publish error or strand ancestor/root/generation FDs."""
    from mlet.outlook import build as outlook_build

    nested_root = tmp_path / "trusted" / "outlooks"
    original_open = os.open
    original_close = os.close
    opened_directory_fds: list[int] = []

    def capture_directory_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if dir_fd is None:
            descriptor = original_open(path, flags, mode)
        else:
            descriptor = original_open(path, flags, mode, dir_fd=dir_fd)
        if flags & os.O_DIRECTORY:
            opened_directory_fds.append(descriptor)
        return descriptor

    def close_then_report_error(descriptor: int) -> None:
        original_close(descriptor)
        if descriptor in opened_directory_fds:
            raise OSError("injected close reporting error")

    def fail_publish(
        root_fd: int, private_generation: object, run_id: str
    ) -> None:
        del root_fd, private_generation, run_id
        raise RuntimeError("primary publish failure")

    monkeypatch.setattr("mlet.outlook.build.os.open", capture_directory_open)
    monkeypatch.setattr("mlet.outlook.build.os.close", close_then_report_error)
    monkeypatch.setattr("mlet.outlook.build._publish_private_artifact", fail_publish)

    with pytest.raises(RuntimeError, match="primary publish failure"):
        build_outlook(
            weather_path=WEATHER_FIXTURE,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=nested_root,
        )

    assert opened_directory_fds
    for descriptor in opened_directory_fds:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_failed_publication_fsync_preserves_claim_without_racy_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A durability-ambiguous claim is never readlink-then-unlinked."""
    from mlet.outlook import build as outlook_build

    original_fsync_directory = outlook_build._fsync_directory_fd
    root_stat = tmp_path.stat()

    def fail_after_public_claim(directory_fd: int) -> None:
        current = os.fstat(directory_fd)
        if (
            (current.st_dev, current.st_ino) == (root_stat.st_dev, root_stat.st_ino)
            and any(name and not name.startswith(".") for name in os.listdir(directory_fd))
        ):
            raise OSError("injected publication root fsync failure")
        original_fsync_directory(directory_fd)

    monkeypatch.setattr(
        "mlet.outlook.build._fsync_directory_fd", fail_after_public_claim
    )

    with pytest.raises(OSError, match="publication root fsync failure"):
        build_outlook(
            weather_path=WEATHER_FIXTURE,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=tmp_path,
        )

    stable = next(path for path in tmp_path.iterdir() if not path.name.startswith("."))
    assert stable.is_symlink()
    assert stable.resolve().is_dir()
    assert list(tmp_path.glob(".*.building-*"))


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
    generation = _private_generation(result)

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
            (_private_generation(alternate) / "manifest.json").read_bytes()
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


def test_reader_returns_original_verified_bytes_when_public_link_is_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A replacement after readlink cannot redirect the pinned generation FD."""
    from mlet.outlook import build as outlook_build

    result = build_outlook(
        weather_path=WEATHER_FIXTURE,
        state_path=STATE_FIXTURE,
        crop_path=CROP_FIXTURE,
        out_dir=tmp_path,
    )
    generation = _private_generation(result)
    expected = (generation / "outlook.json").read_bytes()
    stable_link = tmp_path / result.run_id
    hostile = tmp_path / ".hostile-generation"
    hostile.mkdir()
    original_open = outlook_build._open_pinned_published_generation

    def replace_public_link(root_fd: int, run_id: str):
        pinned = original_open(root_fd, run_id)
        stable_link.unlink()
        stable_link.symlink_to(hostile, target_is_directory=True)
        return pinned

    monkeypatch.setattr(
        "mlet.outlook.build._open_pinned_published_generation", replace_public_link
    )

    published = read_published_run(tmp_path, result.run_id)
    assert published.artifact_bytes("outlook.json") == expected
    assert stable_link.resolve() == hostile


def test_reader_rejects_generation_replaced_before_open_while_stable_link_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A target-name swap cannot redirect the reader after its inode sample."""
    from mlet.outlook import build as outlook_build

    result = build_outlook(
        weather_path=WEATHER_FIXTURE,
        state_path=STATE_FIXTURE,
        crop_path=CROP_FIXTURE,
        out_dir=tmp_path,
    )
    stable_link = tmp_path / result.run_id
    target = os.readlink(stable_link)
    generation = tmp_path / target
    moved = tmp_path / f"{target}.original"
    original_open = outlook_build._open_child_directory
    swapped = False

    def replace_named_generation(parent_fd: int, name: str) -> int:
        nonlocal swapped
        if name == target and not swapped:
            swapped = True
            generation.rename(moved)
            generation.mkdir()
        return original_open(parent_fd, name)

    monkeypatch.setattr(
        "mlet.outlook.build._open_child_directory", replace_named_generation
    )

    with pytest.raises(ValueError, match="generation changed while being opened"):
        read_published_run(tmp_path, result.run_id)
    assert swapped
    assert os.readlink(stable_link) == target
    assert moved.is_dir()


@pytest.mark.parametrize("missing_flag", ["O_DIRECTORY", "O_NOFOLLOW"])
def test_outlook_descriptor_capability_is_checked_lazily(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing_flag: str
) -> None:
    """Unsupported POSIX flags fail at use, not while importing MLET."""
    monkeypatch.delattr("mlet.outlook.build.os." + missing_flag, raising=False)

    with pytest.raises(OSError, match="requires local POSIX descriptor support"):
        build_outlook(
            weather_path=WEATHER_FIXTURE,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=tmp_path,
        )


def test_reader_returns_original_verified_bytes_when_generation_name_is_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ancestor/name swap after generation open cannot affect member reads."""
    from mlet.outlook import build as outlook_build

    result = build_outlook(
        weather_path=WEATHER_FIXTURE,
        state_path=STATE_FIXTURE,
        crop_path=CROP_FIXTURE,
        out_dir=tmp_path,
    )
    generation = _private_generation(result)
    expected = (generation / "outlook.json").read_bytes()
    moved = tmp_path / ".moved-original"
    original_read = outlook_build._read_regular_at
    swapped = False

    def move_generation_after_manifest(directory_fd: int, filename: str) -> bytes:
        nonlocal swapped
        contents = original_read(directory_fd, filename)
        if filename == "manifest.json" and not swapped:
            swapped = True
            generation.rename(moved)
            generation.mkdir()
            (generation / "manifest.json").write_text("{}", encoding="utf-8")
        return contents

    monkeypatch.setattr("mlet.outlook.build._read_regular_at", move_generation_after_manifest)

    published = read_published_run(tmp_path, result.run_id)
    assert swapped
    assert published.artifact_bytes("outlook.json") == expected
    assert (generation / "manifest.json").read_text(encoding="utf-8") == "{}"


def test_reader_rejects_member_replaced_between_lstat_and_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The inode comparison rejects a member swap before the FD is pinned."""
    result = build_outlook(
        weather_path=WEATHER_FIXTURE,
        state_path=STATE_FIXTURE,
        crop_path=CROP_FIXTURE,
        out_dir=tmp_path,
    )
    original_open = os.open
    swapped = False

    def swap_then_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if path == "outlook.json" and (flags & os.O_ACCMODE) == os.O_RDONLY and not swapped:
            swapped = True
            generation = _private_generation(result)
            replacement = generation / "replacement.json"
            replacement.write_bytes(b"replaced after lstat")
            replacement.replace(generation / "outlook.json")
        if dir_fd is None:
            return original_open(path, flags, mode)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr("mlet.outlook.build.os.open", swap_then_open)

    with pytest.raises(ValueError, match="changed while being read: outlook.json"):
        read_published_run(tmp_path, result.run_id)
    assert swapped


def test_builder_keeps_writing_to_pinned_parent_after_ancestor_name_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A symlink substituted after parent open cannot redirect publication."""
    from mlet.outlook import build as outlook_build

    safe_parent = tmp_path / "safe-parent"
    safe_parent.mkdir()
    moved_parent = tmp_path / "moved-parent"
    attacker_target = tmp_path / "attacker-target"
    attacker_target.mkdir()
    original_open_child = outlook_build._open_child_directory
    swapped = False

    def swap_parent_after_open(parent_fd: int, name: str) -> int:
        nonlocal swapped
        descriptor = original_open_child(parent_fd, name)
        if name == "safe-parent" and not swapped:
            swapped = True
            safe_parent.rename(moved_parent)
            safe_parent.symlink_to(attacker_target, target_is_directory=True)
        return descriptor

    monkeypatch.setattr(
        "mlet.outlook.build._open_child_directory", swap_parent_after_open
    )

    result = build_outlook(
        weather_path=WEATHER_FIXTURE,
        state_path=STATE_FIXTURE,
        crop_path=CROP_FIXTURE,
        out_dir=safe_parent / "outlooks",
    )

    assert swapped
    assert not (attacker_target / "outlooks").exists()
    assert read_published_run(moved_parent / "outlooks", result.run_id).run_id == result.run_id
