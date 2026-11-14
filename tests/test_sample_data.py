"""Tests for the sample data generator and the data files bundled in the package."""

import subprocess
import sys
from importlib.resources import files
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = PROJECT_ROOT / "scripts" / "make_sample_data.py"
SAMPLE_FILES = ["rosters.csv", "sessions.csv"]
UTF8_BYTE_ORDER_MARK = b"\xef\xbb\xbf"


def run_generator(out_dir: Path) -> None:
    """Run the sample data generator, writing its files to ``out_dir``."""
    subprocess.run(
        [sys.executable, str(GENERATOR), "--out", str(out_dir)],
        check=True,
        capture_output=True,
    )


def bundled_sample(name: str) -> bytes:
    """Read a sample file from the installed package data."""
    return files("roster_check").joinpath("data", "sample", name).read_bytes()


@pytest.mark.parametrize("name", SAMPLE_FILES)
def test_generator_output_is_deterministic(tmp_path: Path, name: str) -> None:
    run_generator(tmp_path / "first")
    run_generator(tmp_path / "second")

    first = (tmp_path / "first" / name).read_bytes()
    second = (tmp_path / "second" / name).read_bytes()
    assert first == second


@pytest.mark.parametrize("name", SAMPLE_FILES)
def test_bundled_sample_matches_generator_output(tmp_path: Path, name: str) -> None:
    run_generator(tmp_path)

    assert bundled_sample(name) == (tmp_path / name).read_bytes()


@pytest.mark.parametrize(
    "path",
    [
        ("centres.csv",),
        ("staffing_rules.csv",),
        ("sample", "rosters.csv"),
        ("sample", "sessions.csv"),
    ],
)
def test_data_files_are_bundled_in_the_package(path: tuple[str, ...]) -> None:
    assert files("roster_check").joinpath("data", *path).is_file()


def test_rosters_sample_is_written_as_an_excel_export() -> None:
    content = bundled_sample("rosters.csv")

    assert content.startswith(UTF8_BYTE_ORDER_MARK)
    assert content.count(b"\n") == content.count(b"\r\n")


def test_sessions_sample_is_plain_utf8() -> None:
    content = bundled_sample("sessions.csv")

    assert not content.startswith(UTF8_BYTE_ORDER_MARK)
    assert b"\r" not in content


@pytest.mark.parametrize(
    ("name", "planted_values"),
    [
        ("rosters.csv", [b",XYZ,", b",cleaner,", b",25:00,", b"/11/26,"]),
        ("sessions.csv", [b",next tues,", b",twelve", b",-3", b",aqua_zumba,"]),
    ],
)
def test_sample_contains_planted_bad_rows(
    name: str,
    planted_values: list[bytes],
) -> None:
    content = bundled_sample(name)

    for value in planted_values:
        assert value in content


@pytest.mark.parametrize("name", SAMPLE_FILES)
def test_sample_contains_one_blank_line(name: str) -> None:
    lines = bundled_sample(name).decode("utf-8-sig").splitlines()

    assert lines.count("") == 1
