import hashlib
import importlib.util
import pathlib


_SPEC = importlib.util.spec_from_file_location(
    "fetch_data", pathlib.Path(__file__).parents[1] / "scripts" / "fetch_data.py"
)
assert _SPEC is not None
assert _SPEC.loader is not None
fetch_data = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fetch_data)


def test_verify_file_matches_md5(tmp_path):
    path = tmp_path / "x.bin"
    path.write_bytes(b"hello")
    md5 = hashlib.md5(b"hello").hexdigest()
    assert fetch_data.verify_file(str(path), md5) is True
    assert fetch_data.verify_file(str(path), "0" * 32) is False


def test_manifest_loads_and_has_three_sources():
    root = pathlib.Path(__file__).parents[1]
    manifest = fetch_data.load_manifest(str(root / "data" / "manifest.json"))
    assert set(manifest["sources"]) == {
        "openet_model_et",
        "flux_benchmark",
        "gridmet_pet",
    }
