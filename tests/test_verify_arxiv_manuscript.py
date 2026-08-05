"""Tests for claim-safe manuscript verification helpers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from scripts.verify_arxiv_manuscript import (
    MANUSCRIPT_TEX,
    RETIRED_PHRASES,
    _verify_generated_artifacts,
    _verify_final_package,
    _verify_phase2_receipt,
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


def test_verifier_rejects_replaced_phase2_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A receipt with a changed result must fail before claims publish."""
    from scripts import verify_arxiv_manuscript

    receipt = json.loads(verify_arxiv_manuscript.PHASE2_RECEIPT.read_text())
    assert isinstance(receipt["result"], dict)
    receipt["result"]["station_count"] = 86
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    monkeypatch.setattr(verify_arxiv_manuscript, "PHASE2_RECEIPT", path)

    with pytest.raises(ValueError, match="different result"):
        _verify_phase2_receipt()


def test_verifier_rejects_stale_generated_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A replaced generated claims file must fail deterministic regeneration."""
    from scripts import verify_arxiv_manuscript

    stale = tmp_path / "generated_claims.tex"
    stale.write_bytes(verify_arxiv_manuscript.CLAIMS_TEX.read_bytes() + b"% stale\n")
    monkeypatch.setattr(verify_arxiv_manuscript, "CLAIMS_TEX", stale)

    with pytest.raises(ValueError, match="claim file is stale"):
        _verify_generated_artifacts()


def test_verifier_rejects_replaced_final_pdf(tmp_path: Path) -> None:
    """A truncated final PDF must fail the clean-source content check."""
    from scripts import verify_arxiv_manuscript

    stale = tmp_path / "stale.pdf"
    stale.write_bytes(verify_arxiv_manuscript.FINAL_PDF.read_bytes()[:-128])

    with pytest.raises(ValueError, match="PDF|clean source"):
        _verify_final_package(stale)


def test_verifier_normalizes_pdfinfo_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Poppler parser failure must become the verifier's stable validation error."""
    from scripts import verify_arxiv_manuscript

    def fail_pdfinfo(command: list[str], **_kwargs: object) -> None:
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(verify_arxiv_manuscript.subprocess, "run", fail_pdfinfo)

    with pytest.raises(ValueError, match="PDF metadata"):
        verify_arxiv_manuscript._verify_pdf(verify_arxiv_manuscript.FINAL_PDF)


def test_verifier_rejects_visible_pdf_overlay(tmp_path: Path) -> None:
    """A visible page overlay must fail even when PDF text metadata stays equal."""
    from scripts import verify_arxiv_manuscript

    reader = PdfReader(str(verify_arxiv_manuscript.FINAL_PDF))
    overlay_writer = PdfWriter()
    overlay_page = overlay_writer.add_blank_page(
        width=float(reader.pages[0].mediabox.width),
        height=float(reader.pages[0].mediabox.height),
    )
    stream = DecodedStreamObject()
    stream.set_data(b"q 1 0 0 rg 1 0 0 RG 72 700 180 50 re B Q\n")
    overlay_page[NameObject("/Contents")] = stream
    overlay_page[NameObject("/Resources")] = DictionaryObject()

    altered = tmp_path / "visible-overlay.pdf"
    writer = PdfWriter(clone_from=str(verify_arxiv_manuscript.FINAL_PDF))
    writer.pages[0].merge_page(overlay_page)
    with altered.open("wb") as handle:
        writer.write(handle)

    original_reader = PdfReader(str(verify_arxiv_manuscript.FINAL_PDF))
    altered_reader = PdfReader(str(altered))
    assert len(original_reader.pages) == len(altered_reader.pages)
    assert original_reader.metadata.get("/Title") == altered_reader.metadata.get("/Title")
    original_text = "\n".join(page.extract_text() or "" for page in original_reader.pages)
    altered_text = "\n".join(page.extract_text() or "" for page in altered_reader.pages)
    assert original_text == altered_text

    with pytest.raises(ValueError, match="PDF|clean source"):
        _verify_final_package(altered)


def test_verifier_fails_loudly_without_pdf_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing raster renderer must stop package verification."""
    from scripts import verify_arxiv_manuscript

    monkeypatch.setattr(verify_arxiv_manuscript.shutil, "which", lambda _name: None)

    with pytest.raises(ValueError, match="renderer.*unavailable"):
        verify_arxiv_manuscript._pdf_signature(verify_arxiv_manuscript.FINAL_PDF)


def test_verifier_rejects_stale_clean_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changed tracked clean source file must fail package verification."""
    from scripts import verify_arxiv_manuscript

    source = tmp_path / "mlet_preprint_source"
    shutil.copytree(verify_arxiv_manuscript.SOURCE_ROOT, source)
    generated = source / "generated_claims.tex"
    generated.write_bytes(generated.read_bytes() + b"% stale\n")
    monkeypatch.setattr(verify_arxiv_manuscript, "SOURCE_ROOT", source)

    with pytest.raises(ValueError, match="clean source"):
        _verify_final_package(verify_arxiv_manuscript.FINAL_PDF)
