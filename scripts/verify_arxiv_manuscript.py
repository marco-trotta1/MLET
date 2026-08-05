#!/usr/bin/env python3
"""Verify the MLET manuscript claims, citations, figures, and PDF."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from pypdf import PdfReader

try:
    from scripts.build_arxiv_claims import (
        _model_by_name,
        _phase2_station_count,
        _validate_phase2_models,
    )
except ModuleNotFoundError as error:
    if error.name != "scripts":
        raise
    from build_arxiv_claims import (
        _model_by_name,
        _phase2_station_count,
        _validate_phase2_models,
    )


REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE2_RESULT = REPO_ROOT / "docs" / "results" / "phase2_openet_value.json"
PHASE2_RECEIPT = REPO_ROOT / "docs" / "results" / "phase2_openet_independent_reproduction_receipt.json"
PHASE2_REPORT = REPO_ROOT / "docs" / "results" / "phase2_openet_value.md"
FIGURE_DATA = REPO_ROOT / "manuscript" / "arxiv" / "figures" / "figure_data.json"
FIGURE_ROOT = FIGURE_DATA.parent
CLAIMS_TEX = REPO_ROOT / "manuscript" / "arxiv" / "generated_claims.tex"
MANUSCRIPT_TEX = REPO_ROOT / "manuscript" / "arxiv" / "mlet_preprint.tex"
COMPILE_LOG = REPO_ROOT / "output" / "pdf" / "mlet_preprint.log"
FINAL_PDF = REPO_ROOT / "output" / "pdf" / "mlet_preprint.pdf"
SOURCE_ROOT = REPO_ROOT / "output" / "arxiv" / "mlet_preprint_source"
SOURCE_ARCHIVE = REPO_ROOT / "output" / "arxiv" / "mlet_preprint_source.tar.gz"
PDF_RENDER_DPI = 144

RETIRED_PHRASES = (
    "field-withheld",
    "H2 model",
    "calibrated interval",
    "nominal width of 0.80",
    "native grid",
    "weather-derived demand index",
    "non-serving FAO-56 dual water-balance",
    "prior-year day-of-year mean",
    "station_day_of_year_mean_prior_to_issue_year",
    "issue-time-valid",
    "lowest descriptive mae",
    "lowest descriptive point mae",
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
    phase2_station_count = _phase2_station_count(payload)
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
        "PhaseTwoStations": f"{phase2_station_count:,}",
        "BootstrapPhaseTwo": f"{int(payload.get('bootstrap_replicates', 0)):,}",
    }
    if type(payload.get("bootstrap_replicates")) is not int or payload["bootstrap_replicates"] < 1:
        raise ValueError("The Phase 2 result lacks bootstrap_replicates")
    for name, value in expected.items():
        if macros.get(name) != value:
            raise ValueError(f"The {name} macro is {macros.get(name)!r}, expected {value!r}")


def _verify_phase2_receipt() -> None:
    """Verify the independent receipt binds the current result and report bytes."""
    result = _object(PHASE2_RESULT)
    receipt = _object(PHASE2_RECEIPT)
    if receipt.get("schema_version") != 2:
        raise ValueError("The Phase 2 receipt must use schema version 2")
    if receipt.get("result") != result:
        raise ValueError("The Phase 2 receipt embeds a different result")
    output = receipt.get("output_sha256")
    if not isinstance(output, dict):
        raise ValueError("The Phase 2 receipt lacks output digests")
    expected = {
        "result_json": _sha256(PHASE2_RESULT),
        "report_markdown": _sha256(PHASE2_REPORT),
    }
    for name, digest in expected.items():
        if output.get(name) != digest:
            raise ValueError(f"The Phase 2 receipt digest is stale: {name}")


def _verify_generated_artifacts() -> None:
    """Regenerate claims and figures, then reject stale publication artifacts."""
    with tempfile.TemporaryDirectory(prefix="mlet-arxiv-generated-") as directory:
        root = Path(directory)
        generated_claims = root / "generated_claims.tex"
        generated_figures = root / "figures"
        environment = {"PYTHONPATH": str(REPO_ROOT / "src")}
        subprocess.run(
            ["python3", str(REPO_ROOT / "scripts" / "build_arxiv_claims.py"), "--out", str(generated_claims)],
            check=True,
            cwd=REPO_ROOT,
            env={**dict(os.environ), **environment},
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["python3", str(REPO_ROOT / "scripts" / "build_arxiv_figures.py"), "--out", str(generated_figures)],
            check=True,
            cwd=REPO_ROOT,
            env={**dict(os.environ), **environment},
            capture_output=True,
            text=True,
        )
        if generated_claims.read_bytes() != CLAIMS_TEX.read_bytes():
            raise ValueError("The generated claim file is stale or replaced")
        expected_names = (
            "figure_1_evidence_paths",
            "figure_2_phase2_models",
            "figure_3_boii_feasibility",
            "figure_4_native_grid",
            "figure_5_support_tensor",
        )
        for name in (*expected_names, "figure_data"):
            suffixes = ("json",) if name == "figure_data" else ("pdf", "png")
            for suffix in suffixes:
                generated = generated_figures / f"{name}.{suffix}"
                committed = FIGURE_ROOT / f"{name}.{suffix}"
                if not generated.is_file() or generated.read_bytes() != committed.read_bytes():
                    raise ValueError(f"The generated figure artifact is stale or replaced: {committed}")


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


def _verify_outlook_provenance() -> None:
    """Verify the BOII provenance records bind the current fold-2 evidence."""
    acquisition_path = REPO_ROOT / "data" / "outlook" / "agrimet_historical_acquisition.json"
    acquisition = _object(acquisition_path)
    target_build = acquisition.get("target_build")
    if not isinstance(target_build, dict):
        raise ValueError("The AgriMet acquisition record lacks target-build provenance")
    target_index = REPO_ROOT / "data" / "outlook" / "eto_feasibility_agrimet_index.json"
    target_path = REPO_ROOT / "data" / "outlook" / "eto_feasibility_targets" / "targets" / "issue-20190703-station-BOII-season-JJA-fold-2.json"
    evidence_path = REPO_ROOT / "data" / "outlook" / "eto_feasibility_archive" / "evidence.json"
    expected_hashes = {
        "target_index_sha256": target_index,
        "target_artifact_sha256": target_path,
        "evidence_sha256": evidence_path,
    }
    for field, path in expected_hashes.items():
        if target_build.get(field) != _sha256(path):
            raise ValueError(f"The AgriMet provenance digest is stale: {field}")
    timing = target_build.get("timing")
    if not isinstance(timing, dict) or timing.get("schema_version") != 2:
        raise ValueError("The AgriMet target timing record must use schema version 2")
    if timing.get("temporal_role") != "retrospective_reforecast":
        raise ValueError("The AgriMet target timing role is invalid")
    if timing.get("source_issue_at") != "2019-07-03T00:00:00Z":
        raise ValueError("The AgriMet target source issue time is invalid")
    expected_target_timing = _object(target_path).get("receipt")
    if not isinstance(expected_target_timing, dict):
        raise ValueError("The AgriMet target lacks its receipt")
    if timing.get("archive_available_at") != expected_target_timing.get("available_at"):
        raise ValueError("The AgriMet target archive availability is stale")

    evidence_text = (REPO_ROOT / "docs" / "data" / "2019-07-03_FEASIBILITY_EVIDENCE.md").read_text(encoding="utf-8")
    target_digest_match = re.search(r"Target SHA-256: `([0-9a-f]{64})`", evidence_text)
    evidence_digest_match = re.search(r"Evidence SHA-256: `([0-9a-f]{64})`", evidence_text)
    if target_digest_match is None or target_digest_match.group(1) != _sha256(target_path):
        raise ValueError("The BOII evidence target digest is stale")
    if evidence_digest_match is None or evidence_digest_match.group(1) != _sha256(evidence_path):
        raise ValueError("The BOII evidence bundle digest is stale")
    if "season-JJA-fold-4" in evidence_text or "reforecast issue timestamp as `available_at`" in evidence_text:
        raise ValueError("The BOII evidence prose contains retired fold or timing wording")
    if "season-JJA-fold-2" not in evidence_text or "archive_available_at" not in evidence_text:
        raise ValueError("The BOII evidence prose lacks current fold-2 timing provenance")


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
        REPO_ROOT / "scripts" / "build_eto_target_index.py",
        REPO_ROOT / "data" / "outlook" / "eto_feasibility_targets" / "target-build-receipt.json",
    ]
    prose_paths = [
        REPO_ROOT / "manuscript" / "manuscript.md",
        REPO_ROOT / "manuscript" / "DATA_AVAILABILITY.md",
        REPO_ROOT / "manuscript" / "arxiv" / "ARXIV_SUBMISSION.md",
        REPO_ROOT / "manuscript" / "SUPPLEMENT.md",
    ]
    for path in (*generated_paths, *prose_paths):
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
        "later retrieval timestamp",
        "does not prove operational availability at",
        "original publication time",
        "strictly prior calendar years",
        "target date, not the issue date, sets $Y_d$",
        "predictor-ready common table used by the runner",
        "drops rows with a missing measured response, OpenET value, gridMET ETo value",
        "common 0.5-degree GEFS grid-point subset",
        "No interpolation",
        "Validation complete",
        "skillful",
        "release review",
        "scripts/decode_gefs_reforecast.py",
        "src/mlet/sources/gefs_reforecast_batch.py",
        "src/mlet/sources/gefs_grib.py",
        "src/mlet/sources/gefs_reforecast.py",
        "src/mlet/outlook/spatial.py",
        "src/mlet/outlook/eto.py",
        "vendor/pyfao56/src/pyfao56/__version__.py",
        "Vendored pyfao56 version 1.4.3",
    )
    for phrase in required:
        if phrase not in normalized_manuscript:
            raise ValueError(f"The manuscript lacks required claim language: {phrase}")


def _verify_pdf(pdf_path: Path) -> None:
    """Verify the compiled PDF metadata and log."""
    if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        raise ValueError(f"The compiled PDF is missing: {pdf_path}")
    try:
        result = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("The PDF metadata check failed") from error
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


def _raster_hashes(pdf_path: Path, page_count: int) -> tuple[str, ...]:
    """Return fixed-resolution per-page raster digests for one PDF."""
    renderer = shutil.which("pdftoppm")
    if renderer is None:
        raise ValueError("The PDF raster renderer pdftoppm is unavailable")
    with tempfile.TemporaryDirectory(prefix="mlet-pdf-raster-") as directory:
        prefix = Path(directory) / "page"
        try:
            subprocess.run(
                [
                    renderer,
                    "-r",
                    str(PDF_RENDER_DPI),
                    "-f",
                    "1",
                    "-l",
                    str(page_count),
                    str(pdf_path),
                    str(prefix),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise ValueError(f"The PDF raster renderer failed for {pdf_path}") from error
        page_paths = sorted(
            Path(directory).glob("page-*.ppm"),
            key=lambda path: int(path.stem.rsplit("-", 1)[1]),
        )
        if len(page_paths) != page_count:
            raise ValueError("The PDF raster renderer returned the wrong page count")
        return tuple(_sha256(path) for path in page_paths)


def _pdf_signature(pdf_path: Path) -> tuple[int, str, str, tuple[str, ...]]:
    """Return stable page, text, title, and raster values for one PDF."""
    try:
        reader = PdfReader(str(pdf_path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        metadata = reader.metadata or {}
        title = str(metadata.get("/Title") or "")
    except Exception as error:
        raise ValueError(f"The PDF cannot be read: {pdf_path}") from error
    page_count = len(reader.pages)
    raster_hashes = _raster_hashes(pdf_path, page_count)
    return page_count, hashlib.sha256(text.encode("utf-8")).hexdigest(), title, raster_hashes


def _source_manifest() -> dict[str, Path]:
    """Return the tracked clean source files and their canonical inputs."""
    manifest = {
        "ARXIV_SUBMISSION.md": REPO_ROOT / "manuscript" / "arxiv" / "ARXIV_SUBMISSION.md",
        "generated_claims.tex": CLAIMS_TEX,
        "mlet_preprint.tex": MANUSCRIPT_TEX,
        "assets/irrigant_logo.png": REPO_ROOT / "manuscript" / "assets" / "irrigant_logo.png",
        "assets/uidaho_logo.png": REPO_ROOT / "manuscript" / "assets" / "uidaho_logo.png",
    }
    for stem in (
        "figure_1_evidence_paths",
        "figure_2_phase2_models",
        "figure_3_boii_feasibility",
        "figure_4_native_grid",
        "figure_5_support_tensor",
    ):
        manifest[f"figures/{stem}.pdf"] = FIGURE_ROOT / f"{stem}.pdf"
    return manifest


def _verify_clean_source(pdf_path: Path) -> None:
    """Verify the tracked source tree, archive, and clean-source PDF binding."""
    manifest = _source_manifest()
    if not SOURCE_ROOT.is_dir():
        raise ValueError("The tracked clean source directory is missing")
    for relative, canonical in manifest.items():
        source_path = SOURCE_ROOT / relative
        if not source_path.is_file() or source_path.read_bytes() != canonical.read_bytes():
            raise ValueError(f"The tracked clean source is stale or replaced: {relative}")

    if not SOURCE_ARCHIVE.is_file() or SOURCE_ARCHIVE.stat().st_size == 0:
        raise ValueError("The tracked clean source archive is missing")
    expected_files = set(manifest)
    archived_files: set[str] = set()
    try:
        with tarfile.open(SOURCE_ARCHIVE, mode="r:gz") as archive:
            for member in archive.getmembers():
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ValueError("The clean source archive contains an unsafe path")
                relative = member.name.removeprefix("./").rstrip("/")
                if not relative or member.isdir():
                    continue
                if not member.isfile() or relative not in expected_files:
                    raise ValueError("The clean source archive contains an unexpected file")
                extracted = archive.extractfile(member)
                if extracted is None or extracted.read() != (SOURCE_ROOT / relative).read_bytes():
                    raise ValueError(f"The clean source archive is stale: {relative}")
                archived_files.add(relative)
    except (OSError, tarfile.TarError) as error:
        raise ValueError("The clean source archive cannot be read") from error
    if archived_files != expected_files:
        missing = sorted(expected_files - archived_files)
        raise ValueError(f"The clean source archive lacks files: {missing}")

    with tempfile.TemporaryDirectory(prefix="mlet-clean-source-") as directory:
        output = Path(directory)
        try:
            subprocess.run(
                [
                    "tectonic",
                    "--outdir",
                    str(output),
                    "--keep-logs",
                    "mlet_preprint.tex",
                ],
                check=True,
                cwd=SOURCE_ROOT,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            raise ValueError("The tracked clean source does not compile") from error
        clean_pdf = output / "mlet_preprint.pdf"
        if _pdf_signature(pdf_path) != _pdf_signature(clean_pdf):
            raise ValueError("The final PDF and tracked clean source content differ")


def _verify_final_package(pdf_path: Path) -> None:
    """Verify the final PDF and bind it to the tracked clean source package."""
    _verify_pdf(pdf_path)
    _verify_clean_source(pdf_path)


def main() -> int:
    """Run all manuscript verification checks."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    args = parser.parse_args()
    macros = _macros()
    _verify_phase2_receipt()
    _verify_phase2(macros)
    _verify_outlook_provenance()
    _verify_generated_artifacts()
    _verify_figure_sources()
    _verify_citations()
    _verify_source_text()
    _verify_final_package(args.pdf.resolve())
    print("MLET arXiv manuscript verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
