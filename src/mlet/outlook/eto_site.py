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


def _root_html(
    viewer_data: dict[str, object], candidate_sha256: str, source_manifest_sha256: str
) -> str:
    run = viewer_data["run"]
    assert isinstance(run, dict)
    provenance = viewer_data["provenance"]
    assert isinstance(provenance, dict)
    days = viewer_data["days"]
    assert isinstance(days, list)
    fields = (
        ("run ID", run["run_id"]),
        ("issued at", run["issued_at"]),
        ("Git revision", provenance["git_revision"]),
        ("candidate SHA-256", candidate_sha256),
        ("source manifest SHA-256", source_manifest_sha256),
        ("GEFS artifact SHA-256", provenance["upstream_sha256"]),
    )
    rows = "".join(
        f"<tr><th scope=\"row\">{html.escape(str(label))}</th><td>{html.escape(str(value))}</td></tr>"
        for label, value in fields
    )
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MLET ETo research candidate</title>
<style>
:root {{ color-scheme: light dark; --paper:#f1ecdf; --panel:#fcfbf7; --ink:#17252e; --muted:#5d6870; --line:#c9c1b3; --navy:#173f54; --rust:#b45132; --gold:#d7a43e; --warn:#704918; --warn-bg:#f7e8c9; }}
@media (prefers-color-scheme: dark) {{ :root {{ --paper:#121a1e; --panel:#1a252a; --ink:#edf1ed; --muted:#aeb9bc; --line:#425058; --navy:#8ec7d8; --rust:#e48a67; --gold:#ebc56f; --warn:#f0c889; --warn-bg:#302719; }} }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--paper); color:var(--ink); font:16px/1.55 system-ui,sans-serif; }} main {{ max-width:980px; margin:auto; padding:28px 20px 68px; }} .eyebrow {{ color:var(--rust); font:700 12px/1.2 ui-monospace,monospace; letter-spacing:.14em; text-transform:uppercase; }} h1 {{ margin:8px 0 10px; max-width:18ch; font:700 clamp(2.3rem,6vw,4.8rem)/.98 Georgia,serif; letter-spacing:-.04em; }} h2 {{ margin:34px 0 10px; font-size:1.05rem; }} a {{ color:var(--navy); }} .dek {{ max-width:62ch; color:var(--muted); font-size:1.08rem; }} .banner {{ padding:15px 17px; border-left:5px solid var(--rust); background:var(--warn-bg); }} .status {{ display:flex; gap:8px; flex-wrap:wrap; margin:20px 0 24px; }} .chip {{ border:1px solid var(--line); border-radius:3px; padding:5px 9px; font:12px ui-monospace,monospace; }} .stats {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:25px 0; }} .stat {{ padding:14px; border-top:3px solid var(--navy); background:var(--panel); }} .stat strong {{ display:block; font:700 1.7rem/1.1 Georgia,serif; }} .stat span {{ display:block; margin-top:5px; color:var(--muted); font-size:.88rem; }} .ledger {{ border-top:1px solid var(--line); border-bottom:1px solid var(--line); }} table {{ border-collapse:collapse; width:100%; }} th,td {{ border-bottom:1px solid var(--line); padding:10px; text-align:left; vertical-align:top; }} th {{ width:220px; color:var(--muted); font-weight:600; }} code {{ overflow-wrap:anywhere; font:12px ui-monospace,monospace; }} pre {{ overflow:auto; padding:14px 16px; border:1px solid var(--line); background:var(--panel); color:var(--ink); font:13px/1.6 ui-monospace,monospace; }} .note {{ color:var(--muted); font-size:.9rem; }} .button {{ display:inline-block; margin-top:12px; padding:10px 15px; border:1px solid var(--navy); background:var(--navy); color:var(--paper); text-decoration:none; }} .boundary {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }} .boundary div {{ padding:14px; border:1px solid var(--line); background:var(--panel); }} .boundary strong {{ display:block; margin-bottom:5px; color:var(--rust); }} @media (max-width:680px) {{ main {{ padding:22px 14px 52px; }} .stats,.boundary {{ grid-template-columns:1fr; }} }}
</style></head>
<body><main>
<p class="eyebrow">MLET / research artifact</p>
<h1>One archived issue. One clear evidence boundary.</h1>
<p class="dek">A static viewer for the 2019-07-03 GEFSv12 ETo candidate. Read it as a reproducibility record, not as a live forecast product.</p>
<p class="banner"><strong>Research candidate.</strong> This artifact is not validated, promoted, or an operational irrigation recommendation.</p>
<div class="status"><span class="chip">research_candidate</span><span class="chip">evaluation_pending</span><span class="chip">not_promoted</span></div>
<section class="stats" aria-label="Artifact summary"><div class="stat"><strong>{html.escape(str(run["issued_at"]))}</strong><span>GEFS issue time</span></div><div class="stat"><strong>{len(days)}</strong><span>lead dates, each in mm/day</span></div><div class="stat"><strong>{html.escape(str(viewer_data["grid_count"]))}</strong><span>native weather-grid cells</span></div></section>
<div class="boundary"><div><strong>Use this page to</strong>inspect ETo quantiles, source identity, issue time, and file checksums.</div><div><strong>Do not use this page to</strong>claim forecast skill, define field boundaries, or make irrigation decisions.</div></div>
<a class="button" href="outlook/">Open the ETo viewer</a>
<h2>Evidence ledger</h2><div class="ledger"><table><tbody>{rows}</tbody></table></div>
<p><a href="outlook/source/outlook.json">Candidate JSON</a> · <a href="outlook/source/manifest.json">Source manifest</a> · <a href="outlook/viewer-data.json">Viewer data</a></p>
<h2>Run locally</h2><p>Run these commands from the repository root. The builder checks the candidate and writes a self-contained static site.</p><pre><code>python3 scripts/build_eto_site.py --source-dir data/outlook/gefs_reforecast_20190703_candidate --out /tmp/mlet-eto-site
python3 -m http.server 8000 --directory /tmp/mlet-eto-site
open http://localhost:8000/</code></pre><p class="note">The site reads local JSON files. Serve it over HTTP because browsers block local fetch requests from a file path.</p>
</main></body></html>
"""


def _viewer_html() -> str:
    return """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MLET ETo viewer</title>
<style>
:root { color-scheme: light dark; --paper:#f1ecdf; --panel:#fcfbf7; --ink:#17252e; --muted:#5d6870; --line:#c9c1b3; --navy:#173f54; --rust:#b45132; --gold:#d7a43e; --no-data:#66737a; --warn:#704918; --warn-bg:#f7e8c9; }
@media (prefers-color-scheme: dark) { :root { --paper:#121a1e; --panel:#1a252a; --ink:#edf1ed; --muted:#aeb9bc; --line:#425058; --navy:#8ec7d8; --rust:#e48a67; --gold:#ebc56f; --no-data:#aeb9bc; --warn:#f0c889; --warn-bg:#302719; } }
* { box-sizing:border-box; } body { margin:0; background:var(--paper); color:var(--ink); font:15px/1.5 system-ui,sans-serif; } main { max-width:1220px; margin:auto; padding:24px 18px 60px; } .eyebrow { color:var(--rust); font:700 12px/1.2 ui-monospace,monospace; letter-spacing:.14em; text-transform:uppercase; } h1 { margin:8px 0; font:700 clamp(2.1rem,5vw,4.2rem)/.98 Georgia,serif; letter-spacing:-.04em; } h2 { font-size:1.05rem; margin:30px 0 10px; } a { color:var(--navy); } button,select { font:inherit; } .dek { max-width:70ch; color:var(--muted); font-size:1.04rem; } .banner { border-left:5px solid var(--rust); background:var(--warn-bg); padding:13px 15px; margin:18px 0; } .chips { display:flex; flex-wrap:wrap; gap:8px; margin:14px 0 22px; } .chip { border:1px solid var(--line); border-radius:3px; padding:5px 9px; font:12px ui-monospace,monospace; } .boundary { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin:16px 0 22px; } .boundary div { padding:13px 15px; border:1px solid var(--line); background:var(--panel); } .boundary strong { display:block; margin-bottom:4px; color:var(--rust); } .controls { display:grid; grid-template-columns:repeat(3,minmax(140px,1fr)); gap:13px; align-items:end; padding:15px; border:1px solid var(--line); background:var(--panel); } label,legend { color:var(--muted); font-weight:600; } select { display:block; width:100%; min-width:0; margin-top:5px; padding:8px 9px; color:var(--ink); background:var(--paper); border:1px solid var(--line); border-radius:3px; } fieldset { border:0; padding:0; margin:0; min-width:0; } fieldset label { display:inline-flex; gap:6px; margin:9px 13px 0 0; color:var(--ink); font-weight:400; } input:focus-visible,select:focus-visible { outline:3px solid var(--gold); outline-offset:2px; } .check { align-self:center; color:var(--ink); font-weight:400; } .summary { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:14px; } .card { border:1px solid var(--line); padding:15px; background:var(--panel); } .value { font:700 1.8rem/1.1 Georgia,serif; } .subtle { color:var(--muted); } .state { min-height:1.6em; margin:12px 0; color:var(--muted); } .map-wrap { overflow:auto; border:1px solid var(--line); background:var(--panel); } svg { display:block; width:100%; min-width:640px; height:430px; } .dot { cursor:pointer; stroke:var(--panel); stroke-width:1.2; } .dot:hover,.dot:focus { stroke:var(--rust); stroke-width:2.5; outline:none; } .dot.selected { stroke:var(--gold); stroke-width:3; } .legend { display:flex; align-items:center; gap:9px; margin-top:9px; color:var(--muted); font:12px ui-monospace,monospace; } .legend-bar { width:180px; height:10px; background:linear-gradient(90deg,#440154,#365c8d,#21918c,#7ad151,#fde725); } .table-wrap { overflow:auto; max-height:430px; border:1px solid var(--line); background:var(--panel); } table { border-collapse:collapse; width:100%; min-width:760px; } th,td { border-bottom:1px solid var(--line); padding:8px 9px; text-align:left; white-space:nowrap; } th { position:sticky; top:0; background:var(--panel); color:var(--muted); font-size:12px; } td { font-variant-numeric:tabular-nums; } .provenance { overflow-wrap:anywhere; } .provenance code { font:12px ui-monospace,monospace; } .interval { height:10px; margin-top:9px; border:1px solid var(--line); position:relative; background:var(--paper); } .interval span { position:absolute; top:0; bottom:0; background:var(--navy); } pre { overflow:auto; padding:14px 16px; border:1px solid var(--line); background:var(--panel); font:13px/1.6 ui-monospace,monospace; } .hidden { display:none; } @media (prefers-reduced-motion: reduce) { * { scroll-behavior:auto !important; } } @media (max-width:720px) { main { padding:21px 12px 48px; } .boundary,.summary { grid-template-columns:1fr; } .controls { grid-template-columns:1fr; } svg { height:340px; } }
</style></head>
<body><main>
<p class="eyebrow"><a href="../">MLET</a> / research artifact</p>
<h1>Inspect the archived weather grid</h1>
<p class="dek">This page shows one ETo candidate from one archived issue. Use the controls to inspect a lead date, quantile, and grid cell.</p>
<p class="banner"><strong>Research candidate.</strong> Values are not validated or promoted. The grid is a weather reference. It is not a field boundary, a field measurement, or an irrigation recommendation.</p>
<div class="chips" aria-label="Candidate status"><span class="chip">production_status: research_candidate</span><span class="chip">validation_status: evaluation_pending</span><span class="chip">promotion_status: not_promoted</span></div>
<div class="boundary"><div><strong>What the values mean</strong>ASCE short-reference ETo quantiles in millimeters per day on the native GEFS grid.</div><div><strong>What the values do not mean</strong>They do not report observed ET, crop ET, field conditions, or forecast skill.</div></div>
<section class="controls" aria-label="Viewer controls">
<label for="lead">Lead day<select id="lead" aria-describedby="selection-state"></select></label>
<label for="date">Valid date<select id="date" aria-describedby="selection-state"></select></label>
<label for="grid">Grid cell<select id="grid" aria-describedby="selection-state"></select></label>
<fieldset><legend>Displayed quantile</legend><label><input type="radio" name="quantile" value="p10"> p10</label><label><input type="radio" name="quantile" value="p50" checked> p50</label><label><input type="radio" name="quantile" value="p90"> p90</label></fieldset>
<label class="check"><input id="show-interval" type="checkbox" checked> Show selected-cell interval</label>
</section>
<p id="selection-state" class="state" role="status" aria-live="polite">Loading the verified candidate data.</p>
<section class="summary" aria-label="Selected ETo summary"><div class="card"><div class="subtle">Selected grid cell</div><div id="selected-value" class="value">Unavailable</div><div id="selected-label" class="subtle">No selection</div></div><div id="interval-card" class="card"><div class="subtle">Selected-cell p10 to p90</div><div id="interval-text" class="value">Unavailable</div><div class="interval" aria-hidden="true"><span id="interval-bar"></span></div></div></section>
<h2>Native grid view</h2><div class="map-wrap"><svg id="map" viewBox="0 0 900 430" role="img" aria-label="ETo values on the native weather grid"></svg></div><div class="legend" aria-label="Fixed color reference"><span>2 mm/day</span><span class="legend-bar" aria-hidden="true"></span><span>10 mm/day</span><span>fixed color reference</span></div>
<h2>Accessible cell table</h2><div class="table-wrap"><table><caption class="subtle">All cells for the selected lead date. Values are millimeters per day.</caption><thead><tr><th scope="col">Grid</th><th scope="col">Latitude</th><th scope="col">Longitude</th><th scope="col">p10</th><th scope="col">p50</th><th scope="col">p90</th><th scope="col">Displayed</th><th scope="col">State</th></tr></thead><tbody id="cells"><tr><td colspan="8">Loading</td></tr></tbody></table></div>
<h2>Evidence ledger</h2><div class="card provenance" id="provenance">Provenance unavailable.</div>
<p class="subtle">Source files: <a href="source/outlook.json">candidate JSON</a> · <a href="source/manifest.json">source manifest</a> · <a href="viewer-data.json">viewer data</a></p>
<h2>Run locally</h2><p>From the repository root, build the site and serve the output over HTTP.</p><pre><code>python3 scripts/build_eto_site.py --source-dir data/outlook/gefs_reforecast_20190703_candidate --out /tmp/mlet-eto-site
python3 -m http.server 8000 --directory /tmp/mlet-eto-site
open http://localhost:8000/</code></pre><p class="subtle">The builder verifies the candidate and writes the site manifest. The page reads local JSON files. It does not fetch a live forecast.</p>
</main>
<script>
(function(){
  const state=document.getElementById('selection-state');
  const lead=document.getElementById('lead');
  const date=document.getElementById('date');
  const grid=document.getElementById('grid');
  const map=document.getElementById('map');
  const cells=document.getElementById('cells');
  const selectedValue=document.getElementById('selected-value');
  const selectedLabel=document.getElementById('selected-label');
  const intervalText=document.getElementById('interval-text');
  const intervalBar=document.getElementById('interval-bar');
  const intervalCard=document.getElementById('interval-card');
  const provenance=document.getElementById('provenance');
  const showInterval=document.getElementById('show-interval');
  const svg='http://www.w3.org/2000/svg';
  const colors=[[68,1,84],[54,92,141],[33,145,140],[122,209,81],[253,231,37]];
  function color(value){const t=Math.max(0,Math.min(1,(value-2)/8));const x=t*(colors.length-1),i=Math.min(colors.length-2,Math.floor(x)),f=x-i;return 'rgb('+colors[i].map((v,k)=>Math.round(v+(colors[i+1][k]-v)*f)).join(',')+')';}
  function format(value){return typeof value==='number'&&Number.isFinite(value)?value.toFixed(2)+' mm/day':'Unavailable';}
  function quantile(){const item=document.querySelector('input[name="quantile"]:checked');return item?item.value:'p50';}
  function current(){return DATA.days.find(item=>item.lead_day===Number(lead.value)&&item.valid_date===date.value)||null;}
  function populate(){const gridIds=new Set();DATA.days.forEach(item=>{const l=document.createElement('option');l.value=String(item.lead_day);l.textContent='Day '+item.lead_day;lead.append(l);const d=document.createElement('option');d.value=item.valid_date;d.textContent=item.valid_date;date.append(d);item.cells.forEach(cell=>gridIds.add(cell.grid_id));});Array.from(gridIds).sort().forEach(gridId=>{const option=document.createElement('option');option.value=gridId;option.textContent=gridId;grid.append(option);});if(DATA.days.length){lead.value=String(DATA.days[0].lead_day);date.value=DATA.days[0].valid_date;if(grid.options.length){grid.value=grid.options[0].value;}}}
  function selectDayFromLead(){const item=DATA.days.find(value=>value.lead_day===Number(lead.value));if(item){date.value=item.valid_date;}}
  function selectLeadFromDate(){const item=DATA.days.find(value=>value.valid_date===date.value);if(item){lead.value=String(item.lead_day);}}
  function chooseGrid(gridId){grid.value=gridId;draw();}
  function draw(){const day=current();map.replaceChildren();cells.replaceChildren();if(!day||!day.cells.length){state.textContent='No grid data for this selection.';selectedValue.textContent='Unavailable';selectedLabel.textContent='No data';intervalText.textContent='Unavailable';intervalBar.style.left='0%';intervalBar.style.width='0%';return;}const selected=quantile();const focusGrid=grid.value||day.cells[0].grid_id;const focusCell=day.cells.find(item=>item.grid_id===focusGrid)||day.cells[0];const minX=Math.min(...day.cells.map(item=>item.longitude),-117),maxX=Math.max(...day.cells.map(item=>item.longitude),-111),minY=Math.min(...day.cells.map(item=>item.latitude),42),maxY=Math.max(...day.cells.map(item=>item.latitude),49),xSpan=maxX-minX||1,ySpan=maxY-minY||1;day.cells.forEach(item=>{const value=item.value&&item.value[selected];const isSelected=item.grid_id===focusCell.grid_id;const circle=document.createElementNS(svg,'circle');circle.setAttribute('class',isSelected?'dot selected':'dot');circle.setAttribute('cx',String(45+(item.longitude-minX)/xSpan*810));circle.setAttribute('cy',String(390-(item.latitude-minY)/ySpan*350));circle.setAttribute('r',isSelected?'10':'8');circle.setAttribute('fill',typeof value==='number'?color(value):'var(--no-data)');circle.setAttribute('tabindex','0');circle.setAttribute('role','button');circle.setAttribute('aria-pressed',String(isSelected));circle.setAttribute('aria-label',item.grid_id+' '+format(value)+'. Select grid cell.');circle.addEventListener('click',function(){chooseGrid(item.grid_id);});circle.addEventListener('keydown',function(event){if(event.key==='Enter'||event.key===' '){event.preventDefault();chooseGrid(item.grid_id);}});const title=document.createElementNS(svg,'title');title.textContent=item.grid_id+': '+format(value);circle.append(title);map.append(circle);const row=document.createElement('tr');[item.grid_id,item.latitude.toFixed(2),item.longitude.toFixed(2),format(item.value&&item.value.p10),format(item.value&&item.value.p50),format(item.value&&item.value.p90),format(value),typeof value==='number'?'available':'missing'].forEach(text=>{const cell=document.createElement('td');cell.textContent=text;row.append(cell);});cells.append(row);});const focusValue=focusCell.value&&focusCell.value[selected];selectedValue.textContent=format(focusValue);selectedLabel.textContent='Grid '+focusCell.grid_id+' · '+focusCell.latitude.toFixed(2)+', '+focusCell.longitude.toFixed(2)+' · '+day.valid_date+' · '+selected;const interval=focusCell.value&&focusCell.value.p10!==undefined&&focusCell.value.p90!==undefined?[focusCell.value.p10,focusCell.value.p90]:null;if(interval&&typeof interval[0]==='number'&&typeof interval[1]==='number'){const lower=interval[0],upper=interval[1];intervalText.textContent=lower.toFixed(2)+' to '+upper.toFixed(2)+' mm/day';const scale=Math.max(upper,8);intervalBar.style.left=Math.max(0,lower/scale*100)+'%';intervalBar.style.width=Math.max(1,(upper-lower)/scale*100)+'%';}else{intervalText.textContent='Unavailable';intervalBar.style.left='0%';intervalBar.style.width='0%';}state.textContent='Showing '+day.cells.length+' grid cells for lead day '+day.lead_day+' on '+day.valid_date+'. Selected '+focusCell.grid_id+'.';}
  function renderProvenance(){const p=DATA.provenance;provenance.replaceChildren();[['Run ID',DATA.run.run_id],['Issue time',DATA.run.issued_at],['Retrieved at',p.retrieved_at],['Git revision',p.git_revision],['Candidate SHA-256',p.candidate_sha256],['Source manifest SHA-256',p.source_manifest_sha256],['GEFS artifact SHA-256',p.upstream_sha256],['Upstream URI',p.upstream_uri]].forEach(pair=>{const paragraph=document.createElement('p');const strong=document.createElement('strong');strong.textContent=pair[0]+': ';const code=document.createElement('code');code.textContent=pair[1];paragraph.append(strong,code);provenance.append(paragraph);});}
  function start(data){window.DATA=data;populate();renderProvenance();lead.addEventListener('change',function(){selectDayFromLead();draw();});date.addEventListener('change',function(){selectLeadFromDate();draw();});grid.addEventListener('change',draw);showInterval.addEventListener('change',function(){intervalCard.classList.toggle('hidden',!showInterval.checked);draw();});document.querySelectorAll('input[name="quantile"]').forEach(item=>item.addEventListener('change',draw));draw();intervalCard.classList.toggle('hidden',!showInterval.checked);}
  fetch('viewer-data.json').then(response=>{if(!response.ok)throw new Error('viewer data unavailable');return response.json();}).then(start).catch(()=>{state.textContent='Viewer data unavailable. Serve this site over HTTP and reload the page.';});
})();
</script></body></html>
"""
