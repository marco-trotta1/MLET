"""Tests for the checked GEFS raw-receipt to daily-artifact bridge."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mlet.sources.gefs_reforecast_batch import decode_gefs_reforecast_issue


def test_batch_decoder_rejects_an_incomplete_verified_raw_issue() -> None:
    """No weather member may be decoded from a partial source receipt."""
    with pytest.raises(ValueError, match="does not match the frozen source plan"):
        decode_gefs_reforecast_issue(
            (),
            issue_time=datetime(2019, 7, 3, tzinfo=timezone.utc),
            idaho_bbox=(-117.25, 42.0, -111.0, 49.0),
        )
