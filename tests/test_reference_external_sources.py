"""Non-scientific structural checks for the external reference-source registry."""

import json
from pathlib import Path

import pytest

REGISTRY = Path("data/reference/external_sources.json")
REQUIRED_KEYS = {"citation", "doi", "license", "intended_use", "not_ingested_because"}
EXPECTED_SOURCES = {"caravan", "caravan_multimet", "neuralhydrology"}


@pytest.fixture(scope="module")
def registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_registry_matches_the_existing_source_registry_shape(registry: dict) -> None:
    outlook = json.loads(Path("data/outlook/source_registry.json").read_text(encoding="utf-8"))
    assert registry["schema_version"] == outlook["schema_version"]
    assert isinstance(registry["sources"], dict)
    assert registry["sources"]


def test_registry_has_the_planned_sources_and_pins_neuralhydrology(registry: dict) -> None:
    """Keep the documentation registry tied to the plan's reviewed sources."""
    assert set(registry["sources"]) == EXPECTED_SOURCES

    neuralhydrology = registry["sources"]["neuralhydrology"]
    assert neuralhydrology["version_reviewed"] == "1.13.0"
    assert neuralhydrology["commit_reviewed"] == (
        "d6d7aa5cc6d9e42308009139ccccf37be006445f"
    )


def test_every_source_declares_provenance_and_intent(registry: dict) -> None:
    for name, source in registry["sources"].items():
        missing = REQUIRED_KEYS - set(source)
        assert not missing, f"{name} is missing {sorted(missing)}"
        assert source["license"], f"{name} has an empty license"


def test_caravan_records_the_era5_land_pet_defect(registry: dict) -> None:
    """A known-bad variable a future contributor might otherwise reach for."""
    caravan = registry["sources"]["caravan"]
    defects = caravan["known_defects"]
    assert any("potential_evaporation" in entry["variable"] for entry in defects)
    entry = next(e for e in defects if "potential_evaporation" in e["variable"])
    assert entry["do_not_use"] is True
    assert entry["use_instead"] == "potential_evaporation_sum_FAO_PENMAN_MONTEITH"


def test_multimet_is_registered_as_the_forecast_pairing_convention(registry: dict) -> None:
    multimet = registry["sources"]["caravan_multimet"]
    assert "issue time" in multimet["intended_use"]
    assert multimet["doi"].startswith("10.") or "arxiv" in multimet["doi"].lower()


def test_no_source_claims_to_be_ingested(registry: dict) -> None:
    """This registry is documentation; ingestion would need its own adapter."""
    for name, source in registry["sources"].items():
        assert source["not_ingested_because"], f"{name} must state why it is not ingested"
