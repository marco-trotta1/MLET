#!/usr/bin/env python3
"""Verify that the committed real ETo candidate builds without fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from mlet.outlook.eto_site import build_eto_site


REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    source_files = {
        "outlook.json": REPO_ROOT / "data/outlook/gefs_reforecast_20190703_outlook.json",
        "manifest.json": REPO_ROOT / "data/outlook/gefs_reforecast_20190703_manifest.json",
    }
    with tempfile.TemporaryDirectory(prefix="mlet-real-eto-site-") as temporary:
        root = Path(temporary)
        source = root / "source"
        destination = root / "site"
        source.mkdir()
        for name, path in source_files.items():
            shutil.copyfile(path, source / name)
        result = build_eto_site(source, destination)
        viewer = json.loads((destination / "outlook/viewer-data.json").read_text())
        if len(viewer["days"]) != 20 or viewer["grid_count"] != 195:
            raise SystemExit("real ETo site coverage changed")
        if viewer["run"]["production_status"] != "research_candidate":
            raise SystemExit("real ETo site status changed")
        if result.candidate_sha256 != hashlib.sha256(
            source_files["outlook.json"].read_bytes()
        ).hexdigest():
            raise SystemExit("real ETo site candidate checksum changed")
    print("real ETo candidate site verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
