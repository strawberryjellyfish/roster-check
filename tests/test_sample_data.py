"""Tests for the sample data generator and the data files bundled in the package."""

import csv
import io
import subprocess
import sys
from collections import Counter
from datetime import datetime
from importlib.resources import files
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = PROJECT_ROOT / "scripts" / "make_sample_data.py"
SAMPLE_FILES = ["rosters.csv", "sessions.csv"]
UTF8_BYTE_ORDER_MARK = b"\xef\xbb\xbf"
EXPECTED_COLUMNS = 8
KNOWN_CENTRES = {"RBC", "NTH", "HLS", "LKV"}
KNOWN_ROLES = {
    "lifeguard",
    "swim_instructor",
    "gym_supervisor",
    "group_fitness",
    "front_desk",
}
KNOWN_ACTIVITIES = {"swim_lesson", "lap_swim", "gym_floor", "group_fitness"}


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


def sample_records(name: str) -> list[dict[str, str]]:
    """Parse a bundled sample file into one dictionary per full-width data row.

    Blank lines and rows with the wrong number of columns are left out, so each
    record has a value for every column.
    """
    text = bundled_sample(name).decode("utf-8-sig")
    header, *rows = csv.reader(io.StringIO(text))
    return [
        dict(zip(header, row, strict=True)) for row in rows if len(row) == len(header)
    ]


def sample_row_widths(name: str) -> list[int]:
    """Return the number of fields in each non-blank data row of a sample file."""
    text = bundled_sample(name).decode("utf-8-sig")
    _, *rows = csv.reader(io.StringIO(text))
    return [len(row) for row in rows if row]


def is_real_date(text: str) -> bool:
    """Return whether ``text`` is a ``DD/MM/YYYY`` date that exists."""
    try:
        datetime.strptime(text, "%d/%m/%Y")
    except ValueError:
        return False
    return True


def is_time(text: str) -> bool:
    """Return whether ``text`` is a valid ``HH:MM`` time."""
    try:
        datetime.strptime(text, "%H:%M")
    except ValueError:
        return False
    return True


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


@pytest.mark.parametrize(
    ("name", "column"),
    [("rosters.csv", "staff_id"), ("sessions.csv", "activity")],
)
def test_sample_has_a_blank_required_field(name: str, column: str) -> None:
    assert any(record[column] == "" for record in sample_records(name))


def test_rosters_sample_has_an_impossible_date() -> None:
    dates = [record["shift_date"] for record in sample_records("rosters.csv")]

    impossible = [
        text
        for text in dates
        if len(text.split("/")) == 3 and len(text) == 10 and not is_real_date(text)
    ]
    assert impossible


@pytest.mark.parametrize("name", SAMPLE_FILES)
def test_sample_has_a_row_that_ends_before_it_starts(name: str) -> None:
    reversed_rows = [
        record
        for record in sample_records(name)
        if is_time(record["start_time"])
        and is_time(record["end_time"])
        and record["end_time"] < record["start_time"]
    ]
    assert reversed_rows


def test_sessions_sample_has_attendance_above_capacity() -> None:
    over_capacity = [
        record
        for record in sample_records("sessions.csv")
        if record["attendance"].isdigit()
        and int(record["attendance"]) > int(record["capacity"])
    ]
    assert over_capacity


@pytest.mark.parametrize(
    ("name", "id_column"),
    [("rosters.csv", "shift_id"), ("sessions.csv", "session_id")],
)
def test_sample_has_a_duplicate_id(name: str, id_column: str) -> None:
    counts = Counter(record[id_column] for record in sample_records(name))

    assert any(count > 1 for count in counts.values())


@pytest.mark.parametrize(
    ("name", "wrong_width"),
    [("rosters.csv", 6), ("sessions.csv", 9)],
)
def test_sample_has_a_row_with_the_wrong_number_of_columns(
    name: str,
    wrong_width: int,
) -> None:
    widths = sample_row_widths(name)

    assert wrong_width in widths
    assert widths.count(EXPECTED_COLUMNS) == len(widths) - 1


def test_rosters_sample_has_recoverable_spacing_and_case() -> None:
    messy = [
        record
        for record in sample_records("rosters.csv")
        if record["role"] != record["role"].strip().lower()
        and record["role"].strip().lower() in KNOWN_ROLES
        and record["centre_code"] != record["centre_code"].upper()
        and record["centre_code"].upper() in KNOWN_CENTRES
    ]
    assert messy


def test_sessions_sample_has_recoverable_spacing_and_case() -> None:
    messy = [
        record
        for record in sample_records("sessions.csv")
        if record["activity"] != record["activity"].strip().lower()
        and record["activity"].strip().lower() in KNOWN_ACTIVITIES
    ]
    assert messy


@pytest.mark.parametrize("name", SAMPLE_FILES)
def test_sample_contains_one_blank_line(name: str) -> None:
    lines = bundled_sample(name).decode("utf-8-sig").splitlines()

    assert lines.count("") == 1
