"""Tests for target-grid spatial blocking and fold derivation."""

import hashlib

import pytest

from mlet.outlook.spatial import (
    spatial_block_for_grid_id,
    spatial_fold_for_grid_id,
    validate_spatial_fold,
)


def test_grid_id_maps_to_one_degree_block() -> None:
    assert spatial_block_for_grid_id("43.50:-116.00") == "43:-116"


def test_fold_uses_the_full_sha256_digest() -> None:
    block = "43:-116"
    expected = int(hashlib.sha256(block.encode("utf-8")).hexdigest(), 16) % 5

    assert spatial_fold_for_grid_id("43.50:-116.00") == expected


def test_boii_target_grid_cell_maps_to_fold_two() -> None:
    assert spatial_fold_for_grid_id("43.50:-116.00") == 2


def test_station_coordinates_do_not_control_target_grid_fold() -> None:
    target_grid_id = "43.50:-116.00"
    station_latitude = 43.60
    station_longitude = -116.20

    assert (station_latitude, station_longitude) != (43.50, -116.00)
    assert spatial_fold_for_grid_id(target_grid_id) == 2


def test_conflicting_supplied_fold_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not match"):
        validate_spatial_fold("43.50:-116.00", 4)


@pytest.mark.parametrize(
    "grid_id",
    ["", "43.50", "43.50:-116.00:1", "nan:-116.00", "43.50:inf", "north:-116"],
)
def test_malformed_grid_id_is_rejected_at_the_boundary(grid_id: str) -> None:
    with pytest.raises(ValueError, match="grid_id"):
        spatial_block_for_grid_id(grid_id)
