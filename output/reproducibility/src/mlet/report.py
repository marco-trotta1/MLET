"""Result and report types for ET CSV validation, plus text rendering."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SiteSummary:
    site_id: str
    row_count: int
    first_date: str
    last_date: str
    span_days: int


@dataclass
class ValidationReport:
    row_count: int
    site_count: int
    sites: list[SiteSummary]
    openet_present: int
    eto_present: int
    ndvi_present: int
    measured_present: int
    has_measured_labels: bool

    def to_text(self) -> str:
        lines = [
            f"rows: {self.row_count}",
            f"sites: {self.site_count}",
        ]
        for site in self.sites:
            density = (site.row_count / site.span_days * 100) if site.span_days else 0.0
            lines.append(
                f"  {site.site_id}: {site.first_date} -> {site.last_date} "
                f"({site.span_days}-day span, {site.row_count} rows, "
                f"{density:.0f}% dense)"
            )
        lines.append(f"OpenET completeness: {_ratio(self.openet_present, self.row_count)}")
        lines.append(f"ETo availability: {_ratio(self.eto_present, self.row_count)}")
        lines.append(f"NDVI availability: {_ratio(self.ndvi_present, self.row_count)}")
        lines.append(
            f"measured ET availability: {_ratio(self.measured_present, self.row_count)}"
        )
        lines.append(f"has_measured_labels: {str(self.has_measured_labels).lower()}")
        return "\n".join(lines)


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    report: ValidationReport | None = None


def _ratio(present: int, total: int) -> str:
    pct = (present / total * 100) if total else 0.0
    return f"{present}/{total} ({pct:.1f}%)"
