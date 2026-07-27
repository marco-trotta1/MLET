"""Non-scientific structural checks that the hybrid tier stays non-serving."""

import ast
from pathlib import Path

import pytest

SERVING_ROOTS = (
    Path("src/mlet/outlook"),
    Path("src/mlet/sources"),
    Path("src/mlet/experiments"),
)
SERVING_FILES = (Path("src/mlet/cli.py"),)
FORBIDDEN_ROOTS = {"torch", "mlet.hybrid"}


def _serving_modules():
    paths = list(SERVING_FILES)
    for root in SERVING_ROOTS:
        paths.extend(sorted(root.rglob("*.py")))
    assert paths, "no serving modules found; check the paths in this test"
    return paths


def _imported_names(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


@pytest.mark.parametrize("path", _serving_modules(), ids=str)
def test_serving_module_does_not_import_the_hybrid_tier(path: Path) -> None:
    """A path from the audited outlook to torch would break the tier contract."""
    for name in _imported_names(path):
        for forbidden in FORBIDDEN_ROOTS:
            assert not (
                name == forbidden or name.startswith(forbidden + ".")
            ), f"{path} imports {name}, which is forbidden on the serving path"


def test_core_dependencies_do_not_include_torch() -> None:
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    core_block = text.split("[project.optional-dependencies]")[0]
    assert "torch" not in core_block


def test_the_hybrid_scaffold_imports_without_torch() -> None:
    """Tier 2 must stay usable on a plain install."""
    import importlib

    for module in ("mlet.hybrid.bounded", "mlet.hybrid.fao56_dual"):
        assert importlib.import_module(module) is not None
