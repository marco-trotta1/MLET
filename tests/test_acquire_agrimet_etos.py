"""Tests for the checksum-bound AgriMet ETos acquisition script."""

from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path


_SPEC = importlib.util.spec_from_file_location(
    "acquire_agrimet_etos",
    Path(__file__).parents[1] / "scripts" / "acquire_agrimet_etos.py",
)
assert _SPEC is not None
assert _SPEC.loader is not None
acquire_agrimet_etos = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(acquire_agrimet_etos)


def test_download_passes_an_explicit_certificate_context(monkeypatch) -> None:
    """The public USBR archive needs the bundled certificate roots."""
    captured = {}

    class Response(BytesIO):
        headers = {"ETag": "etag", "Last-Modified": "date"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    def open_with_context(request, *, timeout, context):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["context"] = context
        return Response(b"BEGIN DATA\nDATE,BOII ETOS\n07/03/2019,0.20\nEND DATA\n")

    monkeypatch.setattr(acquire_agrimet_etos, "urlopen", open_with_context)

    body, headers = acquire_agrimet_etos._download("https://example.test/archive")

    assert body.startswith(b"BEGIN DATA")
    assert headers == {"ETag": "etag", "Last-Modified": "date"}
    assert captured["timeout"] == 60
    assert captured["context"] is acquire_agrimet_etos._TLS_CONTEXT
