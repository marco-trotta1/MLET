"""Write MLET series in the neuralhydrology GenericDataset layout.

``GenericDataset`` (v1.13.0, BSD-3-Clause) expects, under a single root:

    time_series/<entity_id>.nc   one netCDF per entity, coordinate named 'date'
    attributes/*.csv             static attributes, indexed by entity id

Missing values must be NaN. The upstream docstring is explicit that sentinels
such as -999 will not be recognised as missing and will be read as data, so this
module refuses to write them.

Static attributes are physical field properties only. Writing a site identifier
as a feature would satisfy the file format while invalidating withheld-field
evaluation, which is the evaluation MLET's research question depends on, so
there is no option to enable it. neuralhydrology's ``use_basin_id_encoding`` is
the mechanism to avoid; ``EA-LSTM``, which gates on static attributes, is the one
to use.

Uses xarray and pandas only. No torch, so this runs on a plain install.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

import numpy as np
import pandas as pd

#: Values that must never reach a netCDF file, because GenericDataset would read
#: them as observations rather than gaps.
FORBIDDEN_SENTINELS = (-999.0, -9999.0, -99.999)

#: Attribute-name fragments that would encode entity identity rather than
#: physical properties.
IDENTIFIER_FRAGMENTS = (
    "site_id",
    "site_index",
    "basin_id",
    "basin_index",
    "station_id",
    "station_index",
    "entity_id",
    "entity_index",
    "one_hot",
)

IDENTIFIER_NAMES = frozenset(
    {
        "id",
        "basin",
        "site",
        "station",
        "site_code",
        "basin_code",
        "station_code",
        "entity_code",
        "grid_id",
        "cell_id",
        "field_id",
    }
)


def _safe_component(value: object, context: str) -> str:
    """Return a filename component that cannot escape its export directory."""
    if not isinstance(value, str):
        raise ValueError(f"{context} must be a safe path component string")
    if value in {"", ".", ".."}:
        raise ValueError(f"{context} must be a safe path component")
    if "\x00" in value or "/" in value or "\\" in value:
        raise ValueError(f"{context} must be a safe path component")

    posix_path = Path(value)
    windows_path = PureWindowsPath(value)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError(f"{context} must be a safe path component")
    return value


def _looks_like_identifier(name: object) -> bool:
    """Return whether a field name can encode entity identity."""
    if not isinstance(name, str):
        return False
    lowered = name.casefold()
    return lowered in IDENTIFIER_NAMES or any(
        fragment in lowered for fragment in IDENTIFIER_FRAGMENTS
    )


def _export_root(root: Path) -> Path:
    """Create an export root only when its existing path is a real directory."""
    root = Path(root)
    if root.is_symlink():
        raise ValueError("export root must not be a symlink")
    if root.exists() and not root.is_dir():
        raise ValueError("export root must be a directory")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _output_directory(root: Path, name: str) -> Path:
    """Create an output tree only when its existing path is a real directory."""
    destination = _export_root(root) / name
    if destination.is_symlink():
        raise ValueError(f"{name} output directory must not be a symlink")
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"{name} output path must be a directory")
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def _output_file(destination: Path, name: str, context: str) -> Path:
    """Return a final output path without following an existing link or directory."""
    path = destination / name
    if path.is_symlink():
        raise ValueError(f"{context} must not be a symlink")
    if path.exists() and not path.is_file():
        raise ValueError(f"{context} must be a file")
    return path


def _validate_scalar_numeric(value: object, context: str) -> None:
    """Require a real numeric scalar; NaN is the permitted missing marker."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, float, np.integer, np.floating)
    ):
        raise ValueError(f"{context} must be a scalar numeric value or NaN")


@dataclass(frozen=True)
class SiteAttributes:
    """Static physical attributes for one site."""

    site_id: str
    values: dict[str, float]

    def __post_init__(self) -> None:
        _safe_component(self.site_id, "site_id")
        if not isinstance(self.values, Mapping) or not self.values:
            raise ValueError(f"site {self.site_id} has no attributes")
        for name, value in self.values.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("attribute names must be non-empty strings")
            if _looks_like_identifier(name):
                raise ValueError(
                    f"attribute {name!r} looks like an entity identifier; conditioning "
                    "on identity rather than physical attributes invalidates "
                    "withheld-field evaluation"
                )
            _validate_scalar_numeric(value, f"site {self.site_id} attribute {name!r}")


def _numeric_values(values: object, context: str) -> np.ndarray:
    """Convert values to floats while preserving NaN as the missing marker."""
    try:
        numeric = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must contain numeric values or NaN") from exc
    if np.any(np.isinf(numeric)):
        raise ValueError(f"{context} contains infinite values")
    return numeric


def _reject_sentinels(values: object, context: str) -> None:
    numeric = _numeric_values(values, context)
    for sentinel in FORBIDDEN_SENTINELS:
        if np.any(np.isclose(numeric, sentinel, rtol=0.0, atol=1e-9)):
            raise ValueError(
                f"{context} contains the sentinel {sentinel}; "
                "GenericDataset requires NaN for missing values"
            )


def _validate_unique_site_ids(site_ids: Sequence[str], context: str) -> None:
    """Reject ids that collide under case-insensitive filesystem semantics."""
    folded = [site_id.casefold() for site_id in site_ids]
    if len(folded) != len(set(folded)):
        raise ValueError(f"{context} requires unique site_id values")


def _validate_attributes(attributes: Sequence[SiteAttributes]) -> list[SiteAttributes]:
    items = list(attributes)
    if not items:
        raise ValueError("attribute export requires at least one site")

    site_ids = [item.site_id for item in items]
    _validate_unique_site_ids(site_ids, "attribute export")

    key_sets = {frozenset(item.values) for item in items}
    if len(key_sets) != 1:
        raise ValueError("all sites must declare the same attribute names")

    for item in items:
        for name, value in item.values.items():
            _reject_sentinels(value, f"site {item.site_id} attribute {name!r}")
    return items


def write_time_series(root: Path, site_id: str, frame: pd.DataFrame) -> Path:
    """Write one site's daily series to ``root/time_series/<site_id>.nc``."""
    site_id = _safe_component(site_id, "site_id")
    root = Path(root)
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("time-series data must be a pandas DataFrame")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("time-series frame must be indexed by a DatetimeIndex")
    if frame.index.has_duplicates:
        raise ValueError(f"site {site_id} has duplicate dates")
    if not frame.index.is_monotonic_increasing:
        raise ValueError(f"site {site_id} dates must be sorted ascending")
    if frame.empty:
        raise ValueError(f"site {site_id} has no rows")
    if len(frame.index) > 1 and not np.all(
        frame.index[1:] - frame.index[:-1] == pd.Timedelta(days=1)
    ):
        raise ValueError(f"site {site_id} dates must have one-day spacing")

    for column in frame.columns:
        if _looks_like_identifier(column):
            raise ValueError(
                f"column {column!r} looks like an entity identifier; conditioning "
                "on identity rather than physical observations invalidates "
                "withheld-field evaluation"
            )
        _reject_sentinels(frame[column].to_numpy(), f"site {site_id} column {column!r}")

    destination = _output_directory(root, "time_series")
    path = _output_file(destination, f"{site_id}.nc", "time-series output file")

    dataset = frame.rename_axis("date").to_xarray()
    dataset.to_netcdf(path)
    dataset.close()
    return path


def write_attributes(
    root: Path, attributes: Sequence[SiteAttributes], *, filename: str = "attributes.csv"
) -> Path:
    """Write static attributes to ``root/attributes/<filename>``, indexed by site."""
    filename = _safe_component(filename, "filename")
    root = Path(root)
    items = _validate_attributes(attributes)

    destination = _output_directory(root, "attributes")
    path = _output_file(destination, filename, "attribute output file")

    frame = pd.DataFrame(
        [item.values for item in items],
        index=pd.Index([item.site_id for item in items], name="site_id"),
    ).sort_index()
    frame.to_csv(path)
    return path


def export_generic_dataset(
    root: Path, series: Mapping[str, object], attributes: Sequence[SiteAttributes]
) -> Path:
    """Write a complete GenericDataset tree and return its root."""
    root = Path(root)
    if not series:
        raise ValueError("export requires at least one site series")

    items = _validate_attributes(attributes)
    series_site_ids = list(series)
    _validate_unique_site_ids(series_site_ids, "series export")
    series_by_folded_id = {site_id.casefold(): site_id for site_id in series_site_ids}
    attribute_by_folded_id = {
        item.site_id.casefold(): item.site_id for item in items
    }
    missing = [
        series_by_folded_id[key]
        for key in sorted(set(series_by_folded_id) - set(attribute_by_folded_id))
    ]
    if missing:
        raise ValueError(f"every site needs attributes; missing for {missing}")
    extra = [
        attribute_by_folded_id[key]
        for key in sorted(set(attribute_by_folded_id) - set(series_by_folded_id))
    ]
    if extra:
        raise ValueError(f"site coverage must match exactly; attributes have {extra}")

    for site_id in sorted(series):
        write_time_series(root, site_id, series[site_id])
    write_attributes(root, items)
    return root
