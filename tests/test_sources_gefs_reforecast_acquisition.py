"""Tests for immutable retrieval receipts of GEFSv12 raw files."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from mlet.sources.gefs_reforecast_acquisition import (
    load_verified_gefs_reforecast_receipt,
    retrieve_gefs_reforecast_plan,
)
from mlet.sources.gefs_reforecast_plan import build_gefs_reforecast_acquisition_plan


class _Response:
    """Small streamed HTTP response fixture."""

    headers = {"ETag": "\"fixture-version\"", "Last-Modified": "Mon, 01 Jul 2019 00:00:00 GMT"}

    def __init__(self, contents: bytes) -> None:
        self._contents = contents
        self._offset = 0

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, count: int) -> bytes:
        result = self._contents[self._offset : self._offset + count]
        self._offset += len(result)
        return result


def test_retrieval_writes_checksum_bound_receipt_for_the_entire_fixed_plan(
    tmp_path: Path,
) -> None:
    """The receipt has one immutable identity for every planned raw object."""
    plan = build_gefs_reforecast_acquisition_plan(
        (datetime(2019, 7, 3, tzinfo=timezone.utc),)
    )

    receipt_path = retrieve_gefs_reforecast_plan(
        plan,
        data_root=tmp_path / "archive",
        receipt_path=tmp_path / "receipt.json",
        retrieved_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
        opener=lambda _: _Response(b"raw-grib-fixture"),
    )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["kind"] == "mlet.gefs.reforecast-retrieval-receipt"
    assert len(receipt["objects"]) == 187
    assert receipt["objects"][0]["etag"] == "\"fixture-version\""
    assert receipt["objects"][0]["sha256"] == (
        "d725d3d0c5cbfcd6ffeeed768683e65fb5ca9a3f88c6fcaa0662e8633c599316"
    )
    assert (tmp_path / "archive" / receipt["objects"][0]["local_path"]).read_bytes() == (
        b"raw-grib-fixture"
    )
    verified = load_verified_gefs_reforecast_receipt(
        receipt_path, data_root=tmp_path / "archive"
    )
    assert len(verified) == 187
    assert verified[0].path.read_bytes() == b"raw-grib-fixture"


def test_receipt_verifier_rejects_a_symlinked_raw_archive_root(tmp_path: Path) -> None:
    """A receipt must not resolve raw files through an uncontrolled root."""
    plan = build_gefs_reforecast_acquisition_plan(
        (datetime(2019, 7, 3, tzinfo=timezone.utc),)
    )
    archive = tmp_path / "archive"
    receipt_path = retrieve_gefs_reforecast_plan(
        plan,
        data_root=archive,
        receipt_path=tmp_path / "receipt.json",
        retrieved_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
        opener=lambda _: _Response(b"raw-grib-fixture"),
    )
    alias = tmp_path / "archive-alias"
    alias.symlink_to(archive, target_is_directory=True)

    with pytest.raises(ValueError, match="must not be a symlink"):
        load_verified_gefs_reforecast_receipt(receipt_path, data_root=alias)


def test_retrieval_rejects_an_unbounded_worker_count(tmp_path: Path) -> None:
    plan = build_gefs_reforecast_acquisition_plan(
        (datetime(2019, 7, 3, tzinfo=timezone.utc),)
    )

    with pytest.raises(ValueError, match="max_workers"):
        retrieve_gefs_reforecast_plan(
            plan,
            data_root=tmp_path / "archive",
            receipt_path=tmp_path / "receipt.json",
            retrieved_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
            max_workers=17,
            opener=lambda _: _Response(b"raw-grib-fixture"),
        )


def test_retrieval_rejects_an_unbounded_socket_timeout(tmp_path: Path) -> None:
    plan = build_gefs_reforecast_acquisition_plan(
        (datetime(2019, 7, 3, tzinfo=timezone.utc),)
    )

    with pytest.raises(ValueError, match="timeout_seconds"):
        retrieve_gefs_reforecast_plan(
            plan,
            data_root=tmp_path / "archive",
            receipt_path=tmp_path / "receipt.json",
            retrieved_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
            timeout_seconds=3_601,
            opener=lambda _: _Response(b"raw-grib-fixture"),
        )
