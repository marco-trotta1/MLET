from pathlib import Path

from mlet.validator import validate_csv

HEADER = "date,site_id,openet_et_mm,eto_mm,ndvi,measured_et_mm\n"
TEMPLATE = (
    HEADER
    + "2024-06-01,field_001,5.2,5.8,0.71,\n"
    + "2024-06-02,field_001,5.5,6.1,0.73,\n"
)


def write_csv(tmp_path: Path, content: str) -> str:
    path = tmp_path / "data.csv"
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_valid_openet_only_template_has_no_measured_labels(tmp_path):
    result = validate_csv(write_csv(tmp_path, TEMPLATE))
    assert result.is_valid
    assert result.report.has_measured_labels is False
    assert result.report.row_count == 2
    assert result.report.site_count == 1


def test_measured_et_present_sets_has_measured_labels(tmp_path):
    content = HEADER + "2024-06-01,field_001,5.2,5.8,0.71,5.0\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert result.is_valid
    assert result.report.has_measured_labels is True
    assert result.report.measured_present == 1


def test_blank_openet_value_is_allowed_but_counted_incomplete(tmp_path):
    content = (
        HEADER
        + "2024-06-01,field_001,5.2,5.8,0.71,\n"
        + "2024-06-02,field_001,,6.1,0.73,\n"
    )
    result = validate_csv(write_csv(tmp_path, content))
    assert result.is_valid
    assert result.report.openet_present == 1
    assert result.report.row_count == 2


def test_optional_columns_may_be_absent(tmp_path):
    content = "date,site_id,openet_et_mm\n2024-06-01,field_001,5.2\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert result.is_valid
    assert result.report.eto_present == 0
    assert result.report.ndvi_present == 0
    assert result.report.measured_present == 0


def test_missing_required_column_fails_with_name(tmp_path):
    content = (
        "date,site_id,eto_mm,ndvi,measured_et_mm\n"
        "2024-06-01,field_001,5.8,0.71,\n"
    )
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any("openet_et_mm" in error for error in result.errors)


def test_non_numeric_openet_fails_with_row_context(tmp_path):
    content = HEADER + "2024-06-01,field_001,abc,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any(
        "row 2" in error and "openet_et_mm" in error for error in result.errors
    )


def test_non_numeric_optional_columns_fail(tmp_path):
    content = HEADER + "2024-06-01,field_001,5.2,xx,yy,zz\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any("eto_mm" in error for error in result.errors)
    assert any("ndvi" in error for error in result.errors)
    assert any("measured_et_mm" in error for error in result.errors)


def test_negative_et_fails(tmp_path):
    content = HEADER + "2024-06-01,field_001,-1.0,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any(
        "row 2" in error and "openet_et_mm" in error and ">= 0" in error
        for error in result.errors
    )


def test_negative_measured_et_is_allowed_for_ebc_tower_labels(tmp_path):
    content = HEADER + "2024-06-01,field_001,5.2,5.8,0.71,-0.08\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert result.is_valid
    assert result.report.measured_present == 1


def test_negative_nodata_sentinel_fails(tmp_path):
    content = HEADER + "2024-06-01,field_001,-9999,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any(">= 0" in error for error in result.errors)


def test_ndvi_out_of_range_fails(tmp_path):
    content = HEADER + "2024-06-01,field_001,5.2,5.8,1.5,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any(
        "row 2" in error and "ndvi" in error and "[-1, 1]" in error
        for error in result.errors
    )


def test_positive_et_sentinel_not_yet_caught(tmp_path):
    content = HEADER + "2024-06-01,field_001,9999,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert result.is_valid


def test_density_reported_for_gappy_site(tmp_path):
    content = (
        HEADER
        + "2024-06-01,field_001,5.2,5.8,0.71,\n"
        + "2024-06-10,field_001,5.5,6.1,0.73,\n"
    )
    result = validate_csv(write_csv(tmp_path, content))
    assert result.is_valid
    site = result.report.sites[0]
    assert site.span_days == 10
    assert site.row_count == 2


def test_non_finite_numeric_fails(tmp_path):
    content = HEADER + "2024-06-01,field_001,nan,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any(
        "row 2" in error
        and "non-finite" in error
        and "openet_et_mm" in error
        for error in result.errors
    )


def test_inf_numeric_fails(tmp_path):
    content = HEADER + "2024-06-01,field_001,inf,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any("non-finite" in error for error in result.errors)


def test_utf8_bom_header_is_handled(tmp_path):
    content = "\ufeff" + HEADER + "2024-06-01,field_001,5.2,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert result.is_valid
    assert result.report.row_count == 1


def test_empty_file_fails(tmp_path):
    result = validate_csv(write_csv(tmp_path, ""))
    assert not result.is_valid
    assert any("empty" in error for error in result.errors)


def test_header_only_fails(tmp_path):
    result = validate_csv(write_csv(tmp_path, HEADER))
    assert not result.is_valid
    assert any("no usable time-series rows" in error for error in result.errors)


def test_duplicate_site_date_fails(tmp_path):
    content = (
        HEADER
        + "2024-06-01,field_001,5.2,5.8,0.71,\n"
        + "2024-06-01,field_001,5.3,5.9,0.72,\n"
    )
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any(
        "duplicate" in error and "row 3" in error for error in result.errors
    )


def test_invalid_date_format_fails_with_row_context(tmp_path):
    content = HEADER + "06/01/2024,field_001,5.2,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any(
        "row 2" in error and "invalid date" in error for error in result.errors
    )


def test_report_stats_and_date_range(tmp_path):
    content = (
        HEADER
        + "2024-06-02,field_001,5.2,5.8,0.71,\n"
        + "2024-06-01,field_001,5.5,,0.73,\n"
        + "2024-06-01,field_002,4.9,5.0,,\n"
    )
    result = validate_csv(write_csv(tmp_path, content))
    assert result.is_valid
    report = result.report
    assert report.row_count == 3
    assert report.site_count == 2
    assert report.openet_present == 3
    assert report.eto_present == 2
    assert report.ndvi_present == 2
    assert report.measured_present == 0
    by_id = {site.site_id: site for site in report.sites}
    assert by_id["field_001"].first_date == "2024-06-01"
    assert by_id["field_001"].last_date == "2024-06-02"
    assert by_id["field_001"].row_count == 2
    assert by_id["field_002"].row_count == 1


def test_shipped_template_validates_and_has_no_measured_labels():
    repo_root = Path(__file__).resolve().parents[1]
    result = validate_csv(str(repo_root / "examples" / "et_timeseries_template.csv"))
    assert result.is_valid
    assert result.report.has_measured_labels is False
