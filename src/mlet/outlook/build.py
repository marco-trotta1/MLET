"""Build immutable, fixture-replayable Idaho regional ET outlook artifacts.

The public build boundary deliberately accepts the deterministic software
fixtures used by this repository, but does not turn unprovenanced JSONL files
into an operational forecast.  Live GEFS import remains gated by its canonical
artifact receipt and the corresponding OpenET/CDL artifact adapters have not
yet been implemented.  Rejecting an ambiguous non-fixture input is preferable
to manufacturing provenance, soil-water state, or forecast skill evidence.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Iterable, Mapping, Sequence

from mlet.outlook.contracts import OutlookDay, OutlookQuantiles, WeatherMember
from mlet.outlook.crop import (
    CropCoefficientAssignment,
    CropCoefficientInput,
    apply_crop_coefficients,
    potential_et_c,
)
from mlet.outlook.eto import eto_for_member, summarize_members
from mlet.outlook.manifest import RunManifest, build_manifest
from mlet.outlook.scenarios import (
    ScenarioProjection,
    project_no_irrigation_from_state,
    project_well_watered,
)
from mlet.outlook.serve_contract import write_serve_contract
from mlet.outlook.state import (
    NoIrrigationState,
    StateProvenance,
    eta_analysis_from_openet,
    initialize_no_irrigation_state,
)
from mlet.sources.cdl import CdlLayerMetadata, CropFraction
from mlet.sources.gefs import normalize_gefs_rows
from mlet.sources.openet_state import EtaAnalysis, normalize_openet_state


_ARTIFACT_SCHEMA_VERSION = 1
_FIXTURE_GRID_AREA_M2 = 100.0
_FIXTURE_KC_BY_CROP_CODE = {
    "1": 1.15,
    "36": 1.10,
}
_FIXTURE_STATE_PROVENANCE_URI = "https://example.invalid/mlet-fixture-state"
_FIXTURE_CDL_URI = "https://example.invalid/mlet-fixture-cdl"
_FIXTURE_KC_SOURCE = "mlet-fixture-kc-table"


@dataclass(frozen=True)
class BuildResult:
    """Location and cardinality of one immutable outlook build."""

    run_id: str
    run_dir: Path
    day_count: int
    cell_count: int


@dataclass(frozen=True)
class _FixtureInputs:
    """Validated fixture inputs plus the deterministic forecast issue time."""

    weather: tuple[WeatherMember, ...]
    state_rows: tuple[dict[str, object], ...]
    crop_rows: tuple[dict[str, object], ...]
    issued_at: datetime


def build_outlook(
    *, weather_path: Path, state_path: Path, crop_path: Path, out_dir: Path
) -> BuildResult:
    """Build one immutable 20-day regional ET outlook from validated inputs.

    Fixtures are accepted solely to exercise the artifact contract.  They are
    conspicuously marked non-scientific in every input and output.  Nonfixture
    JSONL is refused until all three operational source adapters can retain the
    source-specific provenance required by the frozen product contract.
    """
    weather_path = _require_regular_file(weather_path, "weather_path")
    state_path = _require_regular_file(state_path, "state_path")
    crop_path = _require_regular_file(crop_path, "crop_path")
    inputs = _load_fixture_inputs(weather_path, state_path, crop_path)
    git_revision = _git_revision()
    manifest = build_manifest(
        _format_utc(inputs.issued_at),
        {"crop": crop_path, "state": state_path, "weather": weather_path},
        git_revision,
        _format_utc(inputs.issued_at),
        source_observed_through={
            "crop": None,
            "state": _latest_observed_through(inputs.state_rows),
            "weather": None,
        },
    )
    days = _calculate_outlook_days(inputs, crop_path)
    _validate_days(days, inputs.issued_at)
    destination_root = _prepare_output_root(out_dir)
    destination = destination_root / manifest.run_id
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{manifest.run_id}.building-", dir=destination_root)
    )
    try:
        # Persist the private directory entry before it receives the durable
        # artifact.  The eventual public run id is an exclusive symlink claim,
        # so an interrupted build can leave only an unreferenced private tree.
        _fsync_directory(destination_root)
        outlook_path = temporary / "outlook.json"
        summary_path = temporary / "summary.json"
        validation_path = temporary / "validation.json"
        manifest_path = temporary / "manifest.json"
        write_serve_contract(days, manifest, outlook_path)
        _write_new_json(summary_path, _summary_payload(days, manifest))
        _write_new_json(validation_path, _validation_payload(manifest))
        _fsync_files((outlook_path, summary_path, validation_path))
        completed_manifest = manifest.with_artifact_sha256(
            {
                path.name: _sha256(path)
                for path in (outlook_path, summary_path, validation_path)
            }
        )
        _write_new_text(manifest_path, completed_manifest.to_json() + "\n")
        _fsync_files((manifest_path,))
        _fsync_directory(temporary)
        _publish_private_artifact(temporary, destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return BuildResult(
        run_id=manifest.run_id,
        run_dir=destination,
        day_count=20,
        cell_count=len({day.grid_id for day in days}),
    )


def _publish_private_artifact(temporary: Path, destination: Path) -> None:
    """Atomically expose a durable private artifact without replacing a run id.

    The output root and the private staging directory must be on one local
    POSIX filesystem that provides exclusive ``symlink(2)`` creation and
    durable directory ``fsync``.  ``symlink`` fails if *any* name already
    exists at ``destination`` (including an empty directory), unlike a
    check-then-rename sequence.  The relative link keeps the private artifact
    movable together with its output root while the public stable run id
    remains the sole artifact entry point.
    """
    try:
        relative_target = os.path.relpath(temporary, start=destination.parent)
        os.symlink(relative_target, destination, target_is_directory=True)
    except FileExistsError as error:
        raise ValueError(f"outlook run directory already exists: {destination}") from error
    _fsync_directory(destination.parent)


def _load_fixture_inputs(
    weather_path: Path, state_path: Path, crop_path: Path
) -> _FixtureInputs:
    weather_rows = _read_jsonl(weather_path, "weather")
    state_rows = _read_jsonl(state_path, "state")
    crop_rows = _read_jsonl(crop_path, "crop")
    all_rows = (*weather_rows, *state_rows, *crop_rows)
    if not all_rows or any(row.get("fixture_non_scientific") is not True for row in all_rows):
        raise ValueError(
            "build-outlook accepts direct JSONL only for explicit non-scientific "
            "fixtures; operational inputs require manifest-backed source adapters"
        )
    issue_time = _fixture_issue_time(weather_rows)
    weather = tuple(normalize_gefs_rows(weather_rows, issued_at=_format_utc(issue_time)))
    if any(member.issued_at != issue_time for member in weather):
        raise ValueError("fixture weather issue time is inconsistent")
    return _FixtureInputs(
        weather=weather,
        state_rows=tuple(state_rows),
        crop_rows=tuple(crop_rows),
        issued_at=issue_time,
    )


def _fixture_issue_time(weather_rows: Sequence[dict[str, object]]) -> datetime:
    if not weather_rows:
        raise ValueError("weather fixture contains no rows")
    issue_values = {row.get("issued_at") for row in weather_rows if "issued_at" in row}
    if issue_values:
        if len(issue_values) != 1 or any("issued_at" not in row for row in weather_rows):
            raise ValueError("fixture weather rows must consistently declare issued_at")
        return _parse_utc(issue_values.pop(), "fixture weather issued_at")
    valid_dates = [_parse_date(row.get("valid_date"), "fixture weather valid_date") for row in weather_rows]
    first_valid_date = min(valid_dates)
    return datetime.combine(
        first_valid_date - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
    )


def _calculate_outlook_days(inputs: _FixtureInputs, crop_path: Path) -> tuple[OutlookDay, ...]:
    analyses = _fixture_analyses(inputs.state_rows, inputs.issued_at)
    states = _fixture_no_irrigation_states(inputs.weather, inputs.state_rows, inputs.issued_at)
    crop_assignments = _fixture_crop_assignments(
        inputs.weather, inputs.crop_rows, crop_path, inputs.issued_at
    )
    values: dict[tuple[str, date], dict[str, list[float] | list[None]]] = defaultdict(
        lambda: {
            "eto": [],
            "potential": [],
            "well_watered": [],
            "no_irrigation": [],
        }
    )
    depletion_by_member: dict[tuple[str, str], float | None] = {
        (grid_id, member_id): state.initial_depletion_mm
        for grid_id, state in states.items()
        for member_id in {item.member_id for item in inputs.weather if item.grid_id == grid_id}
    }
    for member in inputs.weather:
        key = (member.grid_id, member.valid_date)
        eto_mm = eto_for_member(member)
        assignment = crop_assignments[(member.grid_id, member.valid_date)]
        potential = potential_et_c(eto_mm, assignment).potential_et_c_mm
        well_watered = project_well_watered(
            potential, precip_mm=member.precip_mm, issued_at=inputs.issued_at
        )
        state = states[member.grid_id]
        member_state_key = (member.grid_id, member.member_id)
        projected_state = state
        if state.is_available:
            projected_state = NoIrrigationState(
                grid_id=state.grid_id,
                taw_mm=state.taw_mm,
                raw_mm=state.raw_mm,
                initial_depletion_mm=depletion_by_member[member_state_key],
                provenance=state.provenance,
                issued_at=state.issued_at,
                unavailable_reason=None,
            )
        no_irrigation = project_no_irrigation_from_state(
            projected_state,
            potential_et_mm=potential,
            precip_mm=member.precip_mm,
            issued_at=inputs.issued_at,
        )
        if no_irrigation.depletion_mm is not None:
            depletion_by_member[member_state_key] = no_irrigation.depletion_mm
        grouped = values[key]
        _append_member_values(grouped, eto_mm, potential, well_watered, no_irrigation)

    result: list[OutlookDay] = []
    for grid_id, valid_date in sorted(values):
        grouped = values[(grid_id, valid_date)]
        no_irrigation = _no_irrigation_quantiles(grouped["no_irrigation"])
        analysis = eta_analysis_from_openet(analyses.get(grid_id), issued_at=inputs.issued_at)
        result.append(
            OutlookDay(
                grid_id=grid_id,
                valid_date=valid_date,
                eto_mm=summarize_members(_float_values(grouped["eto"], "eto")),
                potential_et_c_mm=summarize_members(
                    _float_values(grouped["potential"], "potential ETc")
                ),
                eta_well_watered_mm=summarize_members(
                    _float_values(grouped["well_watered"], "well-watered scenario")
                ),
                eta_no_irrigation_mm=no_irrigation,  # type: ignore[arg-type]
                eta_analysis_mm=analysis.eta_analysis_mm,
                eta_analysis_date=analysis.eta_analysis_date,
            )
        )
    return tuple(result)


def _fixture_analyses(
    rows: Sequence[dict[str, object]], issued_at: datetime
) -> dict[str, EtaAnalysis]:
    normalized = normalize_openet_state(
        rows, issued_at=_format_utc(issued_at), retrieved_at=_format_utc(issued_at)
    )
    by_grid: dict[str, EtaAnalysis] = {}
    for analysis in normalized:
        if analysis.grid_id in by_grid:
            raise ValueError(
                "fixture state must contain at most one eligible OpenET analysis per grid"
            )
        by_grid[analysis.grid_id] = analysis
    return by_grid


def _fixture_no_irrigation_states(
    weather: Sequence[WeatherMember],
    state_rows: Sequence[dict[str, object]],
    issued_at: datetime,
) -> dict[str, NoIrrigationState]:
    state_rows_by_grid = {str(row.get("grid_id")): row for row in state_rows}
    states: dict[str, NoIrrigationState] = {}
    for grid_id in sorted({member.grid_id for member in weather}):
        state_row = state_rows_by_grid.get(grid_id)
        if state_row is None:
            raise ValueError("fixture state must name every weather grid")
        source_available_at = _parse_utc(
            state_row.get("source_available_at"), "fixture state source_available_at"
        )
        observed_date = _parse_date(
            state_row.get("observation_date"), "fixture state observation_date"
        )
        states[grid_id] = initialize_no_irrigation_state(
            grid_id=grid_id,
            taw_mm=100.0,
            raw_mm=50.0,
            initial_depletion_mm=None,
            provenance=StateProvenance(
                source_name="fixture-state-unavailable",
                source_version="fixture-v1",
                source_uri=_FIXTURE_STATE_PROVENANCE_URI,
                observed_date=observed_date,
                source_available_at=source_available_at,
            ),
            issued_at=issued_at,
        )
    return states


def _fixture_crop_assignments(
    weather: Sequence[WeatherMember],
    crop_rows: Sequence[dict[str, object]],
    crop_path: Path,
    issued_at: datetime,
) -> dict[tuple[str, date], CropCoefficientAssignment]:
    rows_by_grid: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in crop_rows:
        grid_id = row.get("grid_id")
        if not isinstance(grid_id, str) or not grid_id.strip():
            raise ValueError("fixture crop grid_id must be non-empty text")
        rows_by_grid[grid_id].append(row)
    metadata = CdlLayerMetadata(
        source_year=2024,
        layer_version="mlet-fixture-2024",
        legend_version="usda-nass-cdl-2024",
        release_at="2025-02-27T00:00:00Z",
        upstream_uri=_FIXTURE_CDL_URI,
        sha256=_sha256(crop_path),
    )
    assignments: dict[tuple[str, date], CropCoefficientAssignment] = {}
    for grid_id, valid_date in sorted({(member.grid_id, member.valid_date) for member in weather}):
        fractions = _fixture_fractions(grid_id, rows_by_grid.get(grid_id, []), metadata)
        coefficients = _fixture_coefficients(fractions, issued_at)
        assignments[(grid_id, valid_date)] = apply_crop_coefficients(
            fractions, coefficients, issued_at=issued_at, valid_date=valid_date
        )
    return assignments


def _fixture_fractions(
    grid_id: str,
    rows: Sequence[dict[str, object]],
    metadata: CdlLayerMetadata,
) -> tuple[CropFraction, ...]:
    if not rows:
        raise ValueError("fixture crop input must name every weather grid")
    parsed: list[tuple[str, str, float, float]] = []
    total_area = 0.0
    for row in rows:
        source_year = row.get("source_year")
        if source_year != 2024:
            raise ValueError("fixture crop source_year must be 2024")
        raw_code = row.get("crop_code")
        if isinstance(raw_code, bool) or not isinstance(raw_code, (int, str)):
            raise ValueError("fixture crop_code must identify a supported fixture crop")
        crop_code = str(raw_code)
        kc = _FIXTURE_KC_BY_CROP_CODE.get(crop_code)
        if kc is None:
            raise ValueError("fixture crop_code has no explicit fixture crop coefficient")
        crop_class = row.get("crop_class")
        if not isinstance(crop_class, str) or not crop_class.strip():
            raise ValueError("fixture crop_class must be non-empty text")
        area = _positive_float(row.get("area_m2"), "fixture crop area_m2")
        confidence = _bounded_float(row.get("confidence"), "fixture crop confidence", 0.0, 100.0)
        total_area += area
        parsed.append((crop_code, crop_class, area, confidence))
    coverage = total_area / _FIXTURE_GRID_AREA_M2
    if not 0.0 < coverage <= 1.0:
        raise ValueError("fixture crop coverage must be within (0, 1]")
    return tuple(
        CropFraction(
            grid_id=grid_id,
            crop_code=crop_code,
            crop_class=crop_class,
            fraction=area / _FIXTURE_GRID_AREA_M2,
            coverage_fraction=coverage,
            source_year=2024,
            confidence_pct=confidence,
            layer_metadata=metadata,
        )
        for crop_code, crop_class, area, confidence in parsed
    )


def _fixture_coefficients(
    fractions: Iterable[CropFraction], issued_at: datetime
) -> tuple[CropCoefficientInput, ...]:
    coefficients: list[CropCoefficientInput] = []
    for fraction in fractions:
        assert fraction.crop_code is not None
        coefficients.append(
            CropCoefficientInput(
                crop_code=fraction.crop_code,
                crop_class=fraction.crop_class,
                kc=_FIXTURE_KC_BY_CROP_CODE[fraction.crop_code],
                effective_date=issued_at.date(),
                vegetation_state="fixture-fixed-software-input",
                source_name=_FIXTURE_KC_SOURCE,
                source_version="fixture-v1",
                source_available_at=issued_at,
            )
        )
    return tuple(coefficients)


def _append_member_values(
    grouped: dict[str, list[float] | list[None]],
    eto_mm: float,
    potential_mm: float,
    well_watered: ScenarioProjection,
    no_irrigation: ScenarioProjection,
) -> None:
    if well_watered.eta_mm is None:
        raise ValueError("well-watered scenario must always be available")
    grouped["eto"].append(eto_mm)  # type: ignore[arg-type]
    grouped["potential"].append(potential_mm)  # type: ignore[arg-type]
    grouped["well_watered"].append(well_watered.eta_mm)  # type: ignore[arg-type]
    grouped["no_irrigation"].append(no_irrigation.eta_mm)  # type: ignore[arg-type]


def _no_irrigation_quantiles(values: list[float] | list[None]) -> OutlookQuantiles | None:
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("no-irrigation scenario availability must be consistent across members")
    return summarize_members(_float_values(values, "no-irrigation scenario"))


def _float_values(values: list[float] | list[None], label: str) -> list[float]:
    if not values or any(value is None for value in values):
        raise ValueError(f"{label} members must all be available")
    return [float(value) for value in values]


def _validate_days(days: Sequence[OutlookDay], issued_at: datetime) -> None:
    if not days:
        raise ValueError("outlook must contain at least one grid cell")
    expected = {issued_at.date() + timedelta(days=lead) for lead in range(1, 21)}
    by_grid: dict[str, set[date]] = defaultdict(set)
    for day in days:
        if day.valid_date in by_grid[day.grid_id]:
            raise ValueError("outlook must not duplicate a grid cell and valid date")
        by_grid[day.grid_id].add(day.valid_date)
    for grid_id, dates in by_grid.items():
        if dates != expected:
            raise ValueError(
                f"outlook grid {grid_id!r} must contain exactly twenty contiguous lead dates"
            )


def _summary_payload(days: Sequence[OutlookDay], manifest: RunManifest) -> dict[str, object]:
    layer_names = (
        "eto_mm",
        "potential_et_c_mm",
        "eta_well_watered_mm",
        "eta_no_irrigation_mm",
        "eta_analysis_mm",
    )
    return {
        "schema_version": _ARTIFACT_SCHEMA_VERSION,
        "run_id": manifest.run_id,
        "issued_at": _format_utc(manifest.issued_at),
        "fixture_non_scientific": True,
        "not_field_scale": True,
        "spatial_resolution": "native_weather_grid",
        "cell_count": len({day.grid_id for day in days}),
        "day_count": 20,
        "layers": list(layer_names),
        "message": (
            "Deterministic software fixture output only; it is not a forecast, "
            "hindcast result, or scientific evidence."
        ),
    }


def _validation_payload(manifest: RunManifest) -> dict[str, object]:
    return {
        "schema_version": _ARTIFACT_SCHEMA_VERSION,
        "run_id": manifest.run_id,
        "promotion": False,
        "fixture_non_scientific": True,
        "blockers": [
            "software fixture only; no real archived hindcast evidence",
            "outlook promotion requires the preregistered no-lookahead hindcast gate",
        ],
    }


def _latest_observed_through(rows: Sequence[dict[str, object]]) -> date | None:
    dates = [
        _parse_date(row.get("observation_date"), "fixture state observation_date")
        for row in rows
    ]
    return max(dates) if dates else None


def _read_jsonl(path: Path, label: str) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"cannot read {label} input: {path}") from error
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{label} JSONL line {line_number} is invalid") from error
        if not isinstance(value, dict):
            raise ValueError(f"{label} JSONL line {line_number} must be an object")
        records.append(value)
    if not records:
        raise ValueError(f"{label} input contains no records")
    return records


def _require_regular_file(path: Path, label: str) -> Path:
    value = Path(path)
    if value.is_symlink() or not value.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    return value


def _prepare_output_root(path: Path) -> Path:
    root = Path(path)
    if root.is_symlink():
        raise ValueError("out_dir must not be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("out_dir must be a real directory")
    return root


def _git_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("build-outlook requires a checked-out git revision") from error


def _parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be an explicit UTC ISO-8601 timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError(
            f"{label} must be an explicit UTC ISO-8601 timestamp ending in Z"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must be an explicit UTC ISO-8601 timestamp ending in Z")
    return parsed.astimezone(timezone.utc)


def _parse_date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} must be YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must be YYYY-MM-DD")
    return parsed


def _positive_float(value: object, label: str) -> float:
    return _bounded_float(value, label, 0.0, float("inf"), strict_minimum=True)


def _bounded_float(
    value: object,
    label: str,
    minimum: float,
    maximum: float,
    *,
    strict_minimum: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or not (
        minimum < result <= maximum
        if strict_minimum
        else minimum <= result <= maximum
    ):
        raise ValueError(f"{label} is outside its allowed range")
    return result


def _write_new_json(path: Path, payload: Mapping[str, object]) -> None:
    _write_new_text(
        path,
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
    )


def _write_new_text(path: Path, text: str) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_files(paths: Iterable[Path]) -> None:
    for path in paths:
        with path.open("rb") as handle:
            os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("timestamp must be explicit UTC")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
