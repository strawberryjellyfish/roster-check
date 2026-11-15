"""Tests for the command-line interface."""

import runpy
import subprocess
import sys
import webbrowser
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from unittest.mock import Mock

import duckdb
import pytest

from roster_check import __version__, cli
from roster_check.cli import main
from roster_check.db import VIEW_NAMES
from roster_check.validate import ROSTER_COLUMNS, SESSION_COLUMNS

FIXED_TIME = datetime(2026, 11, 15, 9, 30)
REPORT_FILE = "roster-check-report.html"
FICTIONAL_NOTE = "All data in this report is fictional."
AI_UNAVAILABLE_NOTE = (
    "The AI summary was unavailable, so this summary was built from the numbers."
)

SAMPLE_SUMMARY = [
    "rosters.csv: 557 rows read, 9 rejected, 1 auto-fixed, 1 blank line skipped",
    "sessions.csv: 289 rows read, 8 rejected, 1 auto-fixed, 1 flagged, "
    "1 blank line skipped",
    "Understaffed sessions: 43 of 281 (15%)",
    f"Report written to {REPORT_FILE}",
]


@pytest.fixture(autouse=True)
def work_in_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every test in an empty folder so the default report lands there."""
    monkeypatch.chdir(tmp_path)


def run_cli(*args: str) -> int:
    """Run the command in-process with a fixed clock and return its exit code."""
    return main(list(args), clock=lambda: FIXED_TIME)


def write_csv(path: Path, columns: tuple[str, ...], *rows: str) -> Path:
    """Write a small CSV file with a header and the given data lines."""
    path.write_text("\n".join([",".join(columns), *rows]) + "\n", encoding="utf-8")
    return path


def clean_rosters(folder: Path) -> Path:
    """Write a roster file whose only row is valid."""
    return write_csv(
        folder / "clean_rosters.csv",
        ROSTER_COLUMNS,
        "SH-1,RBC,S-1,Alex Example,lifeguard,04/11/2026,06:00,12:00",
    )


def clean_sessions(folder: Path) -> Path:
    """Write a session file whose only row is valid."""
    return write_csv(
        folder / "clean_sessions.csv",
        SESSION_COLUMNS,
        "SE-1,RBC,lap_swim,04/11/2026,07:00,08:00,40,10",
    )


@pytest.fixture
def small_inputs(tmp_path: Path) -> list[str]:
    """Arguments pointing at tiny valid input files.

    Most tests use these instead of the bundled sample, which keeps the suite
    fast; the sample is run only where its exact output is checked.
    """
    return [
        "--rosters",
        str(clean_rosters(tmp_path)),
        "--sessions",
        str(clean_sessions(tmp_path)),
    ]


def test_package_version_matches_installed_metadata() -> None:
    assert __version__ == version("roster-check")


def test_version_flag_prints_version_and_exits_cleanly(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"roster-check {__version__}"


def test_unknown_argument_exits_with_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--not-a-real-option"])

    assert exit_info.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_module_entry_point_runs_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["roster_check", "--version"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("roster_check", run_name="__main__")

    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_arguments_writes_the_sample_report_and_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_cli() == 0

    output = capsys.readouterr()
    assert output.out.splitlines() == SAMPLE_SUMMARY
    assert output.err == ""
    page = (tmp_path / REPORT_FILE).read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>")
    assert FICTIONAL_NOTE in page


def test_report_shows_the_time_from_the_injected_clock(
    tmp_path: Path, small_inputs: list[str]
) -> None:
    run_cli(*small_inputs)

    page = (tmp_path / REPORT_FILE).read_text(encoding="utf-8")
    assert "Sun 15 Nov 2026 at 09:30" in page


def test_out_writes_the_report_to_the_given_path(
    tmp_path: Path, small_inputs: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    out_file = tmp_path / "custom.html"

    assert run_cli(*small_inputs, "--out", str(out_file)) == 0

    assert out_file.is_file()
    assert not (tmp_path / REPORT_FILE).exists()
    assert f"Report written to {out_file}" in capsys.readouterr().out


def test_existing_report_is_replaced(tmp_path: Path, small_inputs: list[str]) -> None:
    out_file = tmp_path / REPORT_FILE
    out_file.write_text("old report", encoding="utf-8")

    assert run_cli(*small_inputs) == 0

    assert out_file.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_own_input_files_leave_out_the_fictional_data_note(
    tmp_path: Path, small_inputs: list[str]
) -> None:
    assert run_cli(*small_inputs) == 0

    page = (tmp_path / REPORT_FILE).read_text(encoding="utf-8")
    assert FICTIONAL_NOTE not in page


def test_summary_counts_rows_without_optional_parts_when_none_apply(
    small_inputs: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    run_cli(*small_inputs)

    lines = capsys.readouterr().out.splitlines()
    assert lines[:2] == [
        "clean_rosters.csv: 1 row read, 0 rejected",
        "clean_sessions.csv: 1 row read, 0 rejected",
    ]


def test_summary_notes_fallback_encoding(
    fixtures_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rosters = fixtures_dir / "rosters_windows_1252.csv"
    sessions = clean_sessions(tmp_path)

    assert run_cli("--rosters", str(rosters), "--sessions", str(sessions)) == 0

    assert (
        "Note: rosters_windows_1252.csv was read as Windows-1252 "
        "because it is not valid UTF-8"
    ) in capsys.readouterr().out.splitlines()


def test_summary_notes_ignored_columns(
    fixtures_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rosters = fixtures_dir / "rosters_reordered_columns.csv"
    sessions = clean_sessions(tmp_path)

    assert run_cli("--rosters", str(rosters), "--sessions", str(sessions)) == 0

    assert (
        "Note: rosters_reordered_columns.csv columns ignored: notes"
        in capsys.readouterr().out.splitlines()
    )


def test_strict_fails_after_writing_the_report_when_rows_were_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rosters = write_csv(
        tmp_path / "rosters.csv",
        ROSTER_COLUMNS,
        "SH-1,RBC,S-1,Alex Example,lifeguard,04/11/2026,06:00,12:00",
        "SH-2,XYZ,S-2,Sam Example,lifeguard,04/11/2026,06:00,12:00",
    )
    sessions = clean_sessions(tmp_path)

    exit_code = run_cli(
        "--rosters", str(rosters), "--sessions", str(sessions), "--strict"
    )

    assert exit_code == 1
    assert capsys.readouterr().err.strip() == "Strict mode: 1 row rejected"
    assert (tmp_path / REPORT_FILE).is_file()


def test_strict_succeeds_when_no_row_was_rejected(small_inputs: list[str]) -> None:
    assert run_cli(*small_inputs, "--strict") == 0


def test_summarise_without_an_api_key_is_skipped_and_noted_in_the_report(
    tmp_path: Path, small_inputs: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_cli(*small_inputs, "--summarise") == 0

    first_line = capsys.readouterr().out.splitlines()[0]
    assert first_line == "Skipping AI summary: no API key set"
    page = (tmp_path / REPORT_FILE).read_text(encoding="utf-8")
    assert AI_UNAVAILABLE_NOTE in page


def test_summarise_puts_the_ai_summary_in_the_report(
    tmp_path: Path,
    small_inputs: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "skip_reason", lambda: None)
    monkeypatch.setattr(cli, "summarise", lambda report: "Staffing held up well.")

    assert run_cli(*small_inputs, "--summarise") == 0

    assert capsys.readouterr().out.splitlines()[0].startswith("clean_rosters.csv:")
    page = (tmp_path / REPORT_FILE).read_text(encoding="utf-8")
    assert '<span class="ai-label">AI-generated</span>' in page
    assert "<p>Staffing held up well.</p>" in page


def test_summarise_failure_keeps_the_standard_summary(
    tmp_path: Path,
    small_inputs: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "skip_reason", lambda: None)
    monkeypatch.setattr(cli, "summarise", lambda report: None)

    assert run_cli(*small_inputs, "--summarise") == 0

    first_line = capsys.readouterr().out.splitlines()[0]
    assert first_line == "AI summary unavailable; the report uses the standard summary"
    page = (tmp_path / REPORT_FILE).read_text(encoding="utf-8")
    assert AI_UNAVAILABLE_NOTE in page
    assert "AI-generated" not in page


def test_no_summary_is_requested_without_summarise(
    tmp_path: Path, small_inputs: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def must_not_run(report: object) -> None:
        raise AssertionError("summarise was called")

    monkeypatch.setattr(cli, "summarise", must_not_run)

    assert run_cli(*small_inputs) == 0

    page = (tmp_path / REPORT_FILE).read_text(encoding="utf-8")
    assert AI_UNAVAILABLE_NOTE not in page


def test_missing_input_file_is_a_fatal_input_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_cli("--rosters", str(tmp_path / "missing.csv")) == 2

    assert capsys.readouterr().err.strip() == "missing.csv not found"
    assert not (tmp_path / REPORT_FILE).exists()


@pytest.mark.parametrize(
    ("fixture", "message"),
    [
        ("rosters_empty.csv", "rosters_empty.csv has no rows"),
        (
            "rosters_renamed_column.csv",
            "rosters_renamed_column.csv is missing column 'staff_id'",
        ),
    ],
)
def test_fatal_fixture_exits_with_code_2_and_writes_no_report(
    fixture: str,
    message: str,
    fixtures_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run_cli("--rosters", str(fixtures_dir / fixture)) == 2

    assert capsys.readouterr().err.strip() == message
    assert not (tmp_path / REPORT_FILE).exists()


def test_bad_rules_file_is_a_fatal_input_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rules = tmp_path / "rules.csv"
    rules.write_text(
        "activity,role,participants_per_staff,minimum_staff\nlap_swim,cleaner,40,1\n",
        encoding="utf-8",
    )

    assert run_cli("--rules", str(rules)) == 2

    assert capsys.readouterr().err.strip() == "rules.csv line 2: Unknown role 'cleaner'"


def test_every_row_rejected_still_writes_the_report_with_a_banner(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    rosters = clean_rosters(tmp_path)
    sessions = fixtures_dir / "sessions_all_rejected.csv"

    assert run_cli("--rosters", str(rosters), "--sessions", str(sessions)) == 0

    page = (tmp_path / REPORT_FILE).read_text(encoding="utf-8")
    assert "No usable rows in sessions_all_rejected.csv" in page


def test_missing_output_folder_is_a_fatal_input_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_file = tmp_path / "no_such_folder" / "report.html"

    assert run_cli("--out", str(out_file)) == 2

    assert capsys.readouterr().err.strip() == f"Folder not found for {out_file}"


def test_unwritable_report_path_is_a_fatal_input_error(
    tmp_path: Path, small_inputs: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "a_folder"
    folder.mkdir()

    assert run_cli(*small_inputs, "--out", str(folder)) == 2

    assert capsys.readouterr().err.strip() == f"Could not write {folder}"


def test_unexpected_error_is_one_line_without_a_traceback(
    small_inputs: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def broken_analysis(connection: duckdb.DuckDBPyConnection) -> None:
        raise RuntimeError("database fell over\nsecond line")

    monkeypatch.setattr(cli, "analyse", broken_analysis)

    assert run_cli(*small_inputs) == 1

    error = capsys.readouterr().err
    assert error.strip() == (
        "Unexpected error: database fell over. Run again with --debug for details."
    )
    assert "Traceback" not in error


def test_unexpected_error_without_a_message_names_its_type(
    small_inputs: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def broken_analysis(connection: duckdb.DuckDBPyConnection) -> None:
        raise KeyError

    monkeypatch.setattr(cli, "analyse", broken_analysis)

    assert run_cli(*small_inputs) == 1

    assert capsys.readouterr().err.startswith("Unexpected error: KeyError.")


def test_debug_adds_the_traceback(
    small_inputs: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def broken_analysis(connection: duckdb.DuckDBPyConnection) -> None:
        raise RuntimeError("database fell over")

    monkeypatch.setattr(cli, "analyse", broken_analysis)

    assert run_cli(*small_inputs, "--debug") == 1

    error = capsys.readouterr().err
    assert "Traceback (most recent call last)" in error
    assert "RuntimeError: database fell over" in error


def test_open_passes_the_report_address_to_the_browser(
    tmp_path: Path, small_inputs: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)

    assert run_cli(*small_inputs, "--open") == 0

    assert opened == [(tmp_path / REPORT_FILE).resolve().as_uri()]


def test_open_without_a_browser_notes_where_the_report_is(
    small_inputs: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(webbrowser, "open", lambda url: False)

    assert run_cli(*small_inputs, "--open") == 0

    last_line = capsys.readouterr().out.splitlines()[-1]
    assert last_line == f"Could not open a browser; the report is at {REPORT_FILE}"


def test_open_treats_a_browser_error_as_no_browser(
    small_inputs: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def failing_open(url: str) -> bool:
        raise webbrowser.Error("no runnable browser")

    monkeypatch.setattr(webbrowser, "open", failing_open)

    assert run_cli(*small_inputs, "--open") == 0

    assert "Could not open a browser" in capsys.readouterr().out


def test_db_file_saves_the_tables_and_views(
    tmp_path: Path, small_inputs: list[str]
) -> None:
    database_file = tmp_path / "roster_check.duckdb"

    assert run_cli(*small_inputs, "--db-file", str(database_file)) == 0

    with duckdb.connect(str(database_file), read_only=True) as connection:
        tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
    assert {"centres", "rules", "shifts", "sessions", "rejections"} <= tables
    assert tables >= VIEW_NAMES


@pytest.mark.parametrize("failing_stage", ["create_database", "analyse"])
def test_db_file_connection_is_closed_on_pipeline_failure(
    tmp_path: Path,
    small_inputs: list[str],
    monkeypatch: pytest.MonkeyPatch,
    failing_stage: str,
) -> None:
    database_file = tmp_path / "roster_check.duckdb"
    open_database = cli._open_database_file
    connections: list[duckdb.DuckDBPyConnection] = []

    def capture_connection(path: Path) -> duckdb.DuckDBPyConnection:
        connection = open_database(path)
        connections.append(connection)
        return connection

    monkeypatch.setattr(cli, "_open_database_file", capture_connection)
    monkeypatch.setattr(
        cli, failing_stage, Mock(side_effect=RuntimeError("pipeline failed"))
    )

    assert run_cli(*small_inputs, "--db-file", str(database_file)) == 1

    assert len(connections) == 1
    with pytest.raises(duckdb.ConnectionException, match="closed"):
        connections[0].table("centres")


def test_db_file_replaces_an_existing_file(
    tmp_path: Path, small_inputs: list[str]
) -> None:
    database_file = tmp_path / "roster_check.duckdb"
    run_cli(*small_inputs, "--db-file", str(database_file))

    assert run_cli(*small_inputs, "--db-file", str(database_file)) == 0


def test_db_file_is_kept_when_the_input_is_fatal(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    database_file = tmp_path / "roster_check.duckdb"
    database_file.write_text("existing contents", encoding="utf-8")

    exit_code = run_cli(
        "--db-file",
        str(database_file),
        "--rosters",
        str(fixtures_dir / "rosters_empty.csv"),
    )

    assert exit_code == 2
    assert database_file.read_text(encoding="utf-8") == "existing contents"


def test_db_file_in_a_missing_folder_is_a_fatal_input_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database_file = tmp_path / "no_such_folder" / "roster_check.duckdb"

    assert run_cli("--db-file", str(database_file)) == 2

    assert capsys.readouterr().err.strip() == f"Folder not found for {database_file}"


def test_db_file_that_cannot_be_removed_is_a_fatal_input_error(
    tmp_path: Path,
    small_inputs: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_file = tmp_path / "roster_check.duckdb"

    def locked_unlink(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("file is in use")

    monkeypatch.setattr(Path, "unlink", locked_unlink)

    assert run_cli(*small_inputs, "--db-file", str(database_file)) == 2

    assert capsys.readouterr().err.strip() == f"Could not replace {database_file}"


def test_db_file_that_cannot_be_created_is_a_fatal_input_error(
    tmp_path: Path,
    small_inputs: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_file = tmp_path / "roster_check.duckdb"

    def failing_connect(database: str) -> duckdb.DuckDBPyConnection:
        raise duckdb.IOException("cannot open file")

    monkeypatch.setattr(duckdb, "connect", failing_connect)

    assert run_cli(*small_inputs, "--db-file", str(database_file)) == 2

    assert capsys.readouterr().err.strip() == f"Could not create {database_file}"


@pytest.mark.parametrize("db_file_form", ["relative", "absolute"])
def test_same_file_for_report_and_database_is_rejected_before_writing(
    db_file_form: str,
    tmp_path: Path,
    small_inputs: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    shared = "shared.out"
    db_file = shared if db_file_form == "relative" else str(tmp_path / shared)

    assert run_cli(*small_inputs, "--out", shared, "--db-file", db_file) == 2

    message = capsys.readouterr().err.strip()
    assert message == "--out and --db-file must be different files"
    assert not (tmp_path / shared).exists()


def test_summary_separates_auto_fixed_rows_from_flagged_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rosters = clean_rosters(tmp_path)
    sessions = write_csv(
        tmp_path / "sessions.csv",
        SESSION_COLUMNS,
        " se-1 ,rbc,lap_swim,04/11/2026,07:00,08:00,40,10",
        "SE-2,RBC,lap_swim,04/11/2026,09:00,10:00,40,45",
    )

    run_cli("--rosters", str(rosters), "--sessions", str(sessions))

    lines = capsys.readouterr().out.splitlines()
    assert lines[1] == "sessions.csv: 2 rows read, 0 rejected, 1 auto-fixed, 1 flagged"


def test_attendance_above_capacity_is_kept_as_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rosters = clean_rosters(tmp_path)
    sessions = write_csv(
        tmp_path / "sessions.csv",
        SESSION_COLUMNS,
        "SE-2,RBC,lap_swim,04/11/2026,09:00,10:00,40,45",
    )
    database_file = tmp_path / "roster_check.duckdb"

    run_cli(
        "--rosters",
        str(rosters),
        "--sessions",
        str(sessions),
        "--db-file",
        str(database_file),
    )

    sessions_line = capsys.readouterr().out.splitlines()[1]
    assert sessions_line == "sessions.csv: 1 row read, 0 rejected, 1 flagged"
    with duckdb.connect(str(database_file), read_only=True) as connection:
        stored = connection.execute("SELECT attendance FROM sessions").fetchall()
    assert stored == [(45,)]


def run_command(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the real command in a separate process and capture its output."""
    return subprocess.run(
        [sys.executable, "-m", "roster_check", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_command_writes_the_sample_report_end_to_end(tmp_path: Path) -> None:
    result = run_command(cwd=tmp_path)

    assert result.returncode == 0
    assert result.stdout.splitlines() == SAMPLE_SUMMARY
    assert (tmp_path / REPORT_FILE).is_file()


@pytest.mark.parametrize(
    ("fixture", "message"),
    [
        ("missing.csv", "missing.csv not found"),
        ("rosters_empty.csv", "rosters_empty.csv has no rows"),
        (
            "rosters_renamed_column.csv",
            "rosters_renamed_column.csv is missing column 'staff_id'",
        ),
        (
            "rosters_duplicate_column.csv",
            "rosters_duplicate_column.csv has duplicate column 'role'",
        ),
    ],
)
def test_command_reports_fatal_input_in_one_line_end_to_end(
    fixture: str, message: str, fixtures_dir: Path, tmp_path: Path
) -> None:
    result = run_command("--rosters", str(fixtures_dir / fixture), cwd=tmp_path)

    assert result.returncode == 2
    assert result.stderr.strip() == message
    assert "Traceback" not in result.stdout + result.stderr
    assert not (tmp_path / REPORT_FILE).exists()
