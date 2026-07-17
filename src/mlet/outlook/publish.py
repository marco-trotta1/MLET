"""Render a self-contained, non-promotable Idaho outlook map candidate.

The immutable build artifact is read only through :func:`read_published_run`.
This module may render its verified bytes, but it is not a release authority:
every emitted artifact is permanently a research candidate with validation
pending.  In particular, a sibling validation receipt, a modified environment,
or a caller-provided object cannot make this publisher write a validated or
promoted status.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import json
import math
from pathlib import Path
from typing import Mapping

from mlet.outlook.build import PublishedRun, read_published_run


_SCHEMA_VERSION = 1
_LAYER_LABELS = {
    "eto_mm": "ETo outlook",
    "potential_et_c_mm": "Potential crop ET (well-watered)",
    "eta_analysis_mm": "Latest ETa analysis",
    "eta_well_watered_mm": "ETa scenario: well-watered",
    "eta_no_irrigation_mm": "ETa scenario: no further irrigation",
}
_REGIONAL_WARNING = "Regional outlook — not a field-level irrigation recommendation"


@dataclass(frozen=True)
class PublishResult:
    """Locations for an independently rendered, non-promotable map candidate."""

    run_id: str
    output_dir: Path
    index_path: Path
    geojson_path: Path
    summary_path: Path
    serve_contract_path: Path
    fixture_non_scientific: bool


def publish_outlook(run: Path, *, out_dir: Path | None = None) -> PublishResult:
    """Create a no-setup map from one verified immutable run.

    ``run`` is the public ``OUTPUT_ROOT/RUN_ID`` discovery handle.  It is not
    opened as a normal directory: the descriptor-anchored reader verifies every
    receipt hash before this function parses a byte.  The rendered directory is
    created once and never overwritten.  It is deliberately separate from the
    immutable source generation so publishing a map cannot change its receipt.
    """
    source = _read_run_reference(Path(run))
    contract = _load_contract(source)
    destination = (
        Path(out_dir)
        if out_dir is not None
        else Path(run).parent / f"{source.run_id}-research-candidate"
    )
    _create_output_directory(destination)

    candidate_contract = _candidate_contract(source, contract)
    geojson = _geojson_payload(candidate_contract)
    summary = _summary_payload(candidate_contract)
    index = _render_index(candidate_contract, geojson, summary)
    _write_new_json(destination / "serve-contract.json", candidate_contract)
    _write_new_json(destination / "outlook.geojson", geojson)
    _write_new_json(destination / "summary.json", summary)
    _write_new_text(destination / "index.html", index)
    return PublishResult(
        run_id=source.run_id,
        output_dir=destination,
        index_path=destination / "index.html",
        geojson_path=destination / "outlook.geojson",
        summary_path=destination / "summary.json",
        serve_contract_path=destination / "serve-contract.json",
        fixture_non_scientific=bool(candidate_contract["fixture_non_scientific"]),
    )


def _read_run_reference(run: Path) -> PublishedRun:
    if not run.name or run.name in {".", ".."}:
        raise ValueError("run must identify OUTPUT_ROOT/RUN_ID")
    try:
        return read_published_run(run.parent, run.name)
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read verified published outlook run: {error}") from error


def _load_contract(source: PublishedRun) -> dict[str, object]:
    try:
        payload = json.loads(
            source.artifact_bytes("outlook.json").decode("utf-8"),
            object_pairs_hook=_reject_duplicate_object_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("verified outlook.json must be strict JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("verified outlook.json must be an object")
    if payload.get("run_id") != source.run_id:
        raise ValueError("verified outlook.json run_id does not match its receipt")
    if not isinstance(payload.get("issued_at"), str):
        raise ValueError("verified outlook.json must record issued_at")
    if type(payload.get("fixture_non_scientific")) is not bool:
        raise ValueError("verified outlook.json must classify fixture status")
    if payload.get("spatial_resolution") != "native_weather_grid":
        raise ValueError("verified outlook.json must retain native_weather_grid resolution")
    if not isinstance(payload.get("layers"), dict):
        raise ValueError("verified outlook.json must define named layers")
    if not isinstance(payload.get("feature_collections"), list):
        raise ValueError("verified outlook.json must contain feature collections")
    return payload


def _candidate_contract(source: PublishedRun, contract: Mapping[str, object]) -> dict[str, object]:
    """Copy science fields while forcing this process's permanent false status."""
    fixture = contract["fixture_non_scientific"]
    assert type(fixture) is bool
    blockers = ["requires_separately_trusted_release_authority"]
    if fixture:
        blockers.insert(0, "software fixture is non-scientific and cannot be promoted")
    return {
        "schema_version": _SCHEMA_VERSION,
        "kind": "idaho_regional_et_outlook_research_candidate",
        "run_id": source.run_id,
        "issued_at": contract["issued_at"],
        "source_contract_sha256": hashlib.sha256(
            source.artifact_bytes("outlook.json")
        ).hexdigest(),
        "fixture_non_scientific": fixture,
        "production_status": "research_candidate",
        "promotion": False,
        "promotion_status": "not_promoted",
        # Do not route this value through configuration or a mutable authority
        # object: this evaluator process has no path to a validated status.
        "validation_status": "validation_pending",
        "promotion_blockers": blockers,
        "spatial_resolution": "native_weather_grid",
        "layers": contract["layers"],
        "grid_references": contract.get("grid_references", {}),
        "feature_collections": contract["feature_collections"],
        "regional_warning": _REGIONAL_WARNING,
        "geometry_note": (
            "Feature geometry is a source weather-grid reference point when available; "
            "it is not a field boundary or a synthetic grid-cell polygon."
        ),
    }


def _geojson_payload(candidate: Mapping[str, object]) -> dict[str, object]:
    collections = candidate["feature_collections"]
    assert isinstance(collections, list)
    features: list[dict[str, object]] = []
    for collection in collections:
        if not isinstance(collection, dict):
            raise ValueError("feature collections must be objects")
        valid_date = collection.get("valid_date")
        lead_day = collection.get("lead_day")
        raw_features = collection.get("features")
        if not isinstance(valid_date, str) or type(lead_day) is not int or not isinstance(raw_features, list):
            raise ValueError("feature collections must retain valid_date, lead_day, and features")
        for feature in raw_features:
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise ValueError("outlook feature collections must contain GeoJSON Features")
            properties = feature.get("properties")
            if not isinstance(properties, dict) or not isinstance(properties.get("grid_id"), str):
                raise ValueError("outlook feature must retain a stable grid_id")
            layers = properties.get("layers")
            if not isinstance(layers, dict):
                raise ValueError("outlook feature must retain named layers")
            geometry = feature.get("geometry")
            if geometry is not None and not isinstance(geometry, dict):
                raise ValueError("outlook feature geometry must be GeoJSON or null")
            features.append(
                {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {
                        "grid_id": properties["grid_id"],
                        "valid_date": valid_date,
                        "lead_day": lead_day,
                        "source_run_id": candidate["run_id"],
                        "spatial_resolution": "native_weather_grid",
                        "geometry_representation": properties.get(
                            "geometry_representation", "grid_identifier_only"
                        ),
                        "layers": layers,
                        "eta_analysis": properties.get("eta_analysis"),
                        "fixture_non_scientific": candidate["fixture_non_scientific"],
                        "validation_status": "validation_pending",
                    },
                }
            )
    return {
        "type": "FeatureCollection",
        "schema_version": _SCHEMA_VERSION,
        "run_id": candidate["run_id"],
        "issued_at": candidate["issued_at"],
        "fixture_non_scientific": candidate["fixture_non_scientific"],
        "production_status": "research_candidate",
        "promotion": False,
        "validation_status": "validation_pending",
        "spatial_resolution": "native_weather_grid",
        "regional_warning": _REGIONAL_WARNING,
        "features": features,
    }


def _summary_payload(candidate: Mapping[str, object]) -> dict[str, object]:
    """Expose only equal-cell descriptive means when source cell areas are absent."""
    geojson = _geojson_payload(candidate)
    by_date: dict[str, list[dict[str, object]]] = {}
    for feature in geojson["features"]:
        assert isinstance(feature, dict)
        properties = feature["properties"]
        assert isinstance(properties, dict)
        valid_date = properties["valid_date"]
        assert isinstance(valid_date, str)
        by_date.setdefault(valid_date, []).append(properties)
    return {
        "schema_version": _SCHEMA_VERSION,
        "kind": "idaho_regional_et_outlook_research_candidate_summary",
        "run_id": candidate["run_id"],
        "issued_at": candidate["issued_at"],
        "fixture_non_scientific": candidate["fixture_non_scientific"],
        "production_status": "research_candidate",
        "promotion": False,
        "validation_status": "validation_pending",
        "not_field_scale": True,
        "spatial_resolution": "native_weather_grid",
        "regional_aggregation": "equal_cell_descriptive_mean_not_area_weighted",
        "regional_aggregation_note": (
            "Source-grid cell areas are not present in the serving contract, so this "
            "candidate does not claim statewide area-weighted values."
        ),
        "daily": [
            _daily_summary(valid_date, properties)
            for valid_date, properties in sorted(by_date.items())
        ],
        "regional_warning": _REGIONAL_WARNING,
    }


def _daily_summary(valid_date: str, properties: list[dict[str, object]]) -> dict[str, object]:
    layers: dict[str, object] = {}
    for layer in _LAYER_LABELS:
        if layer == "eta_analysis_mm":
            values = [
                _analysis_value(item.get("eta_analysis")) for item in properties
            ]
            finite = [value for value in values if value is not None]
            layers[layer] = {"equal_cell_mean_mm": _mean(finite) if finite else None}
            continue
        quantiles = [
            _quantile_value(item.get("layers"), layer) for item in properties
        ]
        if any(value is None for value in quantiles):
            layers[layer] = None
            continue
        typed = [value for value in quantiles if value is not None]
        layers[layer] = {
            quantile: _mean([item[quantile] for item in typed])
            for quantile in ("p10", "p50", "p90")
        }
    return {"valid_date": valid_date, "cell_count": len(properties), "layers": layers}


def _quantile_value(value: object, layer: str) -> dict[str, float] | None:
    if not isinstance(value, dict):
        raise ValueError("outlook feature layers must be objects")
    quantiles = value.get(layer)
    if quantiles is None:
        return None
    if not isinstance(quantiles, dict):
        raise ValueError(f"{layer} must be quantiles or null")
    result: dict[str, float] = {}
    for name in ("p10", "p50", "p90"):
        raw = quantiles.get(name)
        if type(raw) not in (int, float) or not math.isfinite(float(raw)):
            raise ValueError(f"{layer} {name} must be finite")
        result[name] = float(raw)
    if not result["p10"] <= result["p50"] <= result["p90"]:
        raise ValueError(f"{layer} quantiles must be ordered")
    return result


def _analysis_value(value: object) -> float | None:
    if not isinstance(value, dict):
        raise ValueError("ETa analysis metadata must be an object")
    raw = value.get("eta_analysis_mm")
    if raw is None:
        return None
    if type(raw) not in (int, float) or not math.isfinite(float(raw)):
        raise ValueError("ETa analysis value must be finite or null")
    return float(raw)


def _mean(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot summarize an empty value set")
    return sum(values) / len(values)


def _render_index(
    candidate: Mapping[str, object], geojson: Mapping[str, object], summary: Mapping[str, object]
) -> str:
    """Return a standalone HTML document: no package install or network fetch."""
    fixture = bool(candidate["fixture_non_scientific"])
    fixture_notice = (
        "NON-SCIENTIFIC SOFTWARE FIXTURE — this is a map software test only; it is not a forecast or scientific evidence."
        if fixture
        else "RESEARCH CANDIDATE — validation pending; this is not a validated or operational product."
    )
    data = json.dumps({"geojson": geojson, "summary": summary}, sort_keys=True, separators=(",", ":"))
    options = "".join(
        f'<option value="{html.escape(key)}">{html.escape(label)}</option>'
        for key, label in _LAYER_LABELS.items()
    )
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Idaho ET outlook research candidate</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;color:#15231b;background:#f7faf7}}main{{max-width:980px;margin:auto;padding:24px}}.status{{padding:12px;background:#fff3cd;border:1px solid #d39e00;font-weight:700}}.warning{{font-weight:700}}label{{display:inline-block;margin:14px 12px 8px 0}}select{{padding:6px}}svg{{width:100%;height:430px;background:#dfeff4;border:1px solid #9fb8be}}.dot{{stroke:#15231b;stroke-width:1}}#detail{{background:white;padding:14px;border:1px solid #ced8d0}}small{{color:#445}}
</style></head><body><main>
<h1>Idaho regional ET outlook</h1><p class="status">{html.escape(fixture_notice)}</p>
<p><strong>Run ID:</strong> {html.escape(str(candidate['run_id']))}<br><strong>Issue time:</strong> {html.escape(str(candidate['issued_at']))}<br><strong>Resolution:</strong> native weather grid</p>
<p class="warning">{html.escape(_REGIONAL_WARNING)}</p>
<p>Weather-grid reference points are shown only when retained by the source contract; they are not field boundaries or synthetic cell polygons. Uncertainty is shown as p10, p50, and p90 where applicable.</p>
<label>Layer <select id="layer">{options}</select></label>
<label>Date <select id="date"></select></label><label>Quantile <select id="quantile"><option>p10</option><option selected>p50</option><option>p90</option></select></label>
<svg id="map" viewBox="0 0 900 430" role="img" aria-label="Native weather-grid reference-point map"></svg><div id="detail"></div>
<h2>Layer definitions</h2><ul><li>ETo outlook: weather-driven ASCE short-reference ET ensemble quantiles.</li><li>Potential crop ET (well-watered): Kc × ETo under ample-water conditions.</li><li>Latest ETa analysis: dated historical observation; never a future actual-ET forecast.</li><li>ETa scenario: well-watered: conditional on crop water not limiting.</li><li>ETa scenario: no further irrigation: conditional on no irrigation after issue time.</li></ul>
<p><small>Publication status: research candidate; promotion false; validation pending. A separately trusted external release authority is required before any promoted product may be published.</small></p>
<script>const DATA={data};const features=DATA.geojson.features;const date=document.querySelector('#date'),layer=document.querySelector('#layer'),quantile=document.querySelector('#quantile'),map=document.querySelector('#map'),detail=document.querySelector('#detail');const dates=[...new Set(features.map(f=>f.properties.valid_date))];date.innerHTML=dates.map(d=>`<option>${{d}}</option>`).join('');function value(f){{const p=f.properties;if(layer.value==='eta_analysis_mm')return p.eta_analysis&&p.eta_analysis.eta_analysis_mm;const q=p.layers[layer.value];return q&&q[quantile.value];}}function draw(){{const shown=features.filter(f=>f.properties.valid_date===date.value);const points=shown.map(f=>f.geometry&&f.geometry.type==='Point'?f.geometry.coordinates:null).filter(Boolean);let xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);let minx=Math.min(...xs,-117),maxx=Math.max(...xs,-116),miny=Math.min(...ys,43),maxy=Math.max(...ys,44);if(minx===maxx){{minx-=.25;maxx+=.25}}if(miny===maxy){{miny-=.25;maxy+=.25}}map.innerHTML='';shown.forEach(f=>{{if(!f.geometry||f.geometry.type!=='Point')return;const [x,y]=f.geometry.coordinates;const sx=50+(x-minx)/(maxx-minx)*800,sy=390-(y-miny)/(maxy-miny)*350,v=value(f),color=v==null?'#777':`hsl(${{Math.max(0,210-Math.min(180,v*35))}},70%,45%)`;map.innerHTML+=`<circle class="dot" cx="${{sx}}" cy="${{sy}}" r="12" fill="${{color}}"><title>${{f.properties.grid_id}}: ${{v==null?'unavailable':v.toFixed(2)+' mm/day'}}</title></circle>`;}});const samples=shown.map(value).filter(v=>v!=null);detail.textContent=`${{layer.options[layer.selectedIndex].text}} — ${{date.value}} — ${{layer.value==='eta_analysis_mm'?'dated analysis':' '+quantile.value}}: ${{samples.length?samples.map(v=>v.toFixed(2)+' mm/day').join(', '):'unavailable'}}. ${{DATA.geojson.regional_warning}}`;}}[date,layer,quantile].forEach(x=>x.addEventListener('change',draw));draw();</script>
</main></body></html>"""


def _create_output_directory(destination: Path) -> None:
    if destination.is_symlink() or destination.exists():
        raise ValueError("map candidate destination must not already exist")
    if destination.parent.is_symlink() or not destination.parent.is_dir():
        raise ValueError("map candidate destination parent must be a real directory")
    try:
        destination.mkdir(mode=0o700)
    except OSError as error:
        raise ValueError(f"cannot create map candidate destination: {destination}") from error


def _write_new_json(destination: Path, payload: Mapping[str, object]) -> None:
    _write_new_text(destination, json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")


def _write_new_text(destination: Path, text: str) -> None:
    try:
        with destination.open("x", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as error:
        raise ValueError(f"cannot write map candidate artifact: {destination.name}") from error


def _reject_duplicate_object_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON objects must not contain duplicate keys")
        result[key] = value
    return result
