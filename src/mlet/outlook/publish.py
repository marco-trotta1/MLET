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

from mlet.outlook.build import (
    PublishedRun,
    _close_descriptor,
    _create_private_generation,
    _fsync_directory_fd,
    _open_output_root,
    _publish_private_artifact,
    _write_new_bytes_at,
    read_published_run,
)


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
    schema_version: int


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
    candidate_contract = _candidate_contract(source, contract)
    geojson = _geojson_payload(candidate_contract)
    summary = _summary_payload(candidate_contract)
    index = _render_index(candidate_contract, geojson, summary)
    _publish_candidate_directory(
        destination,
        {
            "serve-contract.json": _json_bytes(candidate_contract),
            "outlook.geojson": _json_bytes(geojson),
            "summary.json": _json_bytes(summary),
            "index.html": index.encode("utf-8"),
        },
    )
    return PublishResult(
        run_id=source.run_id,
        output_dir=destination,
        index_path=destination / "index.html",
        geojson_path=destination / "outlook.geojson",
        summary_path=destination / "summary.json",
        serve_contract_path=destination / "serve-contract.json",
        fixture_non_scientific=bool(candidate_contract["fixture_non_scientific"]),
        schema_version=_SCHEMA_VERSION,
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
    if not isinstance(payload.get("validation_scope"), dict):
        raise ValueError("verified outlook.json must define validation_scope")
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
        "validation_scope": contract["validation_scope"],
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
                        "promotion": False,
                        "promotion_status": "not_promoted",
                        "validation_status": "validation_pending",
                        "validation_scope": candidate["validation_scope"],
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
        "promotion_status": "not_promoted",
        "validation_status": "validation_pending",
        "validation_scope": candidate["validation_scope"],
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
        "promotion_status": "not_promoted",
        "validation_status": "validation_pending",
        "validation_scope": candidate["validation_scope"],
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


_LAYER_NOTES = {
    "eto_mm": "Weather-driven ASCE short-reference ET ensemble quantiles.",
    "potential_et_c_mm": "Kc × ETo under ample-water conditions.",
    "eta_analysis_mm": "Dated historical observation; never a future actual-ET forecast.",
    "eta_well_watered_mm": "Conditional on crop water not limiting.",
    "eta_no_irrigation_mm": "Conditional on no irrigation after issue time.",
}
# The one layer the contract defines without ensemble quantiles.
_SCALAR_LAYER = "eta_analysis_mm"

# Chrome is monochrome by design: viridis is reserved for data, so no interface
# element samples the ramp and nothing competes with a reading.
_VIEWER_CSS = """
:root{
  --paper:#FFFFFF;--surface:#FFFFFF;--surface-2:#F5F5F4;
  --ink:#131514;--ink-2:#4C4F4D;--ink-3:#7A7E7C;--ink-4:#A6AAA8;
  --line:#EAEAE8;--line-2:#DDDEDB;--line-strong:#B9BBB8;
  --accent:#131514;--accent-dim:#8A8D8B;
  --warn:#8A5406;--warn-bg:#FBF2DF;--warn-line:#C77E1B;
  --sans:"Söhne","Sohne","Inter",-apple-system,"Helvetica Neue",sans-serif;
  /* Data face. Inter carries every number, run id, timestamp and axis label;
     tabular figures keep columns aligned without a monospace. */
  --data:"Inter",-apple-system,"Helvetica Neue",Arial,sans-serif;
}
html.dark{
  --paper:#0F1110;--surface:#171918;--surface-2:#1E211F;
  --ink:#EDEEEC;--ink-2:#A0A4A1;--ink-3:#767A78;--ink-4:#535755;
  --line:#232624;--line-2:#2D302E;--line-strong:#3F4341;
  --accent:#EDEEEC;--accent-dim:#5C605E;
  --warn:#E5B36A;--warn-bg:#211A0E;--warn-line:#6B4E1E;
}
*{margin:0;box-sizing:border-box}
html,body{height:100%}
body{background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:12.5px;
  line-height:1.45;-webkit-font-smoothing:antialiased;display:flex;flex-direction:column;
  overflow:hidden;font-variant-numeric:tabular-nums}
.lbl{font-size:9.5px;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-3)}
.strip{display:flex;align-items:center;gap:16px;min-height:38px;padding:0 14px;flex:none;
  background:var(--surface);border-bottom:1px solid var(--line-2)}
.wm{font-family:var(--data);font-weight:600;font-size:12.5px;white-space:nowrap}
.chips{display:flex;gap:5px;flex:1;overflow:hidden;flex-wrap:wrap;padding:5px 0}
.chip{font-family:var(--data);font-size:10.5px;padding:3px 8px;background:var(--paper);
  border:1px solid var(--line-2);border-radius:3px;color:var(--ink-2);white-space:nowrap;
  display:inline-flex;align-items:center;gap:6px}
.chip i{font-style:normal;color:var(--ink-4)}
.dot{width:5px;height:5px;border-radius:50%;background:var(--warn-line)}
.tgl{font-family:var(--data);font-size:10.5px;background:var(--paper);
  border:1px solid var(--line-strong);border-radius:3px;padding:4px 10px;cursor:pointer;
  color:var(--ink-2);flex:none}
.tgl:hover{border-color:var(--accent-dim);color:var(--ink)}
p.status{flex:none;background:var(--warn-bg);border-bottom:1px solid var(--warn-line);
  padding:7px 14px;font-size:11.5px;color:var(--warn);font-weight:600}
.warning{flex:none;padding:6px 14px;font-size:11.5px;color:var(--ink-2);
  border-bottom:1px solid var(--line-2);background:var(--surface)}
.grid{flex:1;display:grid;grid-template-columns:352px minmax(0,1fr) 258px;min-height:0;
  gap:1px;background:var(--line-2)}
.pane{display:flex;flex-direction:column;min-width:0;min-height:0;background:var(--paper)}
.ph{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:7px 12px;
  flex:none;background:var(--surface);border-bottom:1px solid var(--line-2)}
.pb{flex:1;min-height:0;overflow:auto}
.mx{padding:12px 12px 8px}
.mxrow{display:grid;grid-template-columns:118px minmax(0,1fr);align-items:center;gap:9px;margin-bottom:5px}
.mxkey{font-family:var(--data);font-size:10px;color:var(--ink-2);text-align:right;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer;padding:2px 0;
  background:none;border:none}
.mxkey:hover{color:var(--ink)}
.mxkey.on{color:var(--accent);font-weight:600}
.mxcells{display:grid;gap:2px}
.cell{height:20px;border-radius:2px;cursor:pointer;padding:0;border:none;
  outline:1.5px solid transparent;outline-offset:1px}
.cell:hover{outline-color:var(--ink-3)}
.cell.sel{outline-color:var(--ink)}
.cell.na{background:var(--surface-2);
  background-image:repeating-linear-gradient(45deg,transparent,transparent 3px,var(--line-strong) 3px,var(--line-strong) 4px)}
.mxaxis{display:grid;grid-template-columns:118px minmax(0,1fr);gap:9px;margin-top:2px}
.mxdates{display:grid;gap:2px;font-family:var(--data);font-size:8.5px;color:var(--ink-4)}
/* Labelled dates sit on narrow columns; let them spill into the blank
   columns either side instead of clipping to two half-characters. */
.mxdates span{text-align:center;overflow:visible;white-space:nowrap}
.mxdates span.on{color:var(--accent);font-weight:600}
.mxfoot{padding:10px 12px 14px;border-top:1px solid var(--line);margin-top:6px}
.mxlegend{display:flex;align-items:center;gap:9px;margin-bottom:9px}
.mxlegend .r{flex:1;height:7px;border-radius:2px;
  background:linear-gradient(90deg,#440154,#414487,#2A788E,#22A884,#7AD151,#FDE725)}
.mxlegend span{font-family:var(--data);font-size:9px;color:var(--ink-4)}
.mxnote{font-size:10.5px;color:var(--ink-3);line-height:1.5;border-left:2px solid var(--line-strong);
  padding-left:9px}
.swatch-na{display:inline-block;width:9px;height:9px;border-radius:2px;vertical-align:-1px;
  margin-right:4px;background:var(--surface-2);
  background-image:repeating-linear-gradient(45deg,transparent,transparent 2px,var(--line-strong) 2px,var(--line-strong) 3px)}
.defs{padding:14px 12px 18px;border-top:1px solid var(--line)}
.defs dl{margin:0}
.defs .d{padding:6px 0 6px 9px;border-left:2px solid var(--line);cursor:pointer}
.defs .d:hover{border-left-color:var(--line-strong)}
.defs .d.on{border-left-color:var(--accent)}
.defs dt{font-family:var(--data);font-size:10px;color:var(--ink-2)}
.defs .d.on dt{color:var(--accent)}
.defs dd{margin:1px 0 0;font-size:10.5px;color:var(--ink-4);line-height:1.45}
.defs .d.on dd{color:var(--ink-3)}
.mapbox{flex:1;min-height:0;position:relative;background:var(--paper)}
.mapbox svg{width:100%;height:100%;display:block}
.bm-grat line{stroke:var(--line);stroke-width:.6}
.bm-deg{font-family:var(--data);font-size:8px;fill:var(--ink-4)}
.bm-neighbour path{stroke:var(--line-2);stroke-width:1;fill:none;stroke-dasharray:4 3}
.bm-nb{font-size:8.5px;font-weight:600;letter-spacing:.14em;fill:var(--ink-4)}
.bm-state{fill:var(--surface);stroke:var(--line-strong);stroke-width:1.4}
.bm-plain{fill:none;stroke:var(--accent-dim);stroke-width:6;stroke-opacity:.16;
  stroke-linecap:round;stroke-linejoin:round}
.bm-plainlbl{font-size:8px;font-weight:600;letter-spacing:.13em;fill:var(--ink-4)}
.bm-place path{stroke:var(--ink-4);stroke-width:1}
.bm-placelbl{font-family:var(--data);font-size:8.5px;fill:var(--ink-3)}
.bm-scale path{stroke:var(--ink-3);stroke-width:1;fill:none}
.bm-scalelbl{font-family:var(--data);font-size:8.5px;fill:var(--ink-3)}
.ptring{fill:none;stroke:var(--ink);stroke-width:1}
.pt{stroke:var(--paper);stroke-width:1.75;cursor:pointer}
.ptx{stroke:var(--ink);stroke-width:1}
.ptlbl{font-family:var(--data);font-size:9px;fill:var(--ink-2)}
.card{position:absolute;background:var(--surface);border:1px solid var(--line-2);border-radius:4px}
.card.tl{top:11px;left:12px;padding:8px 11px}
.card.bl{bottom:11px;left:12px;padding:8px 11px;width:196px}
.card .k{font-family:var(--data);font-size:11px;color:var(--accent);font-weight:500}
.card .v{font-family:var(--data);font-size:16px;color:var(--ink);margin:3px 0 1px}
.card .v small{font-size:10px;color:var(--ink-3);margin-left:3px}
.card .m{font-family:var(--data);font-size:9.5px;color:var(--ink-4);line-height:1.6}
.card .r{height:7px;border-radius:2px;border:1px solid var(--line-2);
  background:linear-gradient(90deg,#440154,#414487,#2A788E,#22A884,#7AD151,#FDE725)}
.card .rl{display:flex;justify-content:space-between;font-family:var(--data);font-size:8.5px;
  color:var(--ink-4);margin-top:3px}
.card .rt{font-family:var(--data);font-size:9px;color:var(--ink-3);margin-bottom:5px;
  text-transform:uppercase;letter-spacing:.07em}
.fanbox{flex:none;height:190px;position:relative;border-top:1px solid var(--line-2)}
.fanbox svg{width:100%;height:100%;display:block}
.gl{stroke:var(--line);stroke-width:.6;stroke-dasharray:2 3}
.fanband{fill:var(--accent);fill-opacity:.15}
.fanedge{stroke:var(--accent);stroke-width:.85;fill:none;opacity:.42}
.fanline{stroke:var(--accent);stroke-width:2;fill:none;stroke-linejoin:round}
.fandot{fill:var(--paper);stroke:var(--accent);stroke-width:2}
.scrub{stroke:var(--ink-3);stroke-width:1;stroke-dasharray:3 3}
.scrubband{fill:var(--ink);opacity:.045}
.tick{font-family:var(--data);font-size:9px;fill:var(--ink-4)}
.tick.on{fill:var(--accent);font-weight:600}
.fanlbl{font-family:var(--data);font-size:9px;fill:var(--ink-3)}
.qbtns{display:flex;border:1px solid var(--line-strong);border-radius:4px;overflow:hidden}
.qbtns button{font-family:var(--data);font-size:10px;background:var(--paper);border:none;
  border-right:1px solid var(--line-strong);padding:3px 9px;cursor:pointer;color:var(--ink-2)}
.qbtns button:last-child{border-right:none}
.qbtns button.on{background:var(--accent);color:var(--paper);font-weight:600}
.qbtns button:disabled{opacity:.3;cursor:not-allowed}
.ro{width:100%;border-collapse:collapse}
.ro td{font-family:var(--data);font-size:10.5px;padding:4px 12px;border-bottom:1px solid var(--line)}
.ro td:first-child{color:var(--ink-3)}
.ro td:last-child{text-align:right;color:var(--ink)}
.ro tr.hd td{background:var(--surface);color:var(--ink-3);font-weight:600;font-size:9px;
  text-transform:uppercase;letter-spacing:.1em;padding:6px 12px;border-bottom:1px solid var(--line-2)}
.ro tr.on td:last-child{color:var(--accent);font-weight:600}
.ro tr.big td:last-child{font-size:13.5px}
.ro td.na{color:var(--ink-4)}
.foot{flex:none;font-family:var(--data);font-size:9px;color:var(--ink-4);padding:6px 12px;
  border-top:1px solid var(--line-2);background:var(--surface);line-height:1.5}
@media (max-width:1000px){
  .grid{grid-template-columns:minmax(0,1fr);grid-auto-rows:min-content}
  .mapbox{min-height:360px}
}
"""

# Basemap geometry. Everything here is a cartographic reference for locating a
# weather-grid point: a state border, a neighbour name, a graticule, a
# populated place, a scale bar. None of it is an inferred cell boundary, field
# geometry, or management zone, and none of it is ever coloured from the data
# ramp.
_VIEWER_JS = """
const GEO = DATA.geojson, SUM = DATA.summary;
const DAILY = SUM.daily.slice().sort((a, b) => a.valid_date < b.valid_date ? -1 : 1);
const NS = 'http://www.w3.org/2000/svg';
const state = { layer: LAYERS[0].key, q: 'p50', i: 0, grid: null };

const IDAHO = [
  [-117.03,42.00],[-111.05,42.00],[-111.05,44.48],[-112.17,44.52],[-113.00,44.45],
  [-113.45,44.87],[-114.02,45.65],[-114.35,45.55],[-114.56,45.77],[-114.33,46.06],
  [-114.50,46.64],[-115.30,47.25],[-115.75,47.70],[-116.05,48.00],[-116.05,49.00],
  [-117.03,49.00],[-117.03,46.43],[-116.92,46.17],[-116.79,45.87],[-116.46,45.61],
  [-116.68,45.32],[-116.85,44.85],[-117.22,44.30],[-117.03,43.83],[-116.90,43.60]
];
const FRAME = { minLon:-118.5, maxLon:-110.0, minLat:41.3, maxLat:49.6 };
const NEIGHBOUR_BORDERS = [
  [[-117.03,46.00],[-118.5,46.00]], [[-117.03,42.00],[-118.5,42.00]],
  [[-114.05,42.00],[-114.05,41.3]], [[-111.05,42.00],[-111.05,41.3]],
  [[-111.05,44.50],[-110.0,44.50]]
];
const NEIGHBOURS = [
  {name:'WASHINGTON',lon:-117.85,lat:47.35},{name:'OREGON',lon:-117.85,lat:44.20},
  {name:'NEVADA',lon:-115.60,lat:41.66},{name:'UTAH',lon:-112.50,lat:41.66},
  {name:'MONTANA',lon:-112.60,lat:47.60},{name:'WYOMING',lon:-110.55,lat:43.30}
];
const PLACES = [
  {name:"Coeur d'Alene",lon:-116.78,lat:47.68},{name:'Lewiston',lon:-117.02,lat:46.42},
  {name:'Boise',lon:-116.20,lat:43.62},{name:'Twin Falls',lon:-114.46,lat:42.56},
  {name:'Pocatello',lon:-112.45,lat:42.87},{name:'Idaho Falls',lon:-112.03,lat:43.49}
];
const SNAKE_PLAIN = [
  [-117.03,44.28],[-116.65,43.86],[-116.10,43.62],[-115.35,43.30],[-114.50,42.92],
  [-113.60,42.72],[-112.80,42.84],[-112.20,43.18],[-111.60,43.62],[-111.30,43.78]
];
const VIRIDIS = [[68,1,84],[70,50,126],[54,92,141],[39,127,142],[33,145,140],[34,168,132],[122,209,81],[253,231,37]];
function viridis(t){
  t = Math.min(1, Math.max(0, t));
  const x = t*(VIRIDIS.length-1), i = Math.min(VIRIDIS.length-2, Math.floor(x)), f = x-i;
  const c = VIRIDIS[i].map((a,k) => Math.round(a + (VIRIDIS[i+1][k]-a)*f));
  return 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')';
}
// Equirectangular at the bbox mid-latitude. A degree of longitude is only
// cos(lat) as wide as a degree of latitude; without this Idaho renders far too
// wide.
function projection(w, h, pad){
  const k = Math.cos((FRAME.minLat + FRAME.maxLat)/2 * Math.PI/180);
  const dw = (FRAME.maxLon - FRAME.minLon)*k, dh = FRAME.maxLat - FRAME.minLat;
  const s = Math.min((w-pad*2)/dw, (h-pad*2)/dh);
  const ox = (w - dw*s)/2, oy = (h - dh*s)/2;
  return { x: lon => ox + (lon-FRAME.minLon)*k*s, y: lat => h - oy - (lat-FRAME.minLat)*s,
           kmPerUnit: 111.32/s };
}
function pathFrom(coords, p){
  return coords.map((c,i) => (i?'L':'M') + p.x(c[0]).toFixed(1) + ' ' + p.y(c[1]).toFixed(1)).join(' ');
}
// Greedy label placement: a basemap label that cannot be drawn without
// colliding is dropped rather than overprinted.
function labeller(){
  const taken = [];
  const hits = (a,b) => !(a.x2<b.x1 || a.x1>b.x2 || a.y2<b.y1 || a.y1>b.y2);
  return {
    reserve: b => taken.push(b),
    reserveCircle: (x,y,r) => taken.push({x1:x-r,y1:y-r,x2:x+r,y2:y+r}),
    place(x,y,text,size,anchor){
      const w = text.length*size*0.62;
      const x1 = anchor==='middle' ? x-w/2 : (anchor==='end' ? x-w : x);
      const box = {x1:x1-2, y1:y-size, x2:x1+w+2, y2:y+3};
      if (taken.some(t => hits(box,t))) return false;
      taken.push(box); return true;
    }
  };
}
function nearestPlace(lon, lat){
  let best = null;
  PLACES.forEach(p => {
    const dx = (p.lon-lon)*Math.cos(lat*Math.PI/180)*111.32, dy = (p.lat-lat)*111.32;
    const km = Math.sqrt(dx*dx + dy*dy);
    if (!best || km < best.km) best = {name:p.name, km:km};
  });
  return best;
}
function svgText(svg, x, y, cls, str, anchor){
  const t = document.createElementNS(NS, 'text');
  t.setAttribute('x', x); t.setAttribute('y', y); t.setAttribute('class', cls);
  if (anchor) t.setAttribute('text-anchor', anchor);
  t.textContent = str; svg.append(t); return t;
}
function drawBasemap(svg, p, lab){
  const grat = document.createElementNS(NS,'g'); grat.setAttribute('class','bm-grat'); svg.append(grat);
  const degs = [];
  for (let lat = 42; lat <= 49; lat++){
    const l = document.createElementNS(NS,'line');
    l.setAttribute('x1', p.x(FRAME.minLon)); l.setAttribute('x2', p.x(FRAME.maxLon));
    l.setAttribute('y1', p.y(lat)); l.setAttribute('y2', p.y(lat)); grat.append(l);
    if (lat % 2 === 0) degs.push([p.x(FRAME.minLon)+3, p.y(lat)-3, lat + '\\u00B0N', 'start']);
  }
  for (let lon = -118; lon <= -110; lon++){
    const l = document.createElementNS(NS,'line');
    l.setAttribute('y1', p.y(FRAME.minLat)); l.setAttribute('y2', p.y(FRAME.maxLat));
    l.setAttribute('x1', p.x(lon)); l.setAttribute('x2', p.x(lon)); grat.append(l);
    if (lon % 2 === 0) degs.push([p.x(lon), p.y(FRAME.minLat)+9, Math.abs(lon) + '\\u00B0W', 'middle']);
  }
  const nb = document.createElementNS(NS,'g'); nb.setAttribute('class','bm-neighbour'); svg.append(nb);
  NEIGHBOUR_BORDERS.forEach(seg => {
    const path = document.createElementNS(NS,'path');
    path.setAttribute('d', pathFrom(seg, p)); nb.append(path);
  });
  const st = document.createElementNS(NS,'path');
  st.setAttribute('d', pathFrom(IDAHO, p) + ' Z'); st.setAttribute('class','bm-state'); svg.append(st);
  const sp = document.createElementNS(NS,'path');
  sp.setAttribute('d', pathFrom(SNAKE_PLAIN, p)); sp.setAttribute('class','bm-plain'); svg.append(sp);

  const pl = document.createElementNS(NS,'g'); pl.setAttribute('class','bm-place'); svg.append(pl);
  PLACES.forEach(place => {
    const x = p.x(place.lon), y = p.y(place.lat);
    const c = document.createElementNS(NS,'path');
    c.setAttribute('d','M'+(x-3)+' '+y+' L'+(x+3)+' '+y+' M'+x+' '+(y-3)+' L'+x+' '+(y+3));
    pl.append(c);
    const tries = [[x+5.5,y+3,'start'],[x-5.5,y+3,'end'],[x,y+11,'middle']];
    for (let k = 0; k < tries.length; k++){
      if (lab.place(tries[k][0], tries[k][1], place.name, 8.5, tries[k][2])){
        svgText(svg, tries[k][0], tries[k][1], 'bm-placelbl', place.name, tries[k][2]); break;
      }
    }
  });
  const along = [[-113.60,42.72,16],[-115.35,43.30,17],[-112.80,42.84,-11],[-114.50,42.92,-11]];
  for (let k = 0; k < along.length; k++){
    const x = p.x(along[k][0]), y = p.y(along[k][1]) + along[k][2];
    if (lab.place(x, y, 'SNAKE RIVER PLAIN', 8, 'middle')){
      svgText(svg, x, y, 'bm-plainlbl', 'SNAKE RIVER PLAIN', 'middle'); break;
    }
  }
  NEIGHBOURS.forEach(n => {
    const x = p.x(n.lon), y = p.y(n.lat);
    const offs = [0,-14,14,-28,28];
    for (let k = 0; k < offs.length; k++){
      if (lab.place(x, y+offs[k], n.name, 8.5, 'middle')){
        svgText(svg, x, y+offs[k], 'bm-nb', n.name, 'middle'); break;
      }
    }
  });
  degs.forEach(d => { if (lab.place(d[0], d[1], d[2], 8, d[3])) svgText(svg, d[0], d[1], 'bm-deg', d[2], d[3]); });
}
function drawScaleBar(svg, p, x, y){
  const targets = [50,100,150,200,300,500];
  let km = targets[0];
  targets.forEach(t => { if (t/p.kmPerUnit <= 120) km = t; });
  const len = km/p.kmPerUnit;
  const g = document.createElementNS(NS,'g'); g.setAttribute('class','bm-scale');
  const bar = document.createElementNS(NS,'path');
  bar.setAttribute('d','M'+x+' '+(y-4)+' L'+x+' '+y+' L'+(x+len)+' '+y+' L'+(x+len)+' '+(y-4));
  g.append(bar); svg.append(g);
  svgText(svg, x+len/2, y-7, 'bm-scalelbl', km + ' km', 'middle');
}

// ---- accessors -----------------------------------------------------------
// The fan and matrix read summary.daily, the equal-cell descriptive mean the
// contract publishes. The map reads individual features. Scalar layers yield a
// null series: a dated observation is never drawn as a per-lead-day forecast.
function isScalar(key){ return key === SCALAR_LAYER; }
function dailyValue(entry, key, q){
  const v = entry.layers[key];
  if (v == null) return null;
  if (isScalar(key)) return v.equal_cell_mean_mm == null ? null : v.equal_cell_mean_mm;
  return v[q];
}
function seriesFor(key, q){ return DAILY.map(d => isScalar(key) ? null : dailyValue(d, key, q)); }
function bandFor(key){
  return DAILY.map(d => {
    if (isScalar(key)) return null;
    const v = d.layers[key];
    return v == null ? null : [v.p10, v.p90];
  });
}
function featureValue(props, key, q){
  const v = props.layers[key];
  if (v == null) return null;
  if (typeof v === 'number') return v;
  return v[q];
}
const BY_DATE = {};
// The published summary carries valid_date but not lead_day, so lead offsets
// are read back from the features rather than by widening the summary schema.
const LEAD_BY_DATE = {};
GEO.features.forEach(f => {
  const d = f.properties.valid_date;
  if (!BY_DATE[d]) BY_DATE[d] = [];
  BY_DATE[d].push(f);
  if (LEAD_BY_DATE[d] === undefined) LEAD_BY_DATE[d] = f.properties.lead_day;
});
function leadFor(date){
  const v = LEAD_BY_DATE[date];
  return v === undefined || v === null ? null : v;
}
function currentFeatures(){ return BY_DATE[DAILY[state.i].valid_date] || []; }
function selectedFeature(){
  const list = currentFeatures();
  if (!list.length) return null;
  if (state.grid){
    for (let k = 0; k < list.length; k++) if (list[k].properties.grid_id === state.grid) return list[k];
  }
  return list[0];
}
function layerMeta(key){
  for (let k = 0; k < LAYERS.length; k++) if (LAYERS[k].key === key) return LAYERS[k];
  return LAYERS[0];
}

// ---- matrix --------------------------------------------------------------
function drawMatrix(){
  const host = document.getElementById('mx');
  host.replaceChildren();
  const cols = 'repeat(' + DAILY.length + ',minmax(0,1fr))';
  LAYERS.forEach(L => {
    const row = document.createElement('div'); row.className = 'mxrow';
    const key = document.createElement('button');
    key.className = 'mxkey' + (L.key === state.layer ? ' on' : '');
    key.textContent = L.key.replace(/_mm$/, '');
    key.title = L.label + ' \\u2014 ' + L.note;
    key.onclick = () => { state.layer = L.key; draw(); };
    const cells = document.createElement('div');
    cells.className = 'mxcells'; cells.style.gridTemplateColumns = cols;
    DAILY.forEach((d, i) => {
      const v = dailyValue(d, L.key, L.quantile ? state.q : 'p50');
      const c = document.createElement('button');
      c.className = 'cell' + (v == null ? ' na' : '') + (i === state.i && L.key === state.layer ? ' sel' : '');
      if (v != null) c.style.background = viridis(v/8);
      c.title = L.key + ' \\u00B7 ' + d.valid_date + ' \\u00B7 ' +
        (v == null ? 'no value in this run' : v.toFixed(2) + ' mm/day');
      c.onclick = () => { state.layer = L.key; state.i = i; draw(); };
      cells.append(c);
    });
    row.append(key, cells); host.append(row);
  });
  const ax = document.createElement('div'); ax.className = 'mxaxis';
  const dates = document.createElement('div');
  dates.className = 'mxdates'; dates.style.gridTemplateColumns = cols;
  const stride = Math.max(1, Math.round(DAILY.length/7));
  DAILY.forEach((d, i) => {
    const s = document.createElement('span');
    s.textContent = (i % stride === 0 || i === state.i) ? d.valid_date.slice(8) : '';
    if (i === state.i) s.className = 'on';
    dates.append(s);
  });
  ax.append(document.createElement('div'), dates); host.append(ax);

  const L = layerMeta(state.layer);
  document.getElementById('mxunit').textContent = 'mm/day \\u00B7 ' + (L.quantile ? state.q : 'observed');
  // Definitions are server-rendered so the contract's layer names are readable
  // without scripting; script only reflects which one is selected.
  const defs = document.querySelectorAll('#defs .d');
  for (let k = 0; k < defs.length; k++)
    defs[k].classList.toggle('on', defs[k].dataset.k === state.layer);
}

// ---- map -----------------------------------------------------------------
function drawMap(){
  const svg = document.getElementById('map');
  const w = svg.clientWidth || 640, h = svg.clientHeight || 420;
  svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
  svg.replaceChildren();
  const p = projection(w, h, 16);
  const entry = DAILY[state.i];
  const L = layerMeta(state.layer);
  const feats = currentFeatures();
  const chosen = selectedFeature();

  const lab = labeller();
  lab.reserve({x1:6,y1:6,x2:250,y2:86});
  lab.reserve({x1:6,y1:h-78,x2:224,y2:h-6});
  lab.reserve({x1:w-132,y1:h-32,x2:w-4,y2:h-4});
  feats.forEach(f => {
    if (f.geometry && f.geometry.type === 'Point')
      lab.reserveCircle(p.x(f.geometry.coordinates[0]), p.y(f.geometry.coordinates[1]), 16);
  });
  drawBasemap(svg, p, lab);

  let drawn = 0;
  feats.forEach(f => {
    if (!f.geometry || f.geometry.type !== 'Point') return;
    drawn++;
    const x = p.x(f.geometry.coordinates[0]), y = p.y(f.geometry.coordinates[1]);
    const v = featureValue(f.properties, state.layer, state.q);
    const sel = chosen && f.properties.grid_id === chosen.properties.grid_id;
    if (sel){
      const ring = document.createElementNS(NS,'circle');
      ring.setAttribute('cx',x); ring.setAttribute('cy',y); ring.setAttribute('r',14);
      ring.setAttribute('class','ptring'); svg.append(ring);
      const cross = document.createElementNS(NS,'path');
      cross.setAttribute('d','M'+(x-20)+' '+y+' L'+(x-14)+' '+y+' M'+(x+14)+' '+y+' L'+(x+20)+' '+y+
        ' M'+x+' '+(y-20)+' L'+x+' '+(y-14)+' M'+x+' '+(y+14)+' L'+x+' '+(y+20));
      cross.setAttribute('class','ptx'); svg.append(cross);
    }
    const c = document.createElementNS(NS,'circle');
    c.setAttribute('cx',x); c.setAttribute('cy',y);
    c.setAttribute('r', feats.length > 60 ? 4.5 : 7.5);
    c.setAttribute('class','pt');
    c.setAttribute('fill', v == null ? 'var(--ink-4)' : viridis(v/8));
    const title = document.createElementNS(NS,'title');
    title.textContent = f.properties.grid_id + ': ' +
      (v == null ? 'unavailable' : v.toFixed(2) + ' mm/day');
    c.append(title);
    c.onclick = () => { state.grid = f.properties.grid_id; draw(); };
    svg.append(c);
  });

  // A single retained point carries its locality, because the basemap
  // labeller suppresses any place name underneath it. Phrased as proximity: a
  // weather-grid cell is a regional reference, not the settlement itself.
  if (drawn === 1 && chosen && chosen.geometry && chosen.geometry.type === 'Point'){
    const near = nearestPlace(chosen.geometry.coordinates[0], chosen.geometry.coordinates[1]);
    const x = p.x(chosen.geometry.coordinates[0]), y = p.y(chosen.geometry.coordinates[1]);
    svgText(svg, x+27, y+3.5, 'ptlbl',
      near.km < 12 ? 'near ' + near.name : near.km.toFixed(0) + ' km from ' + near.name);
  }
  drawScaleBar(svg, p, w-118, h-14);

  const v = chosen ? featureValue(chosen.properties, state.layer, state.q) : null;
  const lead = leadFor(entry.valid_date);
  document.getElementById('mapdate').textContent =
    entry.valid_date + (lead == null ? '' : ' \\u00B7 lead ' + lead);
  document.getElementById('mi-layer').textContent = L.key;
  const valEl = document.getElementById('mi-val');
  valEl.replaceChildren();
  if (v == null) { valEl.textContent = 'no value'; }
  else {
    valEl.append(document.createTextNode(v.toFixed(2)));
    const s = document.createElement('small');
    s.textContent = 'mm/day' + (L.quantile ? ' \\u00B7 ' + state.q : '');
    valEl.append(s);
  }
  document.getElementById('mi-meta').textContent =
    drawn + (drawn === 1 ? ' reference point \\u00B7 ' : ' reference points \\u00B7 ') + GEO.spatial_resolution;
}

// ---- fan -----------------------------------------------------------------
function drawFan(){
  const svg = document.getElementById('fan');
  const w = svg.clientWidth || 640, h = svg.clientHeight || 190;
  svg.setAttribute('viewBox','0 0 ' + w + ' ' + h);
  svg.replaceChildren();
  const padL = 48, padR = 14, padT = 14, padB = 22;
  const L = layerMeta(state.layer);
  const p50 = seriesFor(state.layer, 'p50'), bd = bandFor(state.layer);
  const vals = [];
  p50.forEach(v => { if (v != null) vals.push(v); });
  bd.forEach(b => { if (b) { vals.push(b[0]); vals.push(b[1]); } });

  if (!vals.length){
    const entry = DAILY[state.i];
    const scalar = isScalar(state.layer);
    svgText(svg, w/2, h/2-4, 'fanlbl', scalar
      ? 'No ensemble series \\u2014 dated historical observation, not a forecast.'
      : 'No value carried for this layer in this run.', 'middle');
    const obs = scalar ? entry.layers[state.layer] : null;
    const mean = obs && obs.equal_cell_mean_mm != null ? obs.equal_cell_mean_mm : null;
    const chosen = selectedFeature();
    const date = chosen && chosen.properties.eta_analysis
      ? chosen.properties.eta_analysis.eta_analysis_date : null;
    svgText(svg, w/2, h/2+13, 'tick', scalar && mean != null
      ? mean.toFixed(2) + ' mm/day, ETa observation date ' + (date || 'unavailable') + ', carried at source lag'
      : 'An absent scenario is never substituted with another layer value.', 'middle');
    return;
  }

  let lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
  const pv = (hi-lo)*0.45 || 0.5; lo -= pv; hi += pv;
  const n = DAILY.length;
  const X = i => n === 1 ? (padL + (w-padL-padR)/2) : padL + i*(w-padL-padR)/(n-1);
  const Y = v => h - padB - (v-lo)*(h-padT-padB)/(hi-lo);

  for (let k = 0; k <= 3; k++){
    const v = lo + (hi-lo)*k/3;
    const l = document.createElementNS(NS,'line');
    l.setAttribute('x1',padL); l.setAttribute('x2',w-padR);
    l.setAttribute('y1',Y(v)); l.setAttribute('y2',Y(v)); l.setAttribute('class','gl'); svg.append(l);
    svgText(svg, padL-7, Y(v)+3, 'tick', v.toFixed(2), 'end');
  }
  const yl = svgText(svg, 0, 0, 'fanlbl', 'mm/day', 'middle');
  yl.setAttribute('transform','translate(11,' + ((h-padB+padT)/2) + ') rotate(-90)');

  const step = n === 1 ? w : (w-padL-padR)/(n-1);
  const hl = document.createElementNS(NS,'rect');
  hl.setAttribute('x', X(state.i)-step/2); hl.setAttribute('y', padT-6);
  hl.setAttribute('width', step); hl.setAttribute('height', h-padB-padT+6);
  hl.setAttribute('class','scrubband'); svg.append(hl);

  const complete = bd.every(b => b);
  if (complete && n > 1){
    const up = bd.map((b,i) => X(i).toFixed(1) + ' ' + Y(b[1]).toFixed(1));
    const dn = bd.map((b,i) => X(i).toFixed(1) + ' ' + Y(b[0]).toFixed(1)).reverse();
    const band = document.createElementNS(NS,'path');
    band.setAttribute('d','M' + up.join(' L') + ' L' + dn.join(' L') + ' Z');
    band.setAttribute('class','fanband'); svg.append(band);
    [1,0].forEach(edge => {
      const e = document.createElementNS(NS,'path');
      e.setAttribute('d', bd.map((b,i) => (i?'L':'M') + X(i).toFixed(1) + ' ' + Y(b[edge]).toFixed(1)).join(' '));
      e.setAttribute('class','fanedge'); svg.append(e);
    });
  }
  const line = document.createElementNS(NS,'path');
  line.setAttribute('d', p50.map((v,i) => (i?'L':'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1)).join(' '));
  line.setAttribute('class','fanline'); svg.append(line);

  const stride = Math.max(1, Math.round(n/6));
  DAILY.forEach((d,i) => {
    if (i % stride !== 0 && i !== state.i) return;
    const t = svgText(svg, X(i), h-7, 'tick' + (i === state.i ? ' on' : ''), d.valid_date.slice(5), 'middle');
    return t;
  });
  const s = document.createElementNS(NS,'line');
  s.setAttribute('x1',X(state.i)); s.setAttribute('x2',X(state.i));
  s.setAttribute('y1',padT-6); s.setAttribute('y2',h-padB); s.setAttribute('class','scrub'); svg.append(s);
  const dot = document.createElementNS(NS,'circle');
  dot.setAttribute('cx',X(state.i)); dot.setAttribute('cy',Y(p50[state.i]));
  dot.setAttribute('r',4.5); dot.setAttribute('class','fandot'); svg.append(dot);

  const hit = document.createElementNS(NS,'rect');
  hit.setAttribute('width',w); hit.setAttribute('height',h); hit.setAttribute('fill','transparent');
  hit.style.cursor = 'col-resize';
  const pick = e => {
    const rect = svg.getBoundingClientRect();
    const px = (e.clientX-rect.left)*(w/rect.width);
    const i = Math.round((px-padL)/step);
    const c = Math.min(n-1, Math.max(0,i));
    if (c !== state.i){ state.i = c; draw(); }
  };
  hit.onpointerdown = e => { hit.setPointerCapture(e.pointerId); pick(e); };
  hit.onpointermove = e => { if (e.buttons) pick(e); };
  svg.append(hit);
}

// ---- readout -------------------------------------------------------------
function drawReadout(){
  const t = document.getElementById('ro');
  t.replaceChildren();
  const entry = DAILY[state.i];
  const L = layerMeta(state.layer);
  const chosen = selectedFeature();
  const hd = k => {
    const tr = document.createElement('tr'); tr.className = 'hd';
    const td = document.createElement('td'); td.colSpan = 2; td.textContent = k;
    tr.append(td); t.append(tr);
  };
  const add = (k, v, cls) => {
    const tr = document.createElement('tr'); if (cls) tr.className = cls;
    const a = document.createElement('td'); a.textContent = k;
    const b = document.createElement('td');
    if (v == null){ b.className = 'na'; b.textContent = 'no value'; } else { b.textContent = v; }
    tr.append(a, b); t.append(tr);
  };

  hd('selection');
  add('valid_date', entry.valid_date);
  const leadDay = leadFor(entry.valid_date);
  add('lead_day', leadDay == null ? null : String(leadDay));
  add('cell_count', String(entry.cell_count));
  if (chosen) add('grid_id', chosen.properties.grid_id);

  const dv = entry.layers[state.layer];
  if (dv && !isScalar(state.layer)){
    hd('regional mean \\u2014 quantiles');
    add('p10', dv.p10.toFixed(3));
    add('p50', dv.p50.toFixed(3), state.q === 'p50' ? 'on big' : '');
    add('p90', dv.p90.toFixed(3));
    add('p90 \\u2212 p10', (dv.p90-dv.p10).toFixed(3));
  } else {
    hd('regional mean');
    const mean = dv && dv.equal_cell_mean_mm != null ? dv.equal_cell_mean_mm.toFixed(2) : null;
    add(state.layer.replace(/_mm$/,''), mean);
  }

  hd('all layers @ ' + entry.valid_date);
  LAYERS.forEach(Lx => {
    const v = dailyValue(entry, Lx.key, Lx.quantile ? state.q : 'p50');
    add(Lx.key.replace(/_mm$/,''), v == null ? null : v.toFixed(2), Lx.key === state.layer ? 'on' : '');
  });

  if (chosen && chosen.properties.eta_analysis){
    hd('eta analysis');
    add('ETa observation date', chosen.properties.eta_analysis.eta_analysis_date || null);
    const m = chosen.properties.eta_analysis.eta_analysis_mm;
    add('eta_analysis_mm', m == null ? null : m.toFixed(2));
  }

  const btns = document.querySelectorAll('#qbtns button');
  for (let k = 0; k < btns.length; k++){
    btns[k].disabled = !L.quantile;
    if (btns[k].dataset.q === state.q && L.quantile) btns[k].classList.add('on');
    else btns[k].classList.remove('on');
  }
  document.getElementById('foot').textContent = L.quantile
    ? 'research candidate \\u00B7 promotion false \\u00B7 validation pending \\u00B7 ' + SUM.regional_aggregation
    : L.key + ' is a dated observation \\u2014 quantiles not applicable';
}

function draw(){ drawMatrix(); drawMap(); drawFan(); drawReadout(); }

const btns = document.querySelectorAll('#qbtns button');
for (let k = 0; k < btns.length; k++){
  btns[k].onclick = function(){ if (!this.disabled){ state.q = this.dataset.q; draw(); } };
}
const defNodes = document.querySelectorAll('#defs .d');
for (let k = 0; k < defNodes.length; k++){
  defNodes[k].onclick = function(){ state.layer = this.dataset.k; draw(); };
}
document.getElementById('tgl').onclick = function(){
  const dark = document.documentElement.classList.toggle('dark');
  this.textContent = dark ? 'light' : 'dark';
  draw();
};
draw();
addEventListener('resize', () => { drawMap(); drawFan(); });
"""


def _render_index(
    candidate: Mapping[str, object], geojson: Mapping[str, object], summary: Mapping[str, object]
) -> str:
    """Return a standalone HTML document: no package install or network fetch."""
    fixture = bool(candidate["fixture_non_scientific"])
    document_title = (
        "Idaho ET outlook — NON-SCIENTIFIC SOFTWARE FIXTURE"
        if fixture
        else "Idaho ET outlook research candidate"
    )
    fixture_notice = (
        "NON-SCIENTIFIC SOFTWARE FIXTURE — map software test only; not a forecast or scientific evidence."
        if fixture
        else "RESEARCH CANDIDATE — validation pending; this is not a validated or operational product."
    )
    data = _script_safe_json({"geojson": geojson, "summary": summary})
    scalar = _script_safe_json(_SCALAR_LAYER)
    layer_meta = _script_safe_json(
        [
            {
                "key": key,
                "label": label,
                "note": _LAYER_NOTES[key],
                "quantile": key != _SCALAR_LAYER,
            }
            for key, label in _LAYER_LABELS.items()
        ]
    )
    # Layer definitions are rendered server-side so the contract's own layer
    # names survive with scripting disabled.
    definitions = "".join(
        f'<div class="d" data-k="{html.escape(key)}">'
        f"<dt>{html.escape(key)}</dt>"
        f"<dd>{html.escape(label)} — {html.escape(_LAYER_NOTES[key])}</dd></div>"
        for key, label in _LAYER_LABELS.items()
    )
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(document_title)}</title>
<style>{_VIEWER_CSS}</style></head>
<body>
<div class="strip">
<span class="wm">MLET · Idaho ET Outlook</span>
<span class="chips">
<span class="chip"><i>run</i>{html.escape(str(candidate['run_id']))}</span>
<span class="chip"><i>issued</i>{html.escape(str(candidate['issued_at']))}</span>
<span class="chip"><i>grid</i>native weather grid</span>
<span class="chip"><span class="dot"></span>validation_pending</span>
<span class="chip"><i>promotion</i>false</span>
</span>
<button class="tgl" id="tgl" type="button">dark</button>
</div>
<p class="status" role="status">{html.escape(fixture_notice)}</p>
<p class="warning">{html.escape(_REGIONAL_WARNING)}. Weather-grid reference points are shown only when
retained by the source contract; they are not field boundaries or synthetic cell polygons.</p>
<div class="grid">
<div class="pane">
<div class="ph"><span class="lbl">Layer × lead day — full outlook</span><span class="lbl" id="mxunit">mm/day</span></div>
<div class="pb">
<div class="mx" id="mx"></div>
<div class="mxfoot">
<div class="mxlegend"><span>0</span><div class="r"></div><span>8+ mm/day</span></div>
<div class="mxnote"><span class="swatch-na"></span>Hatched cells carry no value in this run. An absent
scenario is shown as absent, never as zero and never filled from another layer.</div>
</div>
<div class="defs">
<div class="lbl" style="margin-bottom:9px">Layer definitions — product contract</div>
<dl id="defs">{definitions}</dl>
</div>
</div>
</div>
<div class="pane">
<div class="ph"><span class="lbl">Spatial — weather-grid reference points</span><span class="lbl" id="mapdate"></span></div>
<div class="mapbox">
<svg id="map" role="img" aria-label="Weather-grid reference points over Idaho"></svg>
<div class="card tl"><div class="k" id="mi-layer"></div><div class="v" id="mi-val"></div><div class="m" id="mi-meta"></div></div>
<div class="card bl"><div class="rt">viridis · mm/day</div><div class="r"></div>
<div class="rl"><span>0</span><span>4</span><span>8+</span></div></div>
</div>
<div class="ph"><span class="lbl">Ensemble — p10 / p50 / p90 across lead days</span><span class="lbl">drag to scrub</span></div>
<div class="fanbox"><svg id="fan"></svg></div>
</div>
<div class="pane">
<div class="ph"><span class="lbl">Readout</span>
<span class="qbtns" id="qbtns"><button data-q="p10" type="button">p10</button><button data-q="p50" class="on" type="button">p50</button><button data-q="p90" type="button">p90</button></span>
</div>
<div class="pb"><table class="ro"><tbody id="ro"></tbody></table></div>
<div class="foot" id="foot"></div>
</div>
</div>
<script>const DATA={data};const LAYERS={layer_meta};const SCALAR_LAYER={scalar};{_VIEWER_JS}</script>
</body></html>"""


def _publish_candidate_directory(destination: Path, artifacts: Mapping[str, bytes]) -> None:
    """Atomically expose a complete map candidate below a trusted output root.

    The final candidate name is an exclusive relative symlink to a private,
    fsynced generation.  This intentionally mirrors immutable outlook-run
    publication: readers cannot observe a file-by-file partial candidate, and
    no retry can replace another publisher's final name.
    """
    destination = Path(destination)
    if not destination.name or destination.name in {".", ".."}:
        raise ValueError("map candidate destination must identify a safe basename")
    if destination != destination.parent / destination.name:
        raise ValueError("map candidate destination must identify a safe basename")
    output_root = _open_output_root(destination.parent, create=False)
    private_generation = None
    try:
        private_generation = _create_private_generation(output_root.fd, destination.name)
        for filename, contents in artifacts.items():
            _write_new_bytes_at(private_generation.fd, filename, contents)
        _fsync_directory_fd(private_generation.fd)
        _publish_private_artifact(
            output_root.fd, private_generation, destination.name
        )
    finally:
        if private_generation is not None:
            _close_descriptor(private_generation.fd)
        _close_descriptor(output_root.fd)


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")


def _script_safe_json(payload: Mapping[str, object]) -> str:
    """Serialize data without allowing a source string to terminate ``script``."""
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _reject_duplicate_object_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON objects must not contain duplicate keys")
        result[key] = value
    return result
