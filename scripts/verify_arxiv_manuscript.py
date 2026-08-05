#!/usr/bin/env python3
"""Verify the MLET manuscript claims, citations, figures, and PDF."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

try:
    from scripts.build_arxiv_claims import _model_by_name, _validate_phase2_models
except ModuleNotFoundError as error:
    if error.name != "scripts":
        raise
    from build_arxiv_claims import _model_by_name, _validate_phase2_models


REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE2_RESULT = REPO_ROOT / "docs" / "results" / "phase2_openet_value.json"
FIGURE_DATA = REPO_ROOT / "manuscript" / "arxiv" / "figures" / "figure_data.json"
CLAIMS_TEX = REPO_ROOT / "manuscript" / "arxiv" / "generated_claims.tex"
MANUSCRIPT_TEX = REPO_ROOT / "manuscript" / "arxiv" / "mlet_preprint.tex"
COMPILE_LOG = REPO_ROOT / "output" / "pdf" / "mlet_preprint.log"

RETIRED_PHRASES = (
    "field-withheld",
    "H2 model",
    "calibrated interval",
    "nominal width of 0.80",
    "native grid",
    "weather-derived demand index",
    "non-serving FAO-56 dual water-balance",
)


def _object(path: Path) -> dict[str, object]:
    """Load one JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected one JSON object in {path}")
    return value


def _sha256(path: Path) -> str:
    """Return one file digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _macros() -> dict[str, str]:
    """Parse the generated publication macros."""
    text = CLAIMS_TEX.read_text(encoding="utf-8")
    pairs = re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{([^{}]*)\}", text)
    macros = dict(pairs)
    if len(macros) != len(pairs):
        raise ValueError("The generated claim file has duplicate macros")
    return macros


def validate_retired_phrases(text: str) -> None:
    """Reject claim language retired by the technical correction."""
    normalized = " ".join(text.casefold().split())
    for phrase in RETIRED_PHRASES:
        if phrase.casefold() in normalized:
            raise ValueError(f"The text contains a retired phrase: {phrase}")


def _verify_phase2(macros: dict[str, str]) -> None:
    """Verify the Phase 2 arm, arithmetic, and publication values."""
    payload = _object(PHASE2_RESULT)
    field_withheld = payload.get("field_withheld")
    h2 = payload.get("h2")
    if not isinstance(field_withheld, dict) or not isinstance(h2, dict):
        raise ValueError("The Phase 2 record is incomplete")
    models = field_withheld.get("models")
    if not isinstance(models, list):
        raise ValueError("The Phase 2 record lacks model rows")
    by_name = _model_by_name(payload)
    _validate_phase2_models(by_name)
    b2 = by_name["B2_WeatherRidge"]
    m2 = by_name["M2_OpenETRecal"]
    m3 = by_name["M3_OpenETRidge"]
    b2_mae = float(b2["mae_mm"])
    m2_mae = float(m2["mae_mm"])
    m3_mae = float(m3["mae_mm"])
    delta = float(h2["mae_delta_mm"])
    reduction = float(h2["mae_reduction_fraction"])
    ci95 = h2.get("ci95_mm")
    if not isinstance(ci95, list) or len(ci95) != 2:
        raise ValueError("The H2 interval is missing")
    if str(h2.get("best_openet_free_model")) != "B2_WeatherRidge":
        raise ValueError("The H2 baseline changed")
    if reduction < 0.10:
        raise ValueError("The H2 reduction is below the preregistered 10% threshold")
    if float(ci95[0]) <= 0.0:
        raise ValueError("The H2 confidence interval does not exclude zero")
    if not math.isclose(b2_mae - m3_mae, delta, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("The H2 delta no longer compares B2 with M3")
    if not math.isclose(delta / b2_mae, reduction, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("The H2 reduction is inconsistent")
    expected = {
        "BTwoMAE": f"{b2_mae:.3f}",
        "MTwoMAE": f"{m2_mae:.3f}",
        "MThreeMAE": f"{m3_mae:.3f}",
        "HtwoDelta": f"{delta:.3f}",
        "HtwoReduction": f"{100.0 * reduction:.1f}",
        "HtwoCILow": f"{float(ci95[0]):.3f}",
        "HtwoCIHigh": f"{float(ci95[1]):.3f}",
        "PhaseTwoN": f"{int(b2['sample_count']):,}",
    }
    for name, value in expected.items():
        if macros.get(name) != value:
            raise ValueError(f"The {name} macro is {macros.get(name)!r}, expected {value!r}")


def _verify_figure_sources() -> None:
    """Verify every plotted source digest and expected figure."""
    payload = _object(FIGURE_DATA)
    sources = payload.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("The figure data lacks sources")
    for record in sources.values():
        if not isinstance(record, dict):
            raise ValueError("Every figure source must be an object")
        relative_path = record.get("path")
        expected_sha = record.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(expected_sha, str):
            raise ValueError("A figure source lacks a path or digest")
        path = REPO_ROOT / relative_path
        if _sha256(path) != expected_sha:
            raise ValueError(f"The figure source changed: {relative_path}")
    figure_root = FIGURE_DATA.parent
    for index, stem in enumerate(
        (
            "evidence_paths",
            "phase2_models",
            "boii_feasibility",
            "native_grid",
            "support_tensor",
        ),
        start=1,
    ):
        for suffix in ("pdf", "png"):
            path = figure_root / f"figure_{index}_{stem}.{suffix}"
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f"The manuscript figure is missing: {path}")


def _verify_citations() -> None:
    """Verify complete citation coverage and basic APA entry structure."""
    text = MANUSCRIPT_TEX.read_text(encoding="utf-8")
    citation_groups = re.findall(r"\\cite[pt]?\{([^}]+)\}", text)
    cited = {
        key.strip()
        for group in citation_groups
        for key in group.split(",")
        if key.strip()
    }
    bib_matches = list(
        re.finditer(
            r"\\bibitem\[[^]]+\]\{([^}]+)\}\s*(.*?)(?=\\bibitem|\\end\{thebibliography\})",
            text,
            flags=re.DOTALL,
        )
    )
    bibliography = {match.group(1): match.group(2) for match in bib_matches}
    missing = cited - bibliography.keys()
    unused = bibliography.keys() - cited
    if missing:
        raise ValueError(f"Cited keys lack references: {sorted(missing)}")
    if unused:
        raise ValueError(f"References lack citations: {sorted(unused)}")
    year_pattern = re.compile(r"\((?:19|20)\d{2}[a-z]?\)\.")
    for key, entry in bibliography.items():
        if not year_pattern.search(entry):
            raise ValueError(f"The {key} entry lacks an APA year")
        if "\\textit{" not in entry:
            raise ValueError(f"The {key} entry lacks an italic APA source title")


def _verify_source_text() -> None:
    """Verify required claim language and prohibited characters."""
    generated_paths = [
        CLAIMS_TEX,
        FIGURE_DATA,
        REPO_ROOT / "scripts" / "build_arxiv_claims.py",
        REPO_ROOT / "scripts" / "build_arxiv_figures.py",
    ]
    for path in generated_paths:
        text = path.read_text(encoding="utf-8")
        validate_retired_phrases(text)
        for prohibited in ("—", "–"):
            if prohibited in text:
                raise ValueError(f"The file contains a prohibited dash: {path}")
    manuscript = MANUSCRIPT_TEX.read_text(encoding="utf-8")
    validate_retired_phrases(manuscript)
    normalized_manuscript = " ".join(manuscript.split())
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
        "baseline-minus-forecast MAE difference",
        "source_issue_at",
        "archive_available_at",
        "common 0.5-degree GEFS grid-point subset",
        "No interpolation",
        "Validation complete",
        "skillful",
        "release review",
        "scripts/decode_gefs_reforecast.py",
        "src/mlet/sources/gefs_reforecast_batch.py",
        "src/mlet/sources/gefs_grib.py",
        "src/mlet/sources/gefs_reforecast.py",
        "src/mlet/outlook/eto.py",
    )
    for phrase in required:
        if phrase not in normalized_manuscript:
            raise ValueError(f"The manuscript lacks required claim language: {phrase}")


def _verify_pdf(pdf_path: Path) -> None:
    """Verify the compiled PDF metadata and log."""
    if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        raise ValueError(f"The compiled PDF is missing: {pdf_path}")
    result = subprocess.run(
        ["pdfinfo", str(pdf_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    info = result.stdout
    pages_match = re.search(r"^Pages:\s+(\d+)$", info, flags=re.MULTILINE)
    if pages_match is None or int(pages_match.group(1)) < 8:
        raise ValueError("The compiled manuscript has fewer than eight pages")
    if "Page size:       612 x 792 pts (letter)" not in info:
        raise ValueError("The compiled manuscript is not US Letter size")
    title = "MLET: Incremental Predictive Value of OpenET and an Auditable Reference-Evapotranspiration Outlook"
    title_match = re.search(r"^Title:\s+(.+)$", info, flags=re.MULTILINE)
    if title_match is None or title_match.group(1).strip() != title:
        raise ValueError("The compiled manuscript has the wrong PDF title")
    if COMPILE_LOG.is_file():
        log = COMPILE_LOG.read_text(encoding="utf-8", errors="replace")
        fatal_terms = ("LaTeX Error", "undefined references", "undefined citations")
        for term in fatal_terms:
            if term in log:
                raise ValueError(f"The compile log contains: {term}")


def main() -> int:
    """Run all manuscript verification checks."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    args = parser.parse_args()
    macros = _macros()
    _verify_phase2(macros)
    _verify_figure_sources()
    _verify_citations()
    _verify_source_text()
    _verify_pdf(args.pdf.resolve())
    print("MLET arXiv manuscript verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
