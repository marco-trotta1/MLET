"""Column contract for MLET ET time-series CSV files."""

DATE_COLUMN = "date"
SITE_COLUMN = "site_id"
OPENET_COLUMN = "openet_et_mm"
ETO_COLUMN = "eto_mm"
NDVI_COLUMN = "ndvi"
MEASURED_COLUMN = "measured_et_mm"

# Columns that must be present in the header.
REQUIRED_COLUMNS = (DATE_COLUMN, SITE_COLUMN, OPENET_COLUMN)

# Columns whose non-blank values must parse as floats.
NUMERIC_COLUMNS = (OPENET_COLUMN, ETO_COLUMN, NDVI_COLUMN, MEASURED_COLUMN)

# ET columns (mm) are physically non-negative.
NONNEGATIVE_COLUMNS = (OPENET_COLUMN, ETO_COLUMN, MEASURED_COLUMN)

# NDVI is a normalized ratio, mathematically bounded to [-1, 1].
NDVI_MIN = -1.0
NDVI_MAX = 1.0

# Full ordered contract, used for the example template.
ALL_COLUMNS = (
    DATE_COLUMN,
    SITE_COLUMN,
    OPENET_COLUMN,
    ETO_COLUMN,
    NDVI_COLUMN,
    MEASURED_COLUMN,
)

# Strict ISO date format (YYYY-MM-DD).
DATE_FORMAT = "%Y-%m-%d"
