"""Build a verified static viewer for one ETo research candidate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
from typing import Any

from mlet.outlook.eto_contract import load_eto_candidate


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class EtoSiteResult:
    """Identity of one deterministic ETo static site."""

    destination: Path
    run_id: str
    candidate_sha256: str
    source_manifest_sha256: str
    site_manifest_sha256: str


def build_eto_site(source_dir: Path, destination: Path) -> EtoSiteResult:
    """Build a static site from a checksummed ETo candidate directory."""
    source_root = _regular_directory(source_dir, "ETo source directory")
    candidate_path = source_root / "outlook.json"
    manifest_path = source_root / "manifest.json"
    candidate_bytes = _regular_file_bytes(candidate_path, "ETo candidate")
    manifest_bytes = _regular_file_bytes(manifest_path, "ETo source manifest")
    candidate_sha256 = hashlib.sha256(candidate_bytes).hexdigest()
    source_manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = _load_manifest(manifest_bytes)
    issued_at = _parse_utc(manifest["issued_at"], "ETo source manifest issued_at")
    contract = load_eto_candidate(
        candidate_path,
        expected_run_id=manifest["run_id"],
        expected_issued_at=issued_at,
    )
    if manifest["artifact_sha256"] != {"outlook.json": candidate_sha256}:
        raise ValueError("ETo source manifest does not bind outlook.json")
    viewer_data = _viewer_data(
        candidate_bytes,
        manifest,
        candidate_sha256=candidate_sha256,
        source_manifest_sha256=source_manifest_sha256,
        run_id=contract.run_id,
        issued_at=contract.issued_at,
    )
    output = _prepare_destination(destination)
    output_outlook = output / "outlook"
    output_source = output_outlook / "source"
    output_source.mkdir(parents=True)
    (output / ".nojekyll").write_bytes(b"")
    _write_bytes(output_source / "outlook.json", candidate_bytes)
    _write_bytes(output_source / "manifest.json", manifest_bytes)
    _write_text(output_outlook / "viewer-data.json", _canonical_json(viewer_data))
    _write_text(output_outlook / "index.html", _viewer_html())
    _write_text(
        output / "index.html",
        _root_html(viewer_data, candidate_sha256, source_manifest_sha256),
    )
    file_names = (
        "index.html",
        "outlook/index.html",
        "outlook/viewer-data.json",
        "outlook/source/outlook.json",
        "outlook/source/manifest.json",
    )
    site_manifest = {
        "artifact_sha256": {
            name: _sha256(output / name) for name in file_names
        },
        "files": [
            {
                "bytes": (output / name).stat().st_size,
                "name": name,
                "sha256": _sha256(output / name),
            }
            for name in file_names
        ],
        "issued_at": contract.issued_at.isoformat().replace("+00:00", "Z"),
        "kind": "mlet.eto.static-site-manifest",
        "production_status": "research_candidate",
        "promotion_status": "not_promoted",
        "run_id": contract.run_id,
        "schema_version": 1,
        "source_candidate_sha256": candidate_sha256,
        "source_manifest_sha256": source_manifest_sha256,
        "validation_status": "evaluation_pending",
    }
    site_manifest_path = output / "manifest.json"
    _write_text(site_manifest_path, _canonical_json(site_manifest))
    return EtoSiteResult(
        destination=output,
        run_id=contract.run_id,
        candidate_sha256=candidate_sha256,
        source_manifest_sha256=source_manifest_sha256,
        site_manifest_sha256=_sha256(site_manifest_path),
    )


def _viewer_data(
    candidate_bytes: bytes,
    manifest: dict[str, Any],
    *,
    candidate_sha256: str,
    source_manifest_sha256: str,
    run_id: str,
    issued_at: datetime,
) -> dict[str, object]:
    payload = _load_object(candidate_bytes, "ETo candidate")
    collections = payload["feature_collections"]
    assert isinstance(collections, list)
    days: list[dict[str, object]] = []
    for collection in collections:
        assert isinstance(collection, dict)
        raw_features = collection["features"]
        assert isinstance(raw_features, list)
        cells: list[dict[str, object]] = []
        for feature in raw_features:
            assert isinstance(feature, dict)
            geometry = feature["geometry"]
            assert isinstance(geometry, dict)
            coordinates = geometry["coordinates"]
            assert isinstance(coordinates, list)
            properties = feature["properties"]
            assert isinstance(properties, dict)
            layers = properties["layers"]
            assert isinstance(layers, dict)
            quantiles = layers["eto_mm"]
            assert isinstance(quantiles, dict)
            cells.append(
                {
                    "grid_id": properties["grid_id"],
                    "latitude": float(coordinates[1]),
                    "longitude": float(coordinates[0]),
                    "value": {
                        "p10": float(quantiles["p10"]),
                        "p50": float(quantiles["p50"]),
                        "p90": float(quantiles["p90"]),
                        "status": "available",
                    },
                }
            )
        cells.sort(key=lambda item: str(item["grid_id"]))
        days.append(
            {
                "cells": cells,
                "lead_day": collection["lead_day"],
                "valid_date": collection["valid_date"],
            }
        )
    sources = manifest["sources"]
    assert isinstance(sources, list) and sources
    source = sources[0]
    assert isinstance(source, dict)
    return {
        "days": days,
        "grid_count": len(days[0]["cells"]) if days else 0,
        "kind": "mlet.eto.viewer-data",
        "layer": {
            "id": "eto_mm",
            "units": "mm/day",
            "definition": payload["layers"]["eto_mm"]["definition"],
        },
        "provenance": {
            "candidate_sha256": candidate_sha256,
            "git_revision": manifest["git_revision"],
            "retrieved_at": manifest["retrieved_at"],
            "source_manifest_sha256": source_manifest_sha256,
            "upstream_sha256": source["sha256"],
            "upstream_uri": source["uri"],
        },
        "run": {
            "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
            "production_status": payload["production_status"],
            "promotion_status": payload["promotion_status"],
            "run_id": run_id,
            "validation_status": payload["validation_status"],
        },
        "schema_version": 1,
    }


def _load_manifest(raw_bytes: bytes) -> dict[str, Any]:
    payload = _load_object(raw_bytes, "ETo source manifest")
    expected = {
        "artifact_sha256",
        "git_revision",
        "issued_at",
        "retrieved_at",
        "run_id",
        "schema_version",
        "sources",
    }
    if set(payload) != expected:
        raise ValueError("ETo source manifest fields must match the schema exactly")
    if payload["schema_version"] != 1:
        raise ValueError("ETo source manifest must use schema_version 1")
    if not _text(payload["run_id"]) or not _text(payload["git_revision"]):
        raise ValueError("ETo source manifest identity fields must be non-empty")
    _parse_utc(payload["retrieved_at"], "ETo source manifest retrieved_at")
    hashes = payload["artifact_sha256"]
    if not isinstance(hashes, dict) or set(hashes) != {"outlook.json"}:
        raise ValueError("ETo source manifest artifact_sha256 must name outlook.json")
    candidate_hash = hashes["outlook.json"]
    if not isinstance(candidate_hash, str) or not _SHA256.fullmatch(candidate_hash):
        raise ValueError("ETo source manifest outlook.json hash is invalid")
    sources = payload["sources"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("ETo source manifest must contain one source")
    source = sources[0]
    if not isinstance(source, dict):
        raise ValueError("ETo source manifest source must be an object")
    source_hash = source.get("sha256")
    if not _text(source.get("uri")) or not isinstance(source_hash, str) or not _SHA256.fullmatch(source_hash):
        raise ValueError("ETo source manifest source must contain a URI and checksum")
    return payload


def _load_object(raw_bytes: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} must be duplicate-key-free UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must use canonical UTC text")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError(f"{label} must use canonical UTC text") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must use canonical UTC text")
    return parsed.astimezone(timezone.utc)


def _regular_directory(path: Path, label: str) -> Path:
    supplied = Path(path)
    if supplied.is_symlink() or not supplied.is_dir():
        raise ValueError(f"{label} must be a real directory")
    return supplied.resolve(strict=True)


def _regular_file_bytes(path: Path, label: str) -> bytes:
    supplied = Path(path)
    if supplied.is_symlink() or not supplied.is_file():
        raise ValueError(f"{label} must be a regular file")
    return supplied.read_bytes()


def _prepare_destination(path: Path) -> Path:
    destination = Path(path).resolve()
    if destination == _REPO_ROOT or destination in _REPO_ROOT.parents:
        raise ValueError("ETo site destination must be a dedicated output directory")
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    return destination


def _write_bytes(path: Path, value: bytes) -> None:
    path.write_bytes(value)


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


# The chrome carries no colour: viridis belongs to the data, and the grid is
# the only place data appears. Hierarchy comes from rules, size, and case.
# Nothing on either page is a bordered box, and no webfont is requested, so
# the viewer stays self-contained and offline.
_CSS = """
:root{color-scheme:light dark;
--paper:#fff;--ink:#0e100f;--ink-2:#565a58;--ink-3:#8b908d;
--line:#e7e8e5;--line-2:#c6c9c5;--amber:#a06a0c;
--sans:"Söhne","Sohne","Inter",-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;
--mono:"Söhne Mono","Berkeley Mono","IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace}
@media (prefers-color-scheme:dark){:root{--paper:#0b0d0c;--ink:#edeeeb;--ink-2:#9ba09d;
--ink-3:#6c716e;--line:#1c1f1d;--line-2:#343836;--amber:#d8a54a}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
font-size:13px;line-height:1.5;font-variant-numeric:tabular-nums;
-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:var(--ink);text-decoration:underline;text-decoration-color:var(--line-2);
text-underline-offset:2px}
a:hover{text-decoration-color:var(--ink)}
h1{margin:0;font-size:clamp(20px,2.1vw,26px);font-weight:600;letter-spacing:-.017em;
line-height:1.2;max-width:36ch}
h2{margin:0 0 10px;font-size:10px;font-weight:600;letter-spacing:.11em;
text-transform:uppercase;color:var(--ink-3)}
h2 .sn{margin-right:10px;font-family:var(--mono);opacity:.5}
h3{margin:17px 0 6px;font-size:12px;font-weight:600}
p{margin:0 0 9px;max-width:78ch}
.bar{display:flex;justify-content:space-between;align-items:baseline;gap:16px;
padding:9px 0 8px;border-bottom:1px solid var(--line)}
.wm{font-family:var(--mono);font-size:11px;font-weight:600;letter-spacing:.14em;
text-transform:uppercase;text-decoration:none}
.bar-meta{font-family:var(--mono);font-size:10px;letter-spacing:.05em;color:var(--ink-3)}
.kicker{font-family:var(--mono);font-size:10px;letter-spacing:.13em;text-transform:uppercase;
color:var(--ink-3);margin:0 0 7px}
.lede{margin:11px 0 0;max-width:74ch;font-size:13.5px;line-height:1.5;color:var(--ink-2)}
.sub{color:var(--ink-2)}
.fine{font-size:11.5px;line-height:1.5;color:var(--ink-3);max-width:86ch}
.status{margin:16px 0 0;padding-left:11px;border-left:2px solid var(--amber);max-width:84ch}
.status b{font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:.1em;
text-transform:uppercase;color:var(--amber);margin-right:9px}
.status span{font-size:12px;color:var(--ink-2)}
.spec{display:grid;grid-template-columns:repeat(6,1fr);margin:22px 0 0;
border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.spec>div{padding:8px 14px;border-left:1px solid var(--line)}
.spec>div:first-child{padding-left:0;border-left:0}
.spec dt{font-size:9.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;
color:var(--ink-3);white-space:nowrap}
.spec dd{margin:3px 0 0;font-family:var(--mono);font-size:13.5px;color:var(--ink)}
section{margin-top:28px;padding-top:11px;border-top:1px solid var(--line)}
table{width:100%;border-collapse:collapse}
caption{text-align:left;color:var(--ink-3);font-size:11px;padding-bottom:6px}
th{text-align:left;font-size:9.5px;font-weight:600;letter-spacing:.09em;
text-transform:uppercase;color:var(--ink-3);padding:0 14px 5px 0;
border-bottom:1px solid var(--line-2);white-space:nowrap}
td{padding:5px 14px 5px 0;border-bottom:1px solid var(--line);font-family:var(--mono);
font-size:11.5px;color:var(--ink-2);vertical-align:baseline}
td.k{font-family:var(--sans);font-size:12px;color:var(--ink);white-space:nowrap}
th:last-child,td:last-child{padding-right:0}
.num{text-align:right}
.dot{display:inline-block;width:5px;height:5px;margin-right:7px;border-radius:50%;
background:var(--amber);vertical-align:middle}
/* Bars are data marks, not chrome: they put the effect size on the same row as
   the number so the gap to the baselines is legible without a second figure. */
td.bar{width:112px;padding-right:0}
td.bar i{display:block;height:5px;background:var(--ink-2)}
tr.base td.bar i{background:var(--line-2)}
.meter{position:relative;display:block;width:150px;height:5px;margin-top:5px;
background:var(--line)}
.meter i{display:block;height:100%;background:var(--ink-2)}
.meter b{position:absolute;top:-3px;bottom:-3px;width:1px;background:var(--amber)}
.ledger th{width:186px;font-family:var(--sans);font-size:11.5px;font-weight:400;
letter-spacing:0;text-transform:none;color:var(--ink-3);padding:5px 18px 5px 0;
border-bottom:1px solid var(--line);vertical-align:baseline}
.ledger td{overflow-wrap:anywhere}
.run{margin:0;padding:1px 0 1px 11px;border-left:2px solid var(--line-2);
font-family:var(--mono);font-size:11.5px;line-height:1.72;color:var(--ink-2);
overflow-x:auto}
footer{margin-top:32px;padding-top:10px;border-top:1px solid var(--line);display:flex;
flex-wrap:wrap;gap:18px;font-size:11.5px;color:var(--ink-3)}
@media (max-width:720px){
h1{max-width:none}
.bar{flex-direction:column;align-items:flex-start;gap:5px}
.spec{grid-template-columns:1fr 1fr;border-bottom:0}
.spec>div{padding:8px 12px;border-left:1px solid var(--line);
border-bottom:1px solid var(--line)}
.spec>div:nth-child(odd){padding-left:0;border-left:0}
td.bar{display:none}
}
"""

_ROOT_CSS = """
main{max-width:1080px;margin:0 auto;padding:0 24px 52px}
.hero{padding:26px 0 0}
.jump{margin:16px 0 0;font-size:13px}
.pair{display:grid;grid-template-columns:1fr 1fr}
.pair>div{padding-right:28px}
.pair>div+div{padding:0 0 0 28px;border-left:1px solid var(--line)}
.pair h3{margin:0 0 5px}
.pair p{margin:0;font-size:12px;color:var(--ink-2)}
.lim{margin:0;padding:0;list-style:none}
.lim li{padding:4px 0;border-bottom:1px solid var(--line);font-size:11.5px;
line-height:1.45;color:var(--ink-3)}
.lim li:last-child{border-bottom:0}
.two{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:0}
.two.even{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
.two>div+div{padding-left:30px;margin-left:30px;border-left:1px solid var(--line)}
@media (max-width:900px){
.two{grid-template-columns:1fr}
.two>div+div{margin:22px 0 0;padding:18px 0 0;border-left:0;border-top:1px solid var(--line)}
}
@media (max-width:720px){
main{padding:0 16px 40px}
.hero{padding:20px 0 0}
.pair{grid-template-columns:1fr}
.pair>div{padding:0}
.pair>div+div{margin-top:16px;padding:16px 0 0;border-left:0;border-top:1px solid var(--line)}
}
"""


def _root_html(
    viewer_data: dict[str, object], candidate_sha256: str, source_manifest_sha256: str
) -> str:
    run = viewer_data["run"]
    assert isinstance(run, dict)
    provenance = viewer_data["provenance"]
    assert isinstance(provenance, dict)
    days = viewer_data["days"]
    assert isinstance(days, list)
    layer = viewer_data["layer"]
    assert isinstance(layer, dict)
    issued_at = str(run["issued_at"])
    issue_short = f"{issued_at[:10]} {issued_at[11:13]}Z"
    first_cells = days[0]["cells"] if days else []
    assert isinstance(first_cells, list)
    latitudes = sorted({float(cell["latitude"]) for cell in first_cells})
    spacing = (
        min(upper - lower for lower, upper in zip(latitudes, latitudes[1:]))
        if len(latitudes) > 1
        else 0.0
    )
    ledger = (
        ("Run ID", run["run_id"]),
        ("Issue time", issued_at),
        ("Retrieved at", provenance["retrieved_at"]),
        ("Git revision", provenance["git_revision"]),
        ("Candidate SHA-256", candidate_sha256),
        ("Source manifest SHA-256", source_manifest_sha256),
        ("GEFS artifact SHA-256", provenance["upstream_sha256"]),
        ("Upstream source", provenance["upstream_uri"]),
    )
    def _ledger_rows(entries: tuple[tuple[str, object], ...]) -> str:
        return "".join(
            f'<tr><th scope="row">{html.escape(str(label))}</th>'
            f"<td>{html.escape(str(value))}</td></tr>"
            for label, value in entries
        )

    split = (len(ledger) + 1) // 2
    ledger_rows_left = _ledger_rows(ledger[:split])
    ledger_rows_right = _ledger_rows(ledger[split:])
    # Phase 2 station-held-out figures mirror docs/results/phase2_openet_value.md.
    # The BOII figures mirror manuscript/manuscript.md. Both are frozen results.
    phase2 = (
        ("M2_OpenETRecal", 0.781, "1.060", "0.005", False),
        ("M1_OpenETDirect", 0.784, "1.066", "0.154", False),
        ("M3_OpenETRidge", 0.856, "1.386", "-0.013", False),
        ("B2_WeatherRidge", 1.514, "2.687", "-0.098", True),
        ("B1_CropCoefficient", 1.532, "2.005", "0.149", True),
    )
    worst_mae = max(row[1] for row in phase2)
    phase2_rows = "".join(
        ('<tr class="base">' if baseline else "<tr>")
        + (
            f'<td class="k">{name}</td><td class="num">{mae:.3f}</td>'
            f'<td class="num">{rmse}</td><td class="num">{bias}</td>'
            f'<td class="num">7923</td><td class="bar">'
            f'<i style="width:{mae / worst_mae * 100:.1f}%"></i></td></tr>'
        )
        for name, mae, rmse, bias, baseline in phase2
    )
    coverage_meter = (
        '<span class="meter" aria-hidden="true"><i style="width:25%"></i>'
        '<b style="left:80%"></b></span>'
    )
    boii = (
        ("GEFS ETo forecast, MAE", "1.133 mm/day"),
        ("Prior-year climatology, MAE", "0.505 mm/day"),
        ("Baseline minus forecast", "-0.628 mm/day, forecast worse"),
        ("p10 to p90 coverage", f"0.25, nominal 0.80{coverage_meter}"),
        ("Mean band width", "1.453 mm/day"),
        ("Support", "1 issue, 1 station, 20 targets"),
        ("Paired interval", "not identified, 1 bootstrap cluster"),
    )
    boii_rows = "".join(
        f'<tr><th scope="row">{label}</th><td>{value}</td></tr>'
        for label, value in boii
    )
    # Verbatim from the manuscript limitations section.
    limitations = (
        "The full 365-issue GEFS and AgriMet outcome archive is absent.",
        "Full-archive reference-ETo skill remains pending.",
        "Historical location evidence covers 19 stations.",
        "The weather artifact has grid points, not field boundaries or area weights.",
        "The Phase 2 result does not measure future forecast performance.",
        "The BOII uncertainty is not estimable with one bootstrap cluster.",
    )
    limitation_items = "".join(f"<li>{item}</li>" for item in limitations)
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MLET reference evapotranspiration outlook</title>
<style>{_CSS}{_ROOT_CSS}</style></head>
<body><main>
<header class="bar"><span class="wm">MLET</span>
<span class="bar-meta">Idaho reference evapotranspiration</span></header>

<div class="hero">
<p class="kicker">Reference ETo candidate</p>
<h1>Twenty lead days of reference ET, from one archived weather issue.</h1>
<p class="lede">One ASCE standardized short-reference ETo candidate on the native GEFS
grid. Every cell carries p10, p50, and p90 from the weather ensemble. Every file
carries a checksum.</p>
<p class="status"><b>Validation status</b><span>Evaluation pending. This candidate is
not validated, not promoted, and not an irrigation recommendation. The reference-ETo
skill question stays open until the full archive hindcast runs.</span></p>
<dl class="spec">
<div><dt>GEFS issue</dt><dd>{html.escape(issue_short)}</dd></div>
<div><dt>Lead days</dt><dd>{len(days)}</dd></div>
<div><dt>Grid cells</dt><dd>{html.escape(str(viewer_data["grid_count"]))}</dd></div>
<div><dt>Spacing</dt><dd>{spacing:g} deg</dd></div>
<div><dt>Layer</dt><dd>{html.escape(str(layer["id"]))}</dd></div>
<div><dt>Units</dt><dd>{html.escape(str(layer["units"]))}</dd></div>
</dl>
<p class="jump"><a href="outlook/">Open the grid viewer</a></p>
</div>

<section>
<h2><span class="sn">01</span>Layer boundary</h2>
<div class="pair">
<div><h3>What eto_mm reports</h3>
<p>{html.escape(str(layer["definition"]))} Millimeters per day at common
{spacing:g} degree GEFS grid points, from empirical quantiles over the sorted
ensemble members.</p></div>
<div><h3>What eto_mm does not report</h3>
<p>It is not observed ET, crop ET, soil water, or field condition. A grid point is a
weather reference. It is not a field boundary, and the band is uncalibrated.</p></div>
</div>
</section>

<section>
<h2><span class="sn">02</span>Retrospective daily actual ET</h2>
<p class="fine">85 stations, station-held-out 10-fold evaluation on the
weather-complete public subset. All rows share the same 7,923 common fitted-model
station-days. Baselines are shown in the lighter tone. This is daily-ET evidence
only, and it is not validation of the outlook below.</p>
<table>
<thead><tr><th>Model</th><th class="num">MAE</th><th class="num">RMSE</th>
<th class="num">Bias</th><th class="num">n</th><th class="bar"></th></tr></thead>
<tbody>{phase2_rows}</tbody>
</table>
<p class="fine" style="margin-top:9px">Preregistered comparison: M3 OpenETRidge against
B2 WeatherRidge, the better OpenET-free baseline. MAE is 43.4% lower, a difference of
0.658 mm/day, station-blocked 95% CI 0.399 to 0.911 mm/day. B0 persistence reaches MAE
0.350 mm/day on 1,555 consecutive-day pairs, but it reads the previous observed day and
stays an oracle-like diagnostic, not a comparable model.</p>
</section>

<section>
<h2><span class="sn">03</span>Reference ETo outlook, BOII diagnostic</h2>
<div class="two">
<div>
<p class="fine">One retrospective reforecast case against published AgriMet ETos. The
signed result is negative: the forecast loses to fixed station and target-day
climatology from strictly prior calendar years.</p>
<table class="ledger"><tbody>{boii_rows}</tbody></table>
<p class="fine" style="margin-top:9px">The case sits below the 30-target support rule,
so it supports no skill claim in either direction.</p>
</div>
<div><h3 style="margin-top:0">Limitations</h3>
<ul class="lim">{limitation_items}</ul></div>
</div>
</section>

<section>
<h2><span class="sn">04</span>Artifact ledger</h2>
<div class="two even">
<div><table class="ledger"><tbody>{ledger_rows_left}</tbody></table></div>
<div><table class="ledger"><tbody>{ledger_rows_right}</tbody></table></div>
</div>
<p class="fine" style="margin-top:9px">Files:
<a href="outlook/source/outlook.json">candidate JSON</a> ·
<a href="outlook/source/manifest.json">source manifest</a> ·
<a href="outlook/viewer-data.json">viewer data</a> ·
<a href="manifest.json">site manifest</a></p>
</section>

<section>
<h2><span class="sn">05</span>Run locally</h2>
<pre class="run">python3 scripts/build_eto_site.py \\
  --source-dir data/outlook/gefs_reforecast_20190703_candidate \\
  --out /tmp/mlet-eto-site
python3 -m http.server 8000 --directory /tmp/mlet-eto-site</pre>
<p class="fine" style="margin-top:9px">The builder verifies the candidate against its
manifest and writes a self-contained static site. Serve the output over HTTP: the pages
read local JSON, and browsers block those reads from a file path.</p>
</section>

<footer>
<span>MLET · open-source machine learning evapotranspiration</span>
<a href="https://github.com/marco-trotta1/MLET/blob/main/docs/outlook/PRODUCT_CONTRACT.md">Product contract</a>
<a href="https://github.com/marco-trotta1/MLET/blob/main/docs/evaluation/OUTLOOK_PREREGISTRATION.md">Preregistration</a>
<a href="https://github.com/marco-trotta1/MLET/blob/main/docs/data/DATA_CARD.md">Data card</a>
<a href="https://github.com/marco-trotta1/MLET">Repository</a>
</footer>
</main></body></html>
"""


_VIEWER_CSS = """
main{max-width:1240px;margin:0 auto;padding:0 24px 72px}
.head{padding:20px 0 0}
.head h1{font-size:clamp(19px,2vw,25px);max-width:44ch}
.head .lede{margin-top:8px;font-size:13px;max-width:88ch}
.toolbar{display:flex;flex-wrap:wrap;align-items:flex-end;gap:11px 30px;margin-top:18px;
padding:10px 0 9px;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.tool .lbl{display:block;margin-bottom:5px;font-size:9.5px;font-weight:600;
letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3)}
.ticks{display:flex;flex-wrap:wrap}
.ticks button,.seg button{font-family:var(--mono);font-size:11.5px;line-height:1.3;
color:var(--ink-3);background:none;border:0;border-bottom:2px solid transparent;
padding:1px 7px 3px;cursor:pointer}
.ticks button:first-child,.seg button:first-child{padding-left:0}
.ticks button:hover,.seg button:hover{color:var(--ink)}
.ticks button[aria-pressed="true"],.seg button[aria-pressed="true"]{color:var(--ink);
border-bottom-color:var(--ink)}
select{font-family:var(--mono);font-size:11.5px;color:var(--ink);background:none;
border:0;border-bottom:1px solid var(--line-2);padding:1px 4px 3px 0;cursor:pointer;
max-width:176px}
select:hover{border-bottom-color:var(--ink)}
:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.valid{font-family:var(--mono);font-size:11.5px;color:var(--ink)}
.state{margin:9px 0 0;min-height:1.4em;font-size:11.5px;color:var(--ink-3)}
.work{display:grid;grid-template-columns:minmax(0,360px) minmax(0,1fr);margin-top:14px;
padding-top:16px;border-top:1px solid var(--line)}
.work .left{padding-right:30px}
.work .right{padding-left:30px;border-left:1px solid var(--line)}
.work .right h2{margin-top:26px}
.work .right h2:first-child{margin-top:0}
svg{display:block;width:100%;height:auto}
.cell{cursor:pointer;stroke:none}
.cell:hover{stroke:var(--ink-2);stroke-width:1.2}
.cell.sel{stroke:var(--ink);stroke-width:1.6}
.grat line{stroke:var(--line-2);stroke-width:.5}
.axis{font-family:var(--mono);font-size:9px;fill:var(--ink-3)}
#fan{max-width:520px}
.ramp{height:6px;margin-top:13px;
background:linear-gradient(90deg,#440154,#414487,#2a788e,#22a884,#7ad151,#fde725)}
.rampkey{display:flex;justify-content:space-between;margin-top:5px;font-family:var(--mono);
font-size:10px;color:var(--ink-3)}
.big{font-family:var(--mono);font-size:30px;line-height:1.05;letter-spacing:-.02em;
margin-top:1px}
.big .unit{font-size:12px;color:var(--ink-3);margin-left:6px;letter-spacing:0}
.where{margin-top:6px;font-family:var(--mono);font-size:11px;color:var(--ink-3)}
.trip{display:flex;gap:28px;margin:14px 0 0;padding:0}
.trip div{margin:0}
.trip dt{font-size:9.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;
color:var(--ink-3)}
.trip dd{margin:3px 0 0;font-family:var(--mono);font-size:13.5px}
.band{fill:currentColor;opacity:.11}
.p50line{fill:none;stroke:currentColor;stroke-width:1.5}
.mark{stroke:var(--ink-3);stroke-width:1;stroke-dasharray:2 3}
.markdot{fill:var(--paper);stroke:currentColor;stroke-width:1.75}
.layerid{margin:0 0 4px;font-family:var(--mono);font-size:12px;color:var(--ink)}
.cells{border-collapse:separate;border-spacing:0}
.cells th{position:sticky;top:0;z-index:1;background:var(--paper);padding-top:7px}
.cells td{padding-top:4px;padding-bottom:4px}
.tblwrap{max-height:460px;overflow:auto}
@media (max-width:720px){
main{padding:0 16px 40px}
.head{padding:16px 0 0}
.work{grid-template-columns:1fr}
.work .left{padding-right:0}
.work .right{margin-top:20px;padding:18px 0 0;border-left:0;border-top:1px solid var(--line)}
}
"""

_VIEWER_BODY = """
<body><main>
<header class="bar"><a class="wm" href="../">MLET</a>
<span class="bar-meta"><span class="dot" aria-hidden="true"></span>research candidate ·
evaluation pending · not promoted</span></header>

<div class="head">
<p class="kicker">Grid viewer</p>
<h1>ASCE short-reference ETo on the native GEFS grid.</h1>
<p class="lede">One archived issue, 20 lead days. Pick a lead day, a quantile, and a
grid cell. The band is an uncalibrated ensemble quantile range, and a grid point is a
weather reference, not a field boundary.</p>
</div>

<div class="toolbar">
<div class="tool"><span class="lbl" id="lead-label">Lead day</span>
<div class="ticks" id="lead" role="group" aria-labelledby="lead-label"></div></div>
<div class="tool"><span class="lbl" id="quant-label">Quantile</span>
<div class="seg" id="quantile" role="group" aria-labelledby="quant-label">
<button type="button" data-q="p10" aria-pressed="false">p10</button>
<button type="button" data-q="p50" aria-pressed="true">p50</button>
<button type="button" data-q="p90" aria-pressed="false">p90</button></div></div>
<div class="tool"><span class="lbl"><label for="grid">Grid cell</label></span>
<select id="grid" aria-describedby="selection-state"></select></div>
<div class="tool"><span class="lbl">Valid date</span>
<span class="valid" id="valid-date">Loading</span></div>
</div>
<p id="selection-state" class="state" role="status" aria-live="polite">Loading the
verified candidate data.</p>

<div class="work">
<div class="left">
<svg id="map" viewBox="0 0 476 746" role="img" aria-label="Reference ETo on the native
weather grid. Each cell is 0.5 degrees."></svg>
<div class="ramp" aria-hidden="true"></div>
<div class="rampkey"><span id="ramp-lo">0.00</span>
<span>mm/day, fixed across lead days</span><span id="ramp-hi">0.00</span></div>
</div>
<div class="right">
<h2 style="margin-bottom:0">Selected cell</h2>
<div class="big"><span id="big-value">n/a</span><span class="unit">mm/day</span></div>
<p class="where" id="where">No selection</p>
<dl class="trip">
<div><dt>p10</dt><dd id="t-p10">n/a</dd></div>
<div><dt>p50</dt><dd id="t-p50">n/a</dd></div>
<div><dt>p90</dt><dd id="t-p90">n/a</dd></div>
</dl>
<h2>Selected-cell interval across lead days</h2>
<svg id="fan" viewBox="0 0 560 190" role="img" aria-label="p10 to p90 band and p50 line
for the selected cell across all lead days."></svg>
<p class="fine" style="margin-top:7px">Band is p10 to p90. Line is p50. The dashed
rule marks the selected lead day.</p>
<h2>Displayed layer</h2>
<p class="layerid" id="layer-id">eto_mm</p>
<p class="fine" id="layer-def">Loading the layer definition.</p>
<h2>Evidence ledger</h2>
<table class="ledger"><tbody id="ledger"><tr><th scope="row">Provenance</th>
<td>Unavailable</td></tr></tbody></table>
<p class="fine" style="margin-top:9px">Source files:
<a href="source/outlook.json">candidate JSON</a> ·
<a href="source/manifest.json">source manifest</a> ·
<a href="viewer-data.json">viewer data</a></p>
</div>
</div>

<section>
<h2>All cells, selected lead day</h2>
<div class="tblwrap"><table class="cells">
<caption class="fine">Values are millimeters per day.</caption>
<thead><tr><th scope="col">Grid</th><th scope="col" class="num">Latitude</th>
<th scope="col" class="num">Longitude</th><th scope="col" class="num">p10</th>
<th scope="col" class="num">p50</th><th scope="col" class="num">p90</th>
<th scope="col" class="num">Displayed</th><th scope="col">State</th></tr></thead>
<tbody id="cells"><tr><td colspan="8">Loading</td></tr></tbody>
</table></div>
</section>

<section>
<h2>Run locally</h2>
<p class="fine">From the repository root. The builder verifies the candidate and writes
the site manifest. This page reads local JSON. It never fetches a live forecast.</p>
<pre class="run">python3 scripts/build_eto_site.py \\
  --source-dir data/outlook/gefs_reforecast_20190703_candidate \\
  --out /tmp/mlet-eto-site
python3 -m http.server 8000 --directory /tmp/mlet-eto-site</pre>
</section>

<footer><span>MLET · reference evapotranspiration candidate</span>
<a href="../">Candidate summary</a></footer>
</main>
<script>
(function(){
  const NS='http://www.w3.org/2000/svg';
  // Viridis anchors at 0, .2, .4, .6, .8, 1. Colour appears here and nowhere else.
  const STOPS=[[68,1,84],[65,68,135],[42,120,142],[34,168,132],[122,209,81],[253,231,37]];
  const STEP=0.5;
  const byId=id=>document.getElementById(id);
  const state=byId('selection-state'),leadWrap=byId('lead'),quantWrap=byId('quantile');
  const gridSelect=byId('grid'),map=byId('map'),fan=byId('fan'),rows=byId('cells');
  const bigValue=byId('big-value'),where=byId('where'),validDate=byId('valid-date');
  const ledger=byId('ledger'),rampLo=byId('ramp-lo'),rampHi=byId('ramp-hi');
  const trip={p10:byId('t-p10'),p50:byId('t-p50'),p90:byId('t-p90')};
  let DATA=null,lead=1,quant='p50',gridId=null,lo=0,hi=1;

  const finite=v=>typeof v==='number'&&Number.isFinite(v);
  const fmt=v=>finite(v)?v.toFixed(2):'n/a';
  const withUnit=v=>finite(v)?v.toFixed(2)+' mm/day':'Unavailable';
  function colour(value){
    if(!finite(value))return 'var(--line-2)';
    const t=hi>lo?Math.max(0,Math.min(1,(value-lo)/(hi-lo))):0;
    const x=t*(STOPS.length-1),i=Math.min(STOPS.length-2,Math.floor(x)),f=x-i;
    return 'rgb('+STOPS[i].map((c,k)=>Math.round(c+(STOPS[i+1][k]-c)*f)).join(',')+')';
  }
  const dayFor=n=>DATA.days.find(day=>day.lead_day===n)||null;
  const cellIn=(day,id)=>day?day.cells.find(cell=>cell.grid_id===id)||null:null;
  const shown=cell=>cell&&cell.value?cell.value[quant]:null;
  function node(name,attrs,parent){
    const created=document.createElementNS(NS,name);
    Object.keys(attrs).forEach(key=>created.setAttribute(key,attrs[key]));
    parent.append(created);
    return created;
  }

  // One colour domain for the whole candidate keeps lead days and quantiles
  // comparable: switching either control never rescales the map.
  function computeDomain(){
    let min=Infinity,max=-Infinity;
    DATA.days.forEach(day=>day.cells.forEach(cell=>{
      if(!cell.value)return;
      ['p10','p50','p90'].forEach(key=>{
        const value=cell.value[key];
        if(finite(value)){min=Math.min(min,value);max=Math.max(max,value);}
      });
    }));
    if(!finite(min)||!finite(max)||min===max){min=0;max=1;}
    lo=min;hi=max;
    rampLo.textContent=lo.toFixed(2);
    rampHi.textContent=hi.toFixed(2);
  }

  function buildControls(){
    DATA.days.forEach(day=>{
      const button=document.createElement('button');
      button.type='button';
      button.textContent=String(day.lead_day);
      button.dataset.lead=String(day.lead_day);
      button.setAttribute('aria-pressed','false');
      button.setAttribute('aria-label','Lead day '+day.lead_day+', valid '+day.valid_date);
      button.addEventListener('click',()=>{lead=day.lead_day;render();});
      leadWrap.append(button);
    });
    Array.from(quantWrap.children).forEach(button=>{
      button.addEventListener('click',()=>{quant=button.dataset.q;render();});
    });
    const ids=new Set();
    DATA.days.forEach(day=>day.cells.forEach(cell=>ids.add(cell.grid_id)));
    Array.from(ids).sort().forEach(id=>{
      const option=document.createElement('option');
      option.value=id;
      option.textContent=id;
      gridSelect.append(option);
    });
    gridSelect.addEventListener('change',()=>{gridId=gridSelect.value;render();});
  }

  function renderMap(day){
    map.replaceChildren();
    const lats=Array.from(new Set(day.cells.map(cell=>cell.latitude))).sort((a,b)=>a-b);
    const lons=Array.from(new Set(day.cells.map(cell=>cell.longitude))).sort((a,b)=>a-b);
    const latMin=lats[0]-STEP/2,latMax=lats[lats.length-1]+STEP/2;
    const lonMin=lons[0]-STEP/2,lonMax=lons[lons.length-1]+STEP/2;
    // Longitude degrees are narrower than latitude degrees away from the equator.
    const squeeze=Math.cos((latMin+latMax)/2*Math.PI/180);
    const scale=96,left=32,top=4,right=6,bottom=20;
    const width=(lonMax-lonMin)*squeeze*scale,height=(latMax-latMin)*scale;
    map.setAttribute('viewBox','0 0 '+(left+width+right).toFixed(1)+' '+
      (top+height+bottom).toFixed(1));
    const x=lon=>left+(lon-lonMin)*squeeze*scale;
    const y=lat=>top+(latMax-lat)*scale;
    const field=node('g',{},map);
    let selected=null;
    day.cells.forEach(cell=>{
      const value=shown(cell);
      const isSelected=cell.grid_id===gridId;
      const rect=node('rect',{
        'class':isSelected?'cell sel':'cell',
        x:x(cell.longitude-STEP/2).toFixed(2),
        y:y(cell.latitude+STEP/2).toFixed(2),
        width:(STEP*squeeze*scale).toFixed(2),
        height:(STEP*scale).toFixed(2),
        fill:colour(value),
        'shape-rendering':'crispEdges',
        tabindex:'0',
        role:'button',
        'aria-pressed':String(isSelected),
        'aria-label':cell.grid_id+', '+withUnit(value)+'. Select this grid cell.'
      },field);
      node('title',{},rect).textContent=cell.grid_id+': '+withUnit(value);
      const choose=()=>{gridId=cell.grid_id;render();};
      rect.addEventListener('click',choose);
      rect.addEventListener('keydown',event=>{
        if(event.key==='Enter'||event.key===' '){event.preventDefault();choose();}
      });
      if(isSelected)selected=rect;
    });
    if(selected)field.append(selected);
    const graticule=node('g',{'class':'grat'},map);
    for(let lat=Math.ceil(latMin);lat<=Math.floor(latMax);lat+=1){
      node('line',{x1:x(lonMin),y1:y(lat),x2:x(lonMax),y2:y(lat)},graticule);
      node('text',{'class':'axis',x:left-7,y:(y(lat)+3).toFixed(1),
        'text-anchor':'end'},map).textContent=lat.toFixed(0)+'N';
    }
    for(let lon=Math.ceil(lonMin);lon<=Math.floor(lonMax);lon+=1){
      node('line',{x1:x(lon),y1:y(latMin),x2:x(lon),y2:y(latMax)},graticule);
      node('text',{'class':'axis',x:x(lon).toFixed(1),y:(top+height+13).toFixed(1),
        'text-anchor':'middle'},map).textContent=Math.abs(lon).toFixed(0)+'W';
    }
  }

  function renderFan(){
    fan.replaceChildren();
    const series=DATA.days
      .map(day=>({lead:day.lead_day,value:(cellIn(day,gridId)||{}).value}))
      .filter(point=>point.value&&finite(point.value.p10)&&finite(point.value.p90));
    if(series.length<2)return;
    let min=Infinity,max=-Infinity;
    series.forEach(point=>{
      min=Math.min(min,point.value.p10);
      max=Math.max(max,point.value.p90);
    });
    const pad=(max-min)*0.12||0.5;
    min-=pad;max+=pad;
    const width=560,height=190,left=40,right=10,top=10,bottom=26;
    const first=series[0].lead,last=series[series.length-1].lead;
    const x=value=>left+(last>first?(value-first)/(last-first):0)*(width-left-right);
    const y=value=>top+(1-(value-min)/(max-min))*(height-top-bottom);
    const point=(item,key)=>x(item.lead).toFixed(1)+','+y(item.value[key]).toFixed(1);
    const upper=series.map(item=>point(item,'p90'));
    const lower=series.slice().reverse().map(item=>point(item,'p10'));
    node('path',{'class':'band',d:'M'+upper.concat(lower).join('L')+'Z'},fan);
    node('polyline',{'class':'p50line',
      points:series.map(item=>point(item,'p50')).join(' ')},fan);
    [max-pad,min+pad].forEach(value=>{
      node('text',{'class':'axis',x:left-7,y:(y(value)+3).toFixed(1),
        'text-anchor':'end'},fan).textContent=value.toFixed(1);
    });
    [first,last].forEach(value=>{
      node('text',{'class':'axis',x:x(value).toFixed(1),y:height-6,
        'text-anchor':value===first?'start':'end'},fan).textContent='day '+value;
    });
    const active=series.find(item=>item.lead===lead);
    if(active){
      node('line',{'class':'mark',x1:x(active.lead).toFixed(1),y1:top,
        x2:x(active.lead).toFixed(1),y2:height-bottom},fan);
      node('circle',{'class':'markdot',cx:x(active.lead).toFixed(1),
        cy:y(active.value.p50).toFixed(1),r:3.4},fan);
    }
  }

  function renderTable(day){
    rows.replaceChildren();
    day.cells.forEach(cell=>{
      const value=shown(cell);
      const row=document.createElement('tr');
      const columns=[
        [cell.grid_id,''],
        [cell.latitude.toFixed(2),'num'],
        [cell.longitude.toFixed(2),'num'],
        [fmt(cell.value&&cell.value.p10),'num'],
        [fmt(cell.value&&cell.value.p50),'num'],
        [fmt(cell.value&&cell.value.p90),'num'],
        [fmt(value),'num'],
        [finite(value)?'available':'missing','']
      ];
      columns.forEach(column=>{
        const td=document.createElement('td');
        td.textContent=column[0];
        if(column[1])td.className=column[1];
        row.append(td);
      });
      rows.append(row);
    });
  }

  function renderLedger(){
    const source=DATA.provenance;
    ledger.replaceChildren();
    [['Run ID',DATA.run.run_id],['Issue time',DATA.run.issued_at],
     ['Retrieved at',source.retrieved_at],['Git revision',source.git_revision],
     ['Candidate SHA-256',source.candidate_sha256],
     ['Source manifest SHA-256',source.source_manifest_sha256],
     ['GEFS artifact SHA-256',source.upstream_sha256],
     ['Upstream source',source.upstream_uri]].forEach(pair=>{
      const row=document.createElement('tr');
      const label=document.createElement('th');
      label.scope='row';
      label.textContent=pair[0];
      const value=document.createElement('td');
      value.textContent=pair[1];
      row.append(label,value);
      ledger.append(row);
    });
  }

  function clear(message){
    state.textContent=message;
    map.replaceChildren();
    fan.replaceChildren();
    rows.replaceChildren();
    bigValue.textContent='n/a';
    where.textContent='No selection';
    ['p10','p50','p90'].forEach(key=>{trip[key].textContent='n/a';});
  }

  function render(){
    const day=dayFor(lead);
    Array.from(leadWrap.children).forEach(button=>{
      button.setAttribute('aria-pressed',String(Number(button.dataset.lead)===lead));
    });
    Array.from(quantWrap.children).forEach(button=>{
      button.setAttribute('aria-pressed',String(button.dataset.q===quant));
    });
    if(!day||!day.cells.length){
      validDate.textContent='n/a';
      clear('No grid data for this selection.');
      return;
    }
    validDate.textContent=day.valid_date;
    if(!gridId||!cellIn(day,gridId))gridId=day.cells[0].grid_id;
    gridSelect.value=gridId;
    const cell=cellIn(day,gridId);
    renderMap(day);
    renderFan();
    renderTable(day);
    bigValue.textContent=fmt(shown(cell));
    where.textContent=cell.grid_id+' · '+cell.latitude.toFixed(2)+', '+
      cell.longitude.toFixed(2)+' · '+day.valid_date+' · '+quant;
    ['p10','p50','p90'].forEach(key=>{
      trip[key].textContent=fmt(cell.value&&cell.value[key]);
    });
    state.textContent='Showing '+day.cells.length+' grid cells for lead day '+
      day.lead_day+' on '+day.valid_date+'. Selected '+cell.grid_id+'.';
  }

  function start(data){
    DATA=data;
    if(DATA.days.length)lead=DATA.days[0].lead_day;
    byId('layer-id').textContent=DATA.layer.id+' · '+DATA.layer.units;
    byId('layer-def').textContent=DATA.layer.definition;
    computeDomain();
    buildControls();
    renderLedger();
    render();
  }

  fetch('viewer-data.json')
    .then(response=>{
      if(!response.ok)throw new Error('viewer data unavailable');
      return response.json();
    })
    .then(start)
    .catch(()=>{
      state.textContent='Viewer data unavailable. Serve this site over HTTP and '+
        'reload the page.';
    });
})();
</script></body></html>
"""


def _viewer_html() -> str:
    return (
        '<!doctype html>\n<html lang="en">\n<head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>MLET ETo grid viewer</title>\n<style>"
        + _CSS
        + _VIEWER_CSS
        + "</style></head>"
        + _VIEWER_BODY
    )
