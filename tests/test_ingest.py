"""Tests for reading CSV files and the file-level checks."""

from pathlib import Path

import pytest

from roster_check.ingest import FIELD_TOO_LONG, UNFINISHED_QUOTE, read_csv
from roster_check.models import InputError
from roster_check.validate import ROSTER_COLUMNS, SESSION_COLUMNS

FIRST_ROW = "SH-00001,RBC,S-001,Jordan Placeholder,lifeguard,03/11/2026,06:00,10:30"


def test_reads_header_rows_and_physical_line_numbers(fixtures_dir: Path) -> None:
    csv_file = read_csv(fixtures_dir / "rosters_blank_lines.csv", ROSTER_COLUMNS)

    assert csv_file.file_name == "rosters_blank_lines.csv"
    assert csv_file.header == ROSTER_COLUMNS
    assert [row.line_number for row in csv_file.rows] == [2, 5]
    assert csv_file.rows[0].raw_text == FIRST_ROW
    assert csv_file.rows[0].fields == tuple(FIRST_ROW.split(","))


def test_blank_lines_are_skipped_and_counted(fixtures_dir: Path) -> None:
    csv_file = read_csv(fixtures_dir / "rosters_blank_lines.csv", ROSTER_COLUMNS)

    assert len(csv_file.rows) == 2
    assert csv_file.blank_lines == 2


def test_excel_byte_order_mark_and_line_endings_are_handled(
    fixtures_dir: Path,
) -> None:
    csv_file = read_csv(fixtures_dir / "rosters_excel_export.csv", ROSTER_COLUMNS)

    assert csv_file.header == ROSTER_COLUMNS
    assert csv_file.rows[0].raw_text == FIRST_ROW
    assert not csv_file.used_fallback_encoding


def test_columns_may_be_reordered_and_extra_columns_are_ignored(
    fixtures_dir: Path,
) -> None:
    csv_file = read_csv(fixtures_dir / "rosters_reordered_columns.csv", ROSTER_COLUMNS)

    assert csv_file.header[0] == "end_time"
    assert csv_file.header[7] == "shift_id"
    assert csv_file.ignored_columns == ("notes",)


def test_windows_1252_file_is_read_with_fallback(fixtures_dir: Path) -> None:
    csv_file = read_csv(fixtures_dir / "rosters_windows_1252.csv", ROSTER_COLUMNS)

    assert csv_file.used_fallback_encoding
    assert csv_file.rows[0].fields[3] == "Renée Placeholder"


def test_line_endings_from_old_mac_files_are_handled(tmp_path: Path) -> None:
    path = tmp_path / "rosters.csv"
    path.write_bytes(f"{','.join(ROSTER_COLUMNS)}\r{FIRST_ROW}".encode())

    csv_file = read_csv(path, ROSTER_COLUMNS)

    assert [row.raw_text for row in csv_file.rows] == [FIRST_ROW]


def test_quoted_fields_keep_their_commas(tmp_path: Path) -> None:
    path = tmp_path / "rosters.csv"
    row = 'SH-00001,RBC,S-001,"Placeholder, Jordan",lifeguard,03/11/2026,06:00,10:30'
    path.write_text(f"{','.join(ROSTER_COLUMNS)}\n{row}\n", encoding="utf-8")

    csv_file = read_csv(path, ROSTER_COLUMNS)

    assert csv_file.rows[0].fields[3] == "Placeholder, Jordan"
    assert csv_file.rows[0].raw_text == row


@pytest.mark.parametrize(
    ("fixture", "message"),
    [
        (
            "rosters_renamed_column.csv",
            "rosters_renamed_column.csv is missing column 'staff_id'",
        ),
        (
            "rosters_duplicate_column.csv",
            "rosters_duplicate_column.csv has duplicate column 'role'",
        ),
        ("rosters_empty.csv", "rosters_empty.csv has no rows"),
        ("rosters_header_only.csv", "rosters_header_only.csv has no rows"),
        (
            "rosters_unreadable_bytes.csv",
            "Could not read rosters_unreadable_bytes.csv",
        ),
    ],
)
def test_fatal_file_problems_raise_input_error(
    fixtures_dir: Path,
    fixture: str,
    message: str,
) -> None:
    with pytest.raises(InputError) as error:
        read_csv(fixtures_dir / fixture, ROSTER_COLUMNS)

    assert str(error.value) == message


def test_missing_file_raises_input_error(tmp_path: Path) -> None:
    with pytest.raises(InputError) as error:
        read_csv(tmp_path / "sessions.csv", SESSION_COLUMNS)

    assert str(error.value) == "sessions.csv not found"


def test_file_with_only_blank_lines_after_header_has_no_rows(tmp_path: Path) -> None:
    path = tmp_path / "rosters.csv"
    path.write_text(f"{','.join(ROSTER_COLUMNS)}\n\n\n", encoding="utf-8")

    with pytest.raises(InputError) as error:
        read_csv(path, ROSTER_COLUMNS)

    assert str(error.value) == "rosters.csv has no rows"


def test_unreadable_file_raises_input_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "rosters.csv"
    path.write_text("shift_id\n", encoding="utf-8")

    def refuse(_self: Path) -> bytes:
        raise PermissionError

    monkeypatch.setattr(Path, "read_bytes", refuse)

    with pytest.raises(InputError) as error:
        read_csv(path, ROSTER_COLUMNS)

    assert str(error.value) == "Could not read rosters.csv"


def test_unfinished_quote_is_reported_not_parsed(tmp_path: Path) -> None:
    path = tmp_path / "rosters.csv"
    lines = [
        'SH-00001,RBC,S-001,"Jordan',
        'Placeholder",lifeguard,03/11/2026,06:00,10:30',
        'SH-00002,RBC,S-002,Casey Example,lifeguard,03/11/2026,06:00,"10:30',
    ]
    path.write_text("\n".join([",".join(ROSTER_COLUMNS), *lines]), encoding="utf-8")

    csv_file = read_csv(path, ROSTER_COLUMNS)

    assert [row.problem for row in csv_file.rows] == [UNFINISHED_QUOTE] * 3
    assert all(row.fields == () for row in csv_file.rows)
    assert [row.raw_text for row in csv_file.rows] == lines


def test_oversized_field_in_an_ignored_column_is_reported_not_raised(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rosters.csv"
    huge_note = "x" * 200_000
    path.write_text(
        f"{','.join(ROSTER_COLUMNS)},notes\n{FIRST_ROW},{huge_note}\n{FIRST_ROW},ok\n",
        encoding="utf-8",
    )

    csv_file = read_csv(path, ROSTER_COLUMNS)

    assert csv_file.rows[0].problem == FIELD_TOO_LONG
    assert csv_file.rows[0].fields == ()
    assert csv_file.rows[1].problem is None


def test_unparseable_header_raises_input_error(tmp_path: Path) -> None:
    path = tmp_path / "rosters.csv"
    path.write_text(f'"shift_id,{FIRST_ROW}\n', encoding="utf-8")

    with pytest.raises(InputError) as error:
        read_csv(path, ROSTER_COLUMNS)

    assert str(error.value) == "Could not read rosters.csv"


def test_permission_error_while_checking_the_file_raises_input_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(_self: Path) -> bool:
        raise PermissionError

    monkeypatch.setattr(Path, "is_file", refuse)

    with pytest.raises(InputError) as error:
        read_csv(tmp_path / "rosters.csv", ROSTER_COLUMNS)

    assert str(error.value) == "Could not read rosters.csv"
