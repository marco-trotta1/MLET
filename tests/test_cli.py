import subprocess
import sys
from pathlib import Path

import pytest

from mlet.cli import main

HEADER = "date,site_id,openet_et_mm,eto_mm,ndvi,measured_et_mm\n"


def write_csv(tmp_path: Path, content: str) -> str:
    path = tmp_path / "data.csv"
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_validate_valid_file_returns_0(tmp_path, capsys):
    code = main(
        [
            "validate-csv",
            write_csv(tmp_path, HEADER + "2024-06-01,field_001,5.2,5.8,0.71,\n"),
        ]
    )
    assert code == 0
    assert "has_measured_labels: false" in capsys.readouterr().out


def test_validate_invalid_file_returns_1(tmp_path, capsys):
    code = main(
        [
            "validate-csv",
            write_csv(tmp_path, HEADER + "2024-06-01,field_001,abc,5.8,0.71,\n"),
        ]
    )
    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_missing_argument_exits_2():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_file_not_found_returns_2(tmp_path, capsys):
    code = main(["validate-csv", str(tmp_path / "missing.csv")])
    assert code == 2
    assert "cannot read" in capsys.readouterr().err


def test_error_display_is_capped(tmp_path, capsys):
    bad_rows = "bad-date,field_001,5.2,5.8,0.71,\n" * 25
    code = main(["validate-csv", write_csv(tmp_path, HEADER + bad_rows)])
    assert code == 1
    err = capsys.readouterr().err
    assert "... and 5 more" in err


def test_module_entrypoint_matches_main(tmp_path):
    path = write_csv(tmp_path, HEADER + "2024-06-01,field_001,5.2,5.8,0.71,\n")
    proc = subprocess.run(
        [sys.executable, "-m", "mlet", "validate-csv", path],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "has_measured_labels: false" in proc.stdout
