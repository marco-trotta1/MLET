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
:root {{ color-scheme: light dark; --bg:#f8f8f5; --surface:#fff; --ink:#202522; --muted:#5f6862; --line:#d8ddd8; --accent:#126c68; --warn:#7a4a08; --warn-bg:#fff4df; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#111413; --surface:#1b201d; --ink:#e9ece8; --muted:#a9b1aa; --line:#3a423d; --accent:#71d0c6; --warn:#f0bf73; --warn-bg:#302415; }} }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.55 system-ui,sans-serif; }} main {{ max-width:920px; margin:auto; padding:32px 20px 64px; }} h1 {{ line-height:1.15; max-width:22ch; }} h2 {{ margin-top:32px; font-size:1rem; }} a {{ color:var(--accent); }} .banner {{ padding:14px 16px; border:1px solid var(--warn); background:var(--warn-bg); border-radius:8px; }} .status {{ display:flex; gap:8px; flex-wrap:wrap; margin:20px 0; }} .chip {{ border:1px solid var(--line); border-radius:99px; padding:4px 10px; font:13px ui-monospace,monospace; }} table {{ border-collapse:collapse; width:100%; }} th,td {{ border-bottom:1px solid var(--line); padding:9px 10px; text-align:left; vertical-align:top; }} th {{ width:220px; color:var(--muted); font-weight:600; }} code {{ overflow-wrap:anywhere; }} .button {{ display:inline-block; margin-top:18px; padding:9px 14px; border-radius:6px; background:var(--accent); color:#fff; text-decoration:none; }}
</style></head>
<body><main>
<p><strong>MLET</strong> · Idaho ETo outlook</p>
<h1>GEFS research candidate</h1>
<p class="banner"><strong>Research candidate.</strong> This artifact is not validated, promoted, or an operational irrigation recommendation.</p>
<div class="status"><span class="chip">research_candidate</span><span class="chip">evaluation_pending</span><span class="chip">not_promoted</span></div>
<p>One real GEFS issue supplies 20 lead dates on the native weather grid. Values are ASCE short-reference ETo in millimeters per day.</p>
<a class="button" href="outlook/">Open the ETo viewer</a>
<h2>Provenance</h2><table><tbody>{rows}</tbody></table>
<p><a href="outlook/source/outlook.json">Candidate JSON</a> · <a href="outlook/source/manifest.json">Source manifest</a> · <a href="outlook/viewer-data.json">Viewer data</a></p>
</main></body></html>
"""


def _viewer_html() -> str:
    return """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MLET ETo viewer</title>
<style>
:root { color-scheme: light dark; --bg:#f8f8f5; --surface:#fff; --ink:#202522; --muted:#5f6862; --line:#d8ddd8; --accent:#126c68; --no-data:#69716c; --warn:#7a4a08; --warn-bg:#fff4df; }
@media (prefers-color-scheme: dark) { :root { --bg:#111413; --surface:#1b201d; --ink:#e9ece8; --muted:#a9b1aa; --line:#3a423d; --accent:#71d0c6; --no-data:#a9b1aa; --warn:#f0bf73; --warn-bg:#302415; } }
* { box-sizing:border-box; } body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 system-ui,sans-serif; } main { max-width:1180px; margin:auto; padding:24px 18px 56px; } h1 { margin:4px 0 8px; line-height:1.15; } h2 { font-size:1rem; margin:26px 0 10px; } a { color:var(--accent); } button,select { font:inherit; } .banner { border:1px solid var(--warn); background:var(--warn-bg); border-radius:8px; padding:12px 14px; margin:18px 0; } .chips { display:flex; flex-wrap:wrap; gap:8px; margin:14px 0 22px; } .chip { border:1px solid var(--line); border-radius:99px; padding:4px 9px; font:12px ui-monospace,monospace; } .controls { display:flex; flex-wrap:wrap; gap:14px; align-items:end; padding:14px; border:1px solid var(--line); border-radius:8px; background:var(--surface); } label,legend { color:var(--muted); font-weight:600; } select { display:block; min-width:150px; margin-top:4px; padding:7px 9px; color:var(--ink); background:var(--surface); border:1px solid var(--line); border-radius:5px; } fieldset { border:0; padding:0; margin:0; min-width:190px; } fieldset label { display:inline-flex; gap:6px; margin:8px 12px 0 0; color:var(--ink); font-weight:400; } input:focus-visible,select:focus-visible,button:focus-visible { outline:3px solid var(--accent); outline-offset:2px; } .summary { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:18px; } .card { border:1px solid var(--line); border-radius:8px; padding:14px; background:var(--surface); } .value { font-size:1.9rem; font-weight:700; } .subtle { color:var(--muted); } .state { min-height:1.6em; margin:12px 0; color:var(--muted); } .map-wrap { overflow:auto; border:1px solid var(--line); border-radius:8px; background:var(--surface); } svg { display:block; width:100%; min-width:640px; height:430px; } .dot { stroke:var(--surface); stroke-width:1.2; } .dot:hover { stroke:var(--ink); stroke-width:2.5; } .table-wrap { overflow:auto; max-height:430px; border:1px solid var(--line); border-radius:8px; background:var(--surface); } table { border-collapse:collapse; width:100%; min-width:720px; } th,td { border-bottom:1px solid var(--line); padding:8px 9px; text-align:left; white-space:nowrap; } th { position:sticky; top:0; background:var(--surface); color:var(--muted); font-size:12px; } td { font-variant-numeric:tabular-nums; } .provenance { overflow-wrap:anywhere; } .provenance code { font:12px ui-monospace,monospace; } .interval { height:10px; margin-top:8px; border:1px solid var(--line); border-radius:99px; position:relative; background:var(--bg); } .interval span { position:absolute; top:0; bottom:0; background:var(--accent); border-radius:99px; } .hidden { display:none; } @media (max-width:680px) { main { padding:18px 12px 42px; } .controls,.summary { grid-template-columns:1fr; display:grid; } .controls label,.controls fieldset { min-width:0; width:100%; } select { width:100%; } svg { height:340px; } }
</style></head>
<body><main>
<p><a href="../">MLET</a> · ETo research viewer</p>
<h1>GEFS ETo research candidate</h1>
<p class="banner"><strong>Research candidate.</strong> Values are not validated or promoted. The grid is a weather reference and is not a field boundary or an irrigation recommendation.</p>
<div class="chips" aria-label="Candidate status"><span class="chip">production_status: research_candidate</span><span class="chip">validation_status: evaluation_pending</span><span class="chip">promotion_status: not_promoted</span></div>
<section class="controls" aria-label="Viewer controls">
<label for="lead">Lead day<select id="lead" aria-describedby="selection-state"></select></label>
<label for="date">Valid date<select id="date" aria-describedby="selection-state"></select></label>
<fieldset><legend>Displayed quantile</legend><label><input type="radio" name="quantile" value="p10"> p10</label><label><input type="radio" name="quantile" value="p50" checked> p50</label><label><input type="radio" name="quantile" value="p90"> p90</label></fieldset>
<label><input id="show-interval" type="checkbox" checked> Show p10-p90 interval</label>
</section>
<p id="selection-state" class="state" role="status" aria-live="polite">Loading the verified candidate data.</p>
<section class="summary" aria-label="Selected ETo summary"><div class="card"><div class="subtle">Selected value</div><div id="selected-value" class="value">Unavailable</div><div id="selected-label" class="subtle">No selection</div></div><div id="interval-card" class="card"><div class="subtle">Uncertainty interval</div><div id="interval-text" class="value">Unavailable</div><div class="interval" aria-hidden="true"><span id="interval-bar"></span></div></div></section>
<h2>Native grid view</h2><div class="map-wrap"><svg id="map" viewBox="0 0 900 430" role="img" aria-label="ETo values on the native weather grid"></svg></div>
<h2>Accessible cell table</h2><div class="table-wrap"><table><caption class="subtle">All cells for the selected lead date. Values are millimeters per day.</caption><thead><tr><th scope="col">Grid</th><th scope="col">Latitude</th><th scope="col">Longitude</th><th scope="col">p10</th><th scope="col">p50</th><th scope="col">p90</th><th scope="col">Selected</th><th scope="col">State</th></tr></thead><tbody id="cells"><tr><td colspan="8">Loading</td></tr></tbody></table></div>
<h2>Provenance</h2><div class="card provenance" id="provenance">Provenance unavailable.</div>
<p class="subtle">Source files: <a href="source/outlook.json">candidate JSON</a> · <a href="source/manifest.json">source manifest</a> · <a href="viewer-data.json">viewer data</a></p>
</main>
<script>
(function(){
  const state=document.getElementById('selection-state');
  const lead=document.getElementById('lead');
  const date=document.getElementById('date');
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
  function populate(){DATA.days.forEach(item=>{const l=document.createElement('option');l.value=String(item.lead_day);l.textContent='Day '+item.lead_day;lead.append(l);const d=document.createElement('option');d.value=item.valid_date;d.textContent=item.valid_date;date.append(d);});if(DATA.days.length){lead.value=String(DATA.days[0].lead_day);date.value=DATA.days[0].valid_date;}}
  function draw(){const day=current();map.replaceChildren();cells.replaceChildren();if(!day||!day.cells.length){state.textContent='No grid data for this selection.';selectedValue.textContent='Unavailable';selectedLabel.textContent='No data';intervalText.textContent='Unavailable';return;}const selected=quantile();const values=day.cells.map(item=>item.value&&item.value[selected]).filter(value=>typeof value==='number');const minX=Math.min(...day.cells.map(item=>item.longitude),-117),maxX=Math.max(...day.cells.map(item=>item.longitude),-111),minY=Math.min(...day.cells.map(item=>item.latitude),42),maxY=Math.max(...day.cells.map(item=>item.latitude),49);day.cells.forEach(item=>{const value=item.value&&item.value[selected];const circle=document.createElementNS(svg,'circle');circle.setAttribute('class','dot');circle.setAttribute('cx',String(45+(item.longitude-minX)/(maxX-minX)*810));circle.setAttribute('cy',String(390-(item.latitude-minY)/(maxY-minY)*350));circle.setAttribute('r','8');circle.setAttribute('fill',typeof value==='number'?color(value):'var(--no-data)');circle.setAttribute('aria-label',item.grid_id+' '+format(value));const title=document.createElementNS(svg,'title');title.textContent=item.grid_id+': '+format(value);circle.append(title);map.append(circle);const row=document.createElement('tr');[item.grid_id,item.latitude.toFixed(2),item.longitude.toFixed(2),format(item.value&&item.value.p10),format(item.value&&item.value.p50),format(item.value&&item.value.p90),format(value),typeof value==='number'?'available':'missing'].forEach(text=>{const cell=document.createElement('td');cell.textContent=text;row.append(cell);});cells.append(row);});const first=day.cells[0].value;const focusValue=first&&first[selected];selectedValue.textContent=format(focusValue);selectedLabel.textContent='Grid '+day.cells[0].grid_id+' · '+day.valid_date+' · '+selected;const interval=day.cells.map(item=>item.value).filter(Boolean).map(value=>[value.p10,value.p90]).filter(value=>typeof value[0]==='number'&&typeof value[1]==='number');if(interval.length){const lower=Math.min(...interval.map(value=>value[0])),upper=Math.max(...interval.map(value=>value[1]));intervalText.textContent=lower.toFixed(2)+' to '+upper.toFixed(2)+' mm/day';const scale=Math.max(upper,8);intervalBar.style.left=Math.max(0,lower/scale*100)+'%';intervalBar.style.width=Math.max(1,(upper-lower)/scale*100)+'%';}else{intervalText.textContent='Unavailable';}state.textContent='Showing '+day.cells.length+' grid cells for lead day '+day.lead_day+' on '+day.valid_date+'.';}
  function renderProvenance(){const p=DATA.provenance;provenance.replaceChildren();[['Run ID',DATA.run.run_id],['Issue time',DATA.run.issued_at],['Retrieved at',p.retrieved_at],['Git revision',p.git_revision],['Candidate SHA-256',p.candidate_sha256],['Source manifest SHA-256',p.source_manifest_sha256],['GEFS artifact SHA-256',p.upstream_sha256],['Upstream URI',p.upstream_uri]].forEach(pair=>{const paragraph=document.createElement('p');const strong=document.createElement('strong');strong.textContent=pair[0]+': ';const code=document.createElement('code');code.textContent=pair[1];paragraph.append(strong,code);provenance.append(paragraph);});}
  function start(data){window.DATA=data;populate();renderProvenance();[lead,date,showInterval].forEach(item=>item.addEventListener('change',function(){intervalCard.classList.toggle('hidden',!showInterval.checked);draw();}));document.querySelectorAll('input[name="quantile"]').forEach(item=>item.addEventListener('change',draw));draw();intervalCard.classList.toggle('hidden',!showInterval.checked);}
  fetch('viewer-data.json').then(response=>{if(!response.ok)throw new Error('viewer data unavailable');return response.json();}).then(start).catch(()=>{state.textContent='Viewer data unavailable. Serve this site over HTTP and reload the page.';});
})();
</script></body></html>
"""
