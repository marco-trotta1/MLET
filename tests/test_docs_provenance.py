"""Non-scientific structural checks that provenance documentation stays complete."""

from pathlib import Path

import pytest

PROVENANCE = Path("docs/methods/NEURALHYDROLOGY_PROVENANCE.md")
UPSTREAM_COMMIT = "d6d7aa5cc6d9e42308009139ccccf37be006445f"

#: Every MLET module derived from neuralhydrology, and the upstream file it came
#: from. Adding a derived module without adding it here fails this test.
DERIVED_MODULES = {
    "src/mlet/reference/fao56_radiation.py": "datautils/pet.py",
    "src/mlet/reference/priestley_taylor.py": "datautils/pet.py",
    "src/mlet/outlook/namespaces.py": "utils/config.py",
    "src/mlet/outlook/overlap.py": "modelzoo/handoff_forecast_lstm.py",
    "src/mlet/outlook/scaler_artifact.py": "datasetzoo/basedataset.py",
    "src/mlet/hybrid/bounded.py": "modelzoo/baseconceptualmodel.py",
    "src/mlet/hybrid/fao56_dual.py": "modelzoo/shm.py",
    "src/mlet/hybrid/torch_adapter.py": "modelzoo/hybridmodel.py",
    "src/mlet/hybrid/nh_export.py": "datasetzoo/genericdataset.py",
}


@pytest.fixture(scope="module")
def text() -> str:
    return PROVENANCE.read_text(encoding="utf-8")


def test_upstream_version_and_commit_are_recorded(text: str) -> None:
    assert UPSTREAM_COMMIT in text
    assert "1.13.0" in text
    assert "BSD-3-Clause" in text


@pytest.mark.parametrize("module,upstream", sorted(DERIVED_MODULES.items()))
def test_every_derived_module_is_documented(module: str, upstream: str, text: str) -> None:
    assert Path(module).is_file(), f"{module} is listed as derived but does not exist"
    row = f"| `{module}` | `{upstream}` |"
    assert row in text, f"provenance table row is missing or mismatched: {row}"


def test_both_upstream_defects_are_recorded(text: str) -> None:
    """These are findings; losing them would be losing a manuscript contribution."""
    assert "Eq. 37" in text or "clear_sky" in text
    assert "0.408" in text
    assert "2.451" in text
    assert "19.4" in text


def test_licence_notice_is_retained_with_the_ported_code() -> None:
    """BSD-3-Clause requires the notice travel with the source."""
    notice = Path("src/mlet/reference/UPSTREAM.md").read_text(encoding="utf-8")
    assert "BSD 3-Clause" in notice
    assert "Copyright (c) 2021, NeuralHydrology" in notice
    assert "THIS SOFTWARE IS PROVIDED" in notice
