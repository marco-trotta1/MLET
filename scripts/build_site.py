"""Assemble the static GitHub Pages site from committed repository sources.

The outlook viewer is not hand-copied HTML: this script runs the real
``build_outlook`` → ``publish_outlook`` pipeline on the repository's example
fixtures, so the deployed map is byte-for-byte the artifact the CLI produces,
including its permanent research-candidate and fixture labeling. The landing
page reads ``manifest.json`` written here for run provenance and artifact
checksums.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# The deployed site must always reflect this checkout's source, not whatever
# mlet version happens to be installed in the interpreter.
sys.path.insert(0, str(REPO_ROOT / "src"))
SITE_SOURCE = REPO_ROOT / "site"
WEATHER_FIXTURE = REPO_ROOT / "examples/outlook/weather_members.jsonl"
STATE_FIXTURE = REPO_ROOT / "examples/outlook/state.jsonl"
CROP_FIXTURE = REPO_ROOT / "examples/outlook/crop_grid.jsonl"
CANDIDATE_FILES = ("index.html", "outlook.geojson", "summary.json", "serve-contract.json")


def build_site(destination: Path) -> Path:
    """Write the complete site to ``destination`` and return that path."""
    from mlet.outlook.build import build_outlook
    from mlet.outlook.publish import publish_outlook

    destination = destination.resolve()
    if destination == REPO_ROOT or destination in REPO_ROOT.parents:
        raise ValueError("site destination must be a dedicated output directory")
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(SITE_SOURCE, destination)
    (destination / ".nojekyll").write_bytes(b"")

    with tempfile.TemporaryDirectory() as scratch:
        scratch_root = Path(scratch).resolve()
        run = build_outlook(
            weather_path=WEATHER_FIXTURE,
            state_path=STATE_FIXTURE,
            crop_path=CROP_FIXTURE,
            out_dir=scratch_root,
        )
        published = publish_outlook(
            scratch_root / run.run_id, out_dir=scratch_root / "map"
        )
        outlook_dir = destination / "outlook"
        outlook_dir.mkdir()
        files = []
        for name in CANDIDATE_FILES:
            contents = (published.output_dir / name).read_bytes()
            (outlook_dir / name).write_bytes(contents)
            files.append(
                {
                    "name": name,
                    "bytes": len(contents),
                    "sha256": hashlib.sha256(contents).hexdigest(),
                }
            )
        contract = json.loads(
            (published.output_dir / "serve-contract.json").read_text(encoding="utf-8")
        )
    manifest = {
        "schema_version": 1,
        "run_id": contract["run_id"],
        "issued_at": contract["issued_at"],
        "fixture_non_scientific": contract["fixture_non_scientific"],
        "production_status": contract["production_status"],
        "promotion": contract["promotion"],
        "validation_status": contract["validation_status"],
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": files,
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build_site")
    parser.add_argument("--out", default="_site", help="Site output directory.")
    args = parser.parse_args(argv)
    try:
        destination = build_site(Path(args.out))
    except (OSError, ValueError) as exc:
        print(f"error: cannot build site: {exc}", file=sys.stderr)
        return 2
    print(f"site: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
