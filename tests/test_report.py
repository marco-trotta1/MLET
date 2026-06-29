from mlet.report import SiteSummary, ValidationReport, ValidationResult


def make_report():
    return ValidationReport(
        row_count=2,
        site_count=1,
        sites=[SiteSummary("field_001", 2, "2024-06-01", "2024-06-02", span_days=2)],
        openet_present=2,
        eto_present=2,
        ndvi_present=2,
        measured_present=0,
        has_measured_labels=False,
    )


def test_report_to_text_contains_key_lines():
    text = make_report().to_text()
    assert "rows: 2" in text
    assert "sites: 1" in text
    assert (
        "field_001: 2024-06-01 -> 2024-06-02 "
        "(2-day span, 2 rows, 100% dense)"
    ) in text
    assert "OpenET completeness: 2/2 (100.0%)" in text
    assert "ETo availability: 2/2 (100.0%)" in text
    assert "measured ET availability: 0/2 (0.0%)" in text
    assert "has_measured_labels: false" in text


def test_ratio_handles_zero_rows():
    report = ValidationReport(
        row_count=0,
        site_count=0,
        sites=[],
        openet_present=0,
        eto_present=0,
        ndvi_present=0,
        measured_present=0,
        has_measured_labels=False,
    )
    assert "OpenET completeness: 0/0 (0.0%)" in report.to_text()


def test_result_defaults():
    result = ValidationResult(is_valid=True)
    assert result.errors == []
    assert result.report is None
