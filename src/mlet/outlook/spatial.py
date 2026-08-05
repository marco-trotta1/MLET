"""Derive frozen spatial blocks and folds from canonical target grid IDs."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import hashlib
import re


_COORDINATE = r"[+-]?\d+(?:\.\d+)?"
_GRID_ID_PATTERN = re.compile(
    rf"^(?P<latitude>{_COORDINATE}):(?P<longitude>{_COORDINATE})$"
)


def parse_grid_id(grid_id: object) -> tuple[Decimal, Decimal]:
    """Parse one canonical latitude:longitude grid identifier."""
    if not isinstance(grid_id, str):
        raise ValueError("grid_id must be canonical latitude:longitude text")
    match = _GRID_ID_PATTERN.fullmatch(grid_id)
    if match is None:
        raise ValueError("grid_id must be canonical latitude:longitude text")
    try:
        latitude = Decimal(match["latitude"])
        longitude = Decimal(match["longitude"])
    except InvalidOperation as error:
        raise ValueError("grid_id must contain finite numeric coordinates") from error
    if not latitude.is_finite() or not longitude.is_finite():
        raise ValueError("grid_id must contain finite numeric coordinates")
    if not Decimal("-90") <= latitude <= Decimal("90"):
        raise ValueError("grid_id latitude must be between -90 and 90 degrees")
    if not Decimal("-180") <= longitude <= Decimal("180"):
        raise ValueError("grid_id longitude must be between -180 and 180 degrees")
    return latitude, longitude


def spatial_block_for_grid_id(grid_id: object) -> str:
    """Return the one-degree block containing the target grid point."""
    latitude, longitude = parse_grid_id(grid_id)
    latitude_block = int(latitude.to_integral_value(rounding=ROUND_FLOOR))
    longitude_block = int(longitude.to_integral_value(rounding=ROUND_FLOOR))
    return f"{latitude_block}:{longitude_block}"


def spatial_fold_for_grid_id(grid_id: object) -> int:
    """Return the frozen five-way fold for the target grid point."""
    block = spatial_block_for_grid_id(grid_id)
    digest = hashlib.sha256(block.encode("utf-8")).hexdigest()
    return int(digest, 16) % 5


def validate_spatial_fold(grid_id: object, supplied_fold: object) -> int:
    """Validate a supplied fold against the target grid point and return it."""
    if type(supplied_fold) is not int or supplied_fold not in range(5):
        raise ValueError("supplied spatial fold must be an integer from 0 through 4")
    derived_fold = spatial_fold_for_grid_id(grid_id)
    if supplied_fold != derived_fold:
        raise ValueError(
            "supplied spatial fold does not match the fold derived from target grid_id"
        )
    return derived_fold
