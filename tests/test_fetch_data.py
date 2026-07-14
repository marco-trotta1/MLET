import hashlib
import importlib.util
import io
import pathlib
import urllib.error
import zipfile


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


def test_download_uses_certified_urlopen_and_writes_destination(tmp_path, monkeypatch):
    destination = tmp_path / "download.bin"

    def no_urlretrieve(*args, **kwargs):
        raise AssertionError("urlretrieve does not receive the explicit certificate context")

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr(fetch_data.urllib.request, "urlretrieve", no_urlretrieve)
    monkeypatch.setattr(fetch_data.urllib.request, "urlopen", lambda url, context: Response(b"public data"))
    fetch_data._download("https://example.test/data", str(destination))
    assert destination.read_bytes() == b"public data"


def test_ensure_retries_checksum_mismatch(tmp_path, monkeypatch):
    destination = tmp_path / "archive.zip"
    expected = hashlib.md5(b"complete").hexdigest()
    attempts = 0

    def partial_then_complete(url, path):
        nonlocal attempts
        attempts += 1
        pathlib.Path(path).write_bytes(b"partial" if attempts == 1 else b"complete")

    monkeypatch.setattr(fetch_data, "_download", partial_then_complete)
    assert fetch_data._ensure("https://example.test/archive", str(destination), expected, False) is True
    assert attempts == 2


def test_download_resumes_partial_file_with_http_range(tmp_path, monkeypatch):
    destination = tmp_path / "archive.zip"
    partial = tmp_path / "archive.zip.part"
    partial.write_bytes(b"prefix")

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    def open_resumed(request, context):
        assert request.get_header("Range") == "bytes=6-"
        return Response(b"suffix")

    monkeypatch.setattr(fetch_data.urllib.request, "urlopen", open_resumed)
    fetch_data._download("https://example.test/archive", str(destination))
    assert destination.read_bytes() == b"prefixsuffix"


def test_download_restarts_when_server_ignores_http_range(tmp_path, monkeypatch):
    destination = tmp_path / "archive.zip"
    (tmp_path / "archive.zip.part").write_bytes(b"prefix")

    class Response(io.BytesIO):
        def getcode(self):
            return 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr(fetch_data.urllib.request, "urlopen", lambda request, context: Response(b"complete"))
    fetch_data._download("https://example.test/archive", str(destination))
    assert destination.read_bytes() == b"complete"


def test_download_restarts_after_range_not_satisfiable(tmp_path, monkeypatch):
    destination = tmp_path / "archive.zip"
    (tmp_path / "archive.zip.part").write_bytes(b"stale")
    calls = 0

    class Response(io.BytesIO):
        def getcode(self):
            return 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    def open_after_reset(request, context):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.HTTPError(request.full_url, 416, "range", {}, None)
        return Response(b"complete")

    monkeypatch.setattr(fetch_data.urllib.request, "urlopen", open_after_reset)
    fetch_data._download("https://example.test/archive", str(destination))
    assert calls == 2
    assert destination.read_bytes() == b"complete"


def test_extract_zip_unpacks_verified_archive_into_destination(tmp_path):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("dataset/daily_data.dat", "daily values")
    destination = tmp_path / "raw"
    fetch_data.extract_zip(str(archive), str(destination))
    assert (destination / "dataset" / "daily_data.dat").read_text() == "daily values"
