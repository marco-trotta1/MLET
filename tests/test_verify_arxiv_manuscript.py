"""Tests for claim-safe manuscript verification helpers."""

from __future__ import annotations

import pytest

from scripts.verify_arxiv_manuscript import (
    MANUSCRIPT_TEX,
    RETIRED_PHRASES,
    _verify_citations,
    validate_retired_phrases,
)


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


def test_manuscript_defines_required_terms_and_exact_scope() -> None:
    """The manuscript must define technical terms and state corrected scope."""
    text = " ".join(MANUSCRIPT_TEX.read_text(encoding="utf-8").split())
    required = (
        "Machine Learning Evapotranspiration (MLET)",
        "Global Ensemble Forecast System version 12 (GEFSv12)",
        "National Oceanic and Atmospheric Administration (NOAA)",
        "U.S. Bureau of Reclamation (USBR)",
        "American Society of Civil Engineers Environmental and Water Resources Institute (ASCE-EWRI)",
        "grass-reference evapotranspiration (ETos)",
        "reference evapotranspiration (ETo)",
        "mean absolute error (MAE)",
        "root mean square error (RMSE)",
        "SHA-256 (a 256-bit secure hash)",
        "Coordinated Universal Time (UTC)",
        "00Z (00:00 UTC)",
        "H2 (the preregistered OpenET comparison)",
        "BOII (the Boise, Idaho AgriMet weather-station identifier)",
        "December-January-February (DJF)",
        "March-April-May (MAM)",
        "June-July-August (JJA)",
        "September-October-November (SON)",
        "station-held-out 10-fold evaluation",
        "gridMET ETo",
        "uncalibrated ensemble quantile band",
        "published station-derived target",
        "retrospective reforecast diagnostic",
        "scripts/decode_gefs_reforecast.py",
        "src/mlet/sources/gefs_reforecast_batch.py",
        "src/mlet/sources/gefs_grib.py",
        "src/mlet/sources/gefs_reforecast.py",
        "src/mlet/outlook/eto.py",
    )
    missing = [phrase for phrase in required if phrase not in text]
    assert not missing, f"missing technical definitions or scope: {missing}"


def test_manuscript_removes_orphan_water_balance_limitation() -> None:
    """The retired non-serving water-balance scaffold must not remain."""
    text = MANUSCRIPT_TEX.read_text(encoding="utf-8").casefold()
    assert "non-serving fao-56 dual water-balance" not in text


def test_verifier_audits_citation_keys() -> None:
    """Every cited key and bibliography key must have a one-to-one match."""
    _verify_citations()
