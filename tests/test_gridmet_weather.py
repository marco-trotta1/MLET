import pytest

from mlet.sources.gridmet_weather import decode_gridmet_value


@pytest.mark.parametrize(
    ("variable", "encoded", "expected"),
    [
        ("vs", 47, 4.7),
        ("tmmn", 615, 271.5),
        ("tmmx", 683, 288.3),
        ("vpd", 25, 0.25),
    ],
)
def test_decode_gridmet_packed_values(variable, encoded, expected):
    assert decode_gridmet_value(variable, encoded) == pytest.approx(expected)


def test_decode_gridmet_rejects_unknown_variable():
    with pytest.raises(ValueError, match="unsupported gridMET variable"):
        decode_gridmet_value("tavg", 275)
