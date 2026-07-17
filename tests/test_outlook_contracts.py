import json
from pathlib import Path


def test_outlook_source_registry_has_required_provenance_fields() -> None:
    registry = json.loads(Path("data/outlook/source_registry.json").read_text())
    for name in ("gefs", "openet_eta", "usda_cdl"):
        source = registry["sources"][name]
        assert {"citation", "license", "latency", "required_variables"} <= source.keys()
