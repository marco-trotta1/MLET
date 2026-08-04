import hashlib
import json
from pathlib import Path


def test_outlook_source_registry_has_required_provenance_fields() -> None:
    registry = json.loads(Path("data/outlook/source_registry.json").read_text())
    for name in ("gefs", "openet_eta", "usda_cdl"):
        source = registry["sources"][name]
        assert {"citation", "license", "latency", "required_variables"} <= source.keys()


def test_outlook_source_registry_tracks_historical_eto_contracts() -> None:
    registry = json.loads(Path("data/outlook/source_registry.json").read_text())
    sources = registry["sources"]

    assert sources["gefs"]["artifact_schema"] == (
        "mlet.gefs.daily-artifact v2; docs/data/GEFS_DAILY_ARTIFACT.md"
    )

    agrimet = sources["usbr_agrimet_etos"]
    assert agrimet["artifact_schema"] == (
        "mlet.agrimet.etos-artifact v2; docs/data/AGRIMET_ETO_ARTIFACT.md"
    )
    assert agrimet["station_history_schema"] == (
        "mlet.agrimet.station-history-registry v1; docs/data/AGRIMET_ETO_ARTIFACT.md"
    )
    snapshot = Path(agrimet["station_registry_snapshot"])
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == agrimet[
        "station_registry_snapshot_sha256"
    ]
