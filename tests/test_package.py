from pathlib import Path

import mlet
from mlet import schema


def test_mlet_imports_from_this_checkout() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    assert Path(mlet.__file__).resolve().is_relative_to(repo_root / "src")


def test_version_is_a_string():
    assert isinstance(mlet.__version__, str)
    assert mlet.__version__


def test_required_columns_contract():
    assert schema.REQUIRED_COLUMNS == ("date", "site_id", "openet_et_mm")


def test_numeric_columns_contract():
    assert schema.NUMERIC_COLUMNS == (
        "openet_et_mm",
        "eto_mm",
        "ndvi",
        "measured_et_mm",
    )


def test_all_columns_order():
    assert schema.ALL_COLUMNS == (
        "date",
        "site_id",
        "openet_et_mm",
        "eto_mm",
        "ndvi",
        "measured_et_mm",
    )


def test_date_format_is_strict_iso():
    assert schema.DATE_FORMAT == "%Y-%m-%d"


def test_physical_bounds_contract():
    assert schema.NONNEGATIVE_COLUMNS == ("openet_et_mm", "eto_mm")
    assert (schema.NDVI_MIN, schema.NDVI_MAX) == (-1.0, 1.0)
