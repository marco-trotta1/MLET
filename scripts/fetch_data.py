"""Reproducibly download and checksum-verify MLET Phase 2 sources."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import ssl
import sys
import urllib.request

import certifi

RAW = os.path.join("data", "raw")
GRIDMET = os.path.join(RAW, "gridmet")
DOWNLOAD_ATTEMPTS = 3


def load_manifest(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def verify_file(path: str, expected_md5: str) -> bool:
    if not os.path.exists(path):
        return False
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected_md5


def _download(url: str, destination: str) -> None:
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    temporary = f"{destination}.part"
    offset = os.path.getsize(temporary) if os.path.exists(temporary) else 0
    mode = "ab" if offset else "wb"
    request = urllib.request.Request(url)
    if offset:
        request.add_header("Range", f"bytes={offset}-")
    action = "resuming" if offset else "downloading"
    print(f"{action} {url} -> {destination}", flush=True)
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, context=context) as response:  # noqa: S310
        response_code = response.getcode() if hasattr(response, "getcode") else 206
        if offset and response_code != 206:
            mode = "wb"
        with open(temporary, mode) as handle:
            shutil.copyfileobj(response, handle)
    os.replace(temporary, destination)


def _ensure(url: str, destination: str, expected_md5: str, check_only: bool) -> bool:
    if not verify_file(destination, expected_md5):
        if check_only:
            print(f"MISSING/BAD: {destination}")
            return False
        for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
            _download(url, destination)
            if verify_file(destination, expected_md5):
                break
            print(f"checksum mismatch after attempt {attempt}/{DOWNLOAD_ATTEMPTS}: {destination}", flush=True)
    verified = verify_file(destination, expected_md5)
    print(f"OK {destination}" if verified else f"BAD {destination}", flush=True)
    return verified


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fetch_data")
    parser.add_argument("--manifest", default=os.path.join("data", "manifest.json"))
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)
    manifest = load_manifest(args.manifest)
    sources = manifest["sources"]

    verified = True
    for key in ("openet_model_et", "flux_benchmark"):
        source = sources[key]
        verified = _ensure(
            source["url"], os.path.join(RAW, source["filename"]), source["md5"], args.check_only
        ) and verified
    gridmet = sources["gridmet_pet"]
    for filename, md5 in gridmet["files"].items():
        verified = _ensure(
            gridmet["base_url"] + filename,
            os.path.join(GRIDMET, filename),
            md5,
            args.check_only,
        ) and verified
    print("ALL OK" if verified else "VERIFICATION FAILED")
    return 0 if verified else 1


if __name__ == "__main__":
    sys.exit(main())
