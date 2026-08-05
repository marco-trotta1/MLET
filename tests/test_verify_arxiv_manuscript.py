"""Tests for claim-safe manuscript verification helpers."""

from __future__ import annotations

import pytest

from scripts.verify_arxiv_manuscript import RETIRED_PHRASES, validate_retired_phrases


def test_verifier_rejects_each_retired_phrase() -> None:
    """Each retired phrase must fail the callable text validator."""
    for phrase in RETIRED_PHRASES:
        with pytest.raises(ValueError, match="retired"):
            validate_retired_phrases(f"controlled fixture: {phrase}")


def test_verifier_accepts_exact_scope_language() -> None:
    """The replacement labels must pass retired-phrase validation."""
    validate_retired_phrases(
        "station-held-out 10-fold evaluation; common 0.5-degree GEFS "
        "grid-point subset; uncalibrated ensemble p10 to p90 quantile band; "
        "nominal coverage"
    )
