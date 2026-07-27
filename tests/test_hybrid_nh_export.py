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
