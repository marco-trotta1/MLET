"""Non-scientific deterministic checks for the GenericDataset export layout."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray

from mlet.hybrid.nh_export import (
    FORBIDDEN_SENTINELS,
    SiteAttributes,
    export_generic_dataset,
    write_attributes,
    write_time_series,
)


def _frame(with_gap: bool = False) -> pd.DataFrame:
    dates = pd.date_range("2026-06-01", periods=5, freq="D")
    eto = [6.1, 6.4, 5.9, 6.8, 7.0]
    measured = [5.2, 5.4, np.nan if with_gap else 5.0, 5.8, 6.1]
    return pd.DataFrame({"eto_mm": eto, "measured_et_mm": measured}, index=dates)


def _make_symlink(link: Path, target: Path, *, target_is_directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"platform cannot create symlinks: {exc}")


def test_time_series_uses_the_required_layout_and_coordinate(tmp_path) -> None:
    path = write_time_series(tmp_path, "site-a", _frame())
    assert path == tmp_path / "time_series" / "site-a.nc"
    with xarray.open_dataset(path) as dataset:
        assert "date" in dataset.coords
        assert list(dataset.data_vars) == ["eto_mm", "measured_et_mm"]
        assert dataset.sizes["date"] == 5


def test_missing_values_round_trip_as_nan(tmp_path) -> None:
    """GenericDataset only recognises NaN; a sentinel would be read as data."""
    path = write_time_series(tmp_path, "site-a", _frame(with_gap=True))
    with xarray.open_dataset(path) as dataset:
        values = dataset["measured_et_mm"].values
        assert np.isnan(values[2])
        assert np.count_nonzero(np.isnan(values)) == 1


@pytest.mark.parametrize("sentinel", FORBIDDEN_SENTINELS)
def test_sentinel_values_are_rejected(tmp_path, sentinel) -> None:
    frame = _frame()
    frame.loc[frame.index[1], "measured_et_mm"] = sentinel
    with pytest.raises(ValueError, match="sentinel"):
        write_time_series(tmp_path, "site-a", frame)


def test_time_series_requires_sorted_unique_dates(tmp_path) -> None:
    frame = _frame().iloc[[1, 0, 2, 3, 4]]
    with pytest.raises(ValueError, match="sorted"):
        write_time_series(tmp_path, "site-a", frame)

    frame = _frame()
    frame.index = frame.index.where(frame.index != frame.index[-1], frame.index[-2])
    with pytest.raises(ValueError, match="duplicate"):
        write_time_series(tmp_path, "site-a", frame)


def test_time_series_requires_one_day_spacing(tmp_path) -> None:
    frame = _frame()
    frame.index = pd.to_datetime(
        ["2026-06-01", "2026-06-02", "2026-06-04", "2026-06-05", "2026-06-06"]
    )
    with pytest.raises(ValueError, match="one-day spacing"):
        write_time_series(tmp_path, "site-a", frame)


def test_attributes_are_indexed_by_site_id(tmp_path) -> None:
    path = write_attributes(
        tmp_path,
        [
            SiteAttributes("site-a", {"taw_mm": 180.0, "root_depth_m": 1.2}),
            SiteAttributes("site-b", {"taw_mm": 210.0, "root_depth_m": 1.4}),
        ],
    )
    assert path == tmp_path / "attributes" / "attributes.csv"
    frame = pd.read_csv(path, index_col=0)
    assert frame.index.name == "site_id"
    assert sorted(frame.index) == ["site-a", "site-b"]
    assert frame.loc["site-b", "taw_mm"] == pytest.approx(210.0)


def test_attributes_reject_case_insensitive_site_collisions(tmp_path) -> None:
    with pytest.raises(ValueError, match="unique site_id"):
        write_attributes(
            tmp_path,
            [
                SiteAttributes("site-a", {"taw_mm": 180.0}),
                SiteAttributes("SITE-A", {"taw_mm": 180.0}),
            ],
        )


def test_attributes_must_share_the_same_keys(tmp_path) -> None:
    with pytest.raises(ValueError, match="same attribute names"):
        write_attributes(
            tmp_path,
            [
                SiteAttributes("site-a", {"taw_mm": 180.0}),
                SiteAttributes("site-b", {"root_depth_m": 1.4}),
            ],
        )


@pytest.mark.parametrize("sentinel", FORBIDDEN_SENTINELS)
def test_attribute_sentinels_are_rejected(tmp_path, sentinel) -> None:
    with pytest.raises(ValueError, match="sentinel"):
        write_attributes(tmp_path, [SiteAttributes("site-a", {"taw_mm": sentinel})])


@pytest.mark.parametrize(
    "bad_component",
    [
        None,
        42,
        Path("site-a"),
        "",
        ".",
        "..",
        "../escape",
        r"..\escape",
        "/tmp/escape",
        "C:escape",
    ],
)
def test_site_id_components_cannot_escape_export_root(tmp_path, bad_component) -> None:
    with pytest.raises(ValueError, match="safe path component"):
        SiteAttributes(bad_component, {"taw_mm": 180.0})
    with pytest.raises(ValueError, match="safe path component"):
        write_time_series(tmp_path, bad_component, _frame())


@pytest.mark.parametrize(
    "bad_component",
    [
        None,
        42,
        Path("attributes.csv"),
        "",
        ".",
        "..",
        "../escape",
        r"..\escape",
        "/tmp/escape",
        "C:escape",
    ],
)
def test_attribute_filenames_cannot_escape_export_root(tmp_path, bad_component) -> None:
    attributes = [SiteAttributes("site-a", {"taw_mm": 180.0})]
    with pytest.raises(ValueError, match="safe path component"):
        write_attributes(tmp_path, attributes, filename=bad_component)


def test_site_identifier_is_never_written_as_an_attribute(tmp_path) -> None:
    """Conditioning on an entity id would invalidate withheld-field evaluation."""
    with pytest.raises(ValueError, match="identifier"):
        write_attributes(tmp_path, [SiteAttributes("site-a", {"site_index": 3.0})])


def test_time_series_identifier_columns_are_never_written_as_features(tmp_path) -> None:
    frame = _frame().assign(site_index=np.arange(5, dtype=float))
    with pytest.raises(ValueError, match="identifier"):
        write_time_series(tmp_path, "site-a", frame)


GENERIC_IDENTIFIER_NAMES = [
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
]


@pytest.mark.parametrize("name", GENERIC_IDENTIFIER_NAMES)
def test_generic_identifier_names_are_rejected_for_attributes(tmp_path, name) -> None:
    with pytest.raises(ValueError, match="identifier"):
        write_attributes(tmp_path, [SiteAttributes("site-a", {name: 3.0})])


@pytest.mark.parametrize("name", GENERIC_IDENTIFIER_NAMES)
def test_generic_identifier_names_are_rejected_for_time_series(tmp_path, name) -> None:
    frame = _frame().assign(**{name: np.arange(5, dtype=float)})
    with pytest.raises(ValueError, match="identifier"):
        write_time_series(tmp_path, "site-a", frame)


@pytest.mark.parametrize("value", [[180.0], (180.0,), "180.0"])
def test_attribute_values_must_be_scalar_numeric_values(tmp_path, value) -> None:
    with pytest.raises(ValueError, match="scalar numeric"):
        SiteAttributes("site-a", {"taw_mm": value})


@pytest.mark.parametrize(
    "value", [180, 180.0, np.int64(180), np.float32(180.0), np.nan]
)
def test_scalar_numeric_attribute_values_are_allowed(tmp_path, value) -> None:
    path = write_attributes(tmp_path, [SiteAttributes("site-a", {"taw_mm": value})])
    frame = pd.read_csv(path, index_col=0)
    if np.isnan(value):
        assert np.isnan(frame.loc["site-a", "taw_mm"])
    else:
        assert frame.loc["site-a", "taw_mm"] == pytest.approx(float(value))


@pytest.mark.parametrize("tree", ["time_series", "attributes"])
def test_existing_output_symlink_is_rejected(tmp_path, tree) -> None:
    target = tmp_path / "outside"
    target.mkdir()
    _make_symlink(tmp_path / tree, target, target_is_directory=True)
    if tree == "time_series":
        with pytest.raises(ValueError, match="must not be a symlink"):
            write_time_series(tmp_path, "site-a", _frame())
    else:
        with pytest.raises(ValueError, match="must not be a symlink"):
            write_attributes(tmp_path, [SiteAttributes("site-a", {"taw_mm": 180.0})])


@pytest.mark.parametrize("tree", ["time_series", "attributes"])
def test_existing_output_non_directory_is_rejected(tmp_path, tree) -> None:
    (tmp_path / tree).write_text("not a directory")
    if tree == "time_series":
        with pytest.raises(ValueError, match="must be a directory"):
            write_time_series(tmp_path, "site-a", _frame())
    else:
        with pytest.raises(ValueError, match="must be a directory"):
            write_attributes(tmp_path, [SiteAttributes("site-a", {"taw_mm": 180.0})])


def test_symlinked_export_root_is_rejected_without_touching_target(tmp_path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    _make_symlink(tmp_path / "export", outside, target_is_directory=True)

    with pytest.raises(ValueError, match="export root must not be a symlink"):
        write_time_series(tmp_path / "export", "site-a", _frame())

    assert not (outside / "time_series").exists()


def test_symlinked_time_series_file_is_rejected_without_touching_target(tmp_path) -> None:
    destination = tmp_path / "time_series"
    destination.mkdir()
    outside = tmp_path / "outside.nc"
    outside.write_bytes(b"preserve this netcdf target")
    _make_symlink(destination / "site-a.nc", outside)

    with pytest.raises(ValueError, match="time-series output file must not be a symlink"):
        write_time_series(tmp_path, "site-a", _frame())

    assert outside.read_bytes() == b"preserve this netcdf target"


def test_symlinked_attributes_file_is_rejected_without_touching_target(tmp_path) -> None:
    destination = tmp_path / "attributes"
    destination.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_bytes(b"preserve this csv target")
    _make_symlink(destination / "attributes.csv", outside)

    with pytest.raises(ValueError, match="attribute output file must not be a symlink"):
        write_attributes(tmp_path, [SiteAttributes("site-a", {"taw_mm": 180.0})])

    assert outside.read_bytes() == b"preserve this csv target"


@pytest.mark.parametrize(
    ("tree", "filename"),
    [("time_series", "site-a.nc"), ("attributes", "attributes.csv")],
)
def test_existing_final_output_directory_is_rejected(tmp_path, tree, filename) -> None:
    destination = tmp_path / tree
    destination.mkdir()
    (destination / filename).mkdir()

    if tree == "time_series":
        with pytest.raises(ValueError, match="output file must be a file"):
            write_time_series(tmp_path, "site-a", _frame())
    else:
        with pytest.raises(ValueError, match="output file must be a file"):
            write_attributes(tmp_path, [SiteAttributes("site-a", {"taw_mm": 180.0})])


def test_export_writes_both_trees_and_every_site(tmp_path) -> None:
    root = export_generic_dataset(
        tmp_path,
        {"site-a": _frame(), "site-b": _frame(with_gap=True)},
        [
            SiteAttributes("site-a", {"taw_mm": 180.0}),
            SiteAttributes("site-b", {"taw_mm": 210.0}),
        ],
    )
    assert (root / "time_series" / "site-a.nc").is_file()
    assert (root / "time_series" / "site-b.nc").is_file()
    assert (root / "attributes" / "attributes.csv").is_file()


def test_export_matches_site_ids_case_insensitively_but_preserves_spelling(tmp_path) -> None:
    root = export_generic_dataset(
        tmp_path,
        {"site-a": _frame()},
        [SiteAttributes("SITE-A", {"taw_mm": 180.0})],
    )
    assert (root / "time_series" / "site-a.nc").is_file()
    attributes = pd.read_csv(root / "attributes" / "attributes.csv", index_col=0)
    assert list(attributes.index) == ["SITE-A"]


def test_export_rejects_case_insensitive_series_collisions(tmp_path) -> None:
    with pytest.raises(ValueError, match="unique site_id"):
        export_generic_dataset(
            tmp_path,
            {"site-a": _frame(), "SITE-A": _frame()},
            [SiteAttributes("site-a", {"taw_mm": 180.0})],
        )


def test_export_rejects_a_site_without_attributes(tmp_path) -> None:
    with pytest.raises(ValueError, match="every site needs attributes"):
        export_generic_dataset(
            tmp_path,
            {"site-a": _frame(), "site-b": _frame()},
            [SiteAttributes("site-a", {"taw_mm": 180.0})],
        )


def test_export_rejects_attributes_for_an_unknown_site(tmp_path) -> None:
    with pytest.raises(ValueError, match="site coverage"):
        export_generic_dataset(
            tmp_path,
            {"site-a": _frame()},
            [
                SiteAttributes("site-a", {"taw_mm": 180.0}),
                SiteAttributes("site-b", {"taw_mm": 210.0}),
            ],
        )
