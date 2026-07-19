"""Software contracts for the static GitHub Pages site assembler."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build_site


def test_build_site_assembles_landing_viewer_and_checksummed_manifest(
    tmp_path: Path,
) -> None:
    destination = build_site.build_site(tmp_path / "_site")

    assert (destination / "index.html").is_file()
    assert (destination / ".nojekyll").is_file()
    for name in build_site.CANDIDATE_FILES:
        assert (destination / "outlook" / name).is_file()

    manifest = json.loads((destination / "manifest.json").read_text())
    assert manifest["promotion"] is False
    assert manifest["validation_status"] == "validation_pending"
    assert manifest["production_status"] == "research_candidate"
    assert manifest["fixture_non_scientific"] is True
    assert {entry["name"] for entry in manifest["files"]} == set(
        build_site.CANDIDATE_FILES
    )
    for entry in manifest["files"]:
        contents = (destination / "outlook" / entry["name"]).read_bytes()
        assert entry["bytes"] == len(contents)
        assert entry["sha256"] == hashlib.sha256(contents).hexdigest()

    viewer = (destination / "outlook" / "index.html").read_text(encoding="utf-8")
    assert "NON-SCIENTIFIC SOFTWARE FIXTURE" in viewer


def test_build_site_cli_reports_destination(tmp_path: Path, capsys) -> None:
    assert build_site.main(["--out", str(tmp_path / "_site")]) == 0
    assert "site: " in capsys.readouterr().out


def test_build_site_refuses_the_repository_root(tmp_path: Path) -> None:
    assert build_site.main(["--out", str(build_site.REPO_ROOT)]) == 2
