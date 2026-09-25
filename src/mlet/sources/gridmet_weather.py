"""Decode packed weather values from gridMET point subsets."""
from __future__ import annotations

_PACKING: dict[str, tuple[float, float]] = {
    "vs": (0.1, 0.0),
    "tmmn": (0.1, 210.0),
    "tmmx": (0.1, 220.0),
    "vpd": (0.01, 0.0),
}


def decode_gridmet_value(variable: str, encoded: float) -> float:
    """Decode a packed gridMET value into its documented native unit."""
    try:
        scale, offset = _PACKING[variable]
    except KeyError as exc:
        raise ValueError(f"unsupported gridMET variable: {variable}") from exc
    return float(encoded) * scale + offset
