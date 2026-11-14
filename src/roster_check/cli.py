"""Command-line interface: runs the pipeline, writes the report, returns the exit code.

This is the only module that prints or writes output files. It reads the input
files, passes them through ``validate``, ``db``, ``analysis`` and ``report``,
writes the HTML page and prints a short summary. Fatal input problems and
unexpected errors are reported in one plain line; ``--debug`` adds the
traceback.
"""

import argparse
import sys
import traceback
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

import duckdb

from roster_check import __version__
from roster_check.analysis import analyse
from roster_check.db import create_database
from roster_check.ingest import read_csv
from roster_check.models import CsvFile, InputError, ReportData, ValidationResult
from roster_check.report import percent_text, render_report
from roster_check.validate import (
    CENTRE_COLUMNS,
    CLEANED_REASON,
    ROSTER_COLUMNS,
    SESSION_COLUMNS,
    STAFFING_RULE_COLUMNS,
    validate_centres,
    validate_sessions,
    validate_shifts,
    validate_staffing_rules,
)

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_INPUT_ERROR = 2

DATA_DIR = Path(str(files("roster_check").joinpath("data")))
CENTRES_FILE = DATA_DIR / "centres.csv"
DEFAULT_RULES_FILE = DATA_DIR / "staffing_rules.csv"
SAMPLE_ROSTERS_FILE = DATA_DIR / "sample" / "rosters.csv"
SAMPLE_SESSIONS_FILE = DATA_DIR / "sample" / "sessions.csv"
DEFAULT_OUT_FILE = Path("roster-check-report.html")

SUMMARY_SKIPPED = "Skipping AI summary: not available in this version"


@dataclass(frozen=True)
class DataFile:
    """A data file as read by ``ingest`` and checked by ``validate``."""

    csv: CsvFile
    result: ValidationResult[Any]


@dataclass(frozen=True)
class PipelineOutput:
    """Everything one run produces for the report file and the terminal.

    Attributes:
        report: The figures from ``analysis.analyse``.
        reference_files: The centres and staffing rules files as read.
        data_files: The roster and session files, in that order.
        html: The complete report page.
    """

    report: ReportData
    reference_files: tuple[CsvFile, ...]
    data_files: tuple[DataFile, ...]
    html: str


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the ``roster-check`` command.

    Returns:
        A parser configured with every supported option.
    """
    parser = argparse.ArgumentParser(
        prog="roster-check",
        description=(
            "Check staff rosters against session attendance "
            "and report understaffed sessions."
        ),
    )
    parser.add_argument(
        "--rosters",
        type=Path,
        metavar="PATH",
        help="roster CSV file (default: the bundled sample)",
    )
    parser.add_argument(
        "--sessions",
        type=Path,
        metavar="PATH",
        help="session CSV file (default: the bundled sample)",
    )
    parser.add_argument(
        "--rules",
        type=Path,
        default=DEFAULT_RULES_FILE,
        metavar="PATH",
        help="staffing rules CSV file (default: the bundled rules)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_FILE,
        metavar="PATH",
        help=f"report file to write, replacing any existing one "
        f"(default: {DEFAULT_OUT_FILE})",
    )
    parser.add_argument(
        "--db-file",
        type=Path,
        metavar="PATH",
        help="save the DuckDB database to this file, replacing any existing one",
    )
    parser.add_argument(
        "--summarise",
        action="store_true",
        help="add an AI-written summary to the report (not available yet)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit with code 1 if any row was rejected",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="open the report in the default browser",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="show the full traceback when something goes wrong",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    clock: Callable[[], datetime] = datetime.now,
) -> int:
    """Run the command-line tool.

    Args:
        argv: Arguments excluding the program name. Defaults to ``sys.argv[1:]``.
        clock: Returns the time shown as the report's generated time. Tests
            pass a fixed clock.

    Returns:
        The process exit code: 0 on success, 1 for an unexpected error or a
        ``--strict`` failure, 2 for a fatal input problem.
    """
    args = build_parser().parse_args(argv)
    try:
        return run(args, clock())
    except InputError as error:
        return _fail(str(error), EXIT_INPUT_ERROR, debug=args.debug)
    # The top level catches everything so users never see a traceback by default.
    except Exception as error:
        return _fail(_unexpected_message(error), EXIT_FAILURE, debug=args.debug)


def run(args: argparse.Namespace, generated_at: datetime) -> int:
    """Build and write the report as the parsed arguments ask, then summarise it.

    Args:
        args: Parsed command-line arguments from ``build_parser``.
        generated_at: The time shown as the report's generated time.

    Returns:
        The process exit code.

    Raises:
        InputError: If an input file cannot be used or an output file cannot
            be written.
    """
    if args.summarise:
        print(SUMMARY_SKIPPED)
    _check_output_folder(args.out)
    if args.db_file is not None:
        _check_output_folder(args.db_file)
        _check_different_files(args.out, args.db_file)

    output = build_report(
        rosters_file=args.rosters or SAMPLE_ROSTERS_FILE,
        sessions_file=args.sessions or SAMPLE_SESSIONS_FILE,
        rules_file=args.rules,
        generated_at=generated_at,
        sample_data=args.rosters is None or args.sessions is None,
        database_file=args.db_file,
    )
    _write_report(args.out, output.html)
    for line in summary_lines(output, args.out):
        print(line)

    if args.open and not _open_in_browser(args.out):
        print(f"Could not open a browser; the report is at {args.out}")

    rows_rejected = output.report.kpis.rows_rejected
    if args.strict and rows_rejected > 0:
        print(
            f"Strict mode: {_count(rows_rejected, 'row', 'rows')} rejected",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    return EXIT_SUCCESS


def build_report(
    *,
    rosters_file: Path,
    sessions_file: Path,
    rules_file: Path,
    generated_at: datetime,
    sample_data: bool,
    database_file: Path | None = None,
) -> PipelineOutput:
    """Run the input files through every stage of the pipeline.

    Args:
        rosters_file: The roster CSV file.
        sessions_file: The session CSV file.
        rules_file: The staffing rules CSV file.
        generated_at: The time shown as the report's generated time.
        sample_data: True when bundled sample data is used, which adds a note
            to the report that the data is fictional.
        database_file: A file to save the database in, replacing any existing
            one once the inputs have been validated, or ``None`` to keep the
            database in memory.

    Returns:
        The report page together with what the terminal summary needs.

    Raises:
        InputError: If any input file cannot be used.
    """
    centres_csv = read_csv(CENTRES_FILE, CENTRE_COLUMNS)
    rules_csv = read_csv(rules_file, STAFFING_RULE_COLUMNS)
    rosters_csv = read_csv(rosters_file, ROSTER_COLUMNS)
    sessions_csv = read_csv(sessions_file, SESSION_COLUMNS)

    centres = validate_centres(centres_csv)
    rules = validate_staffing_rules(rules_csv)
    centre_codes = {centre.centre_code for centre in centres}
    shifts = validate_shifts(rosters_csv, centre_codes)
    sessions = validate_sessions(
        sessions_csv, centre_codes, {rule.activity for rule in rules}
    )

    connection = create_database(
        centres=centres,
        rules=rules,
        shifts=shifts.valid,
        sessions=sessions.valid,
        rejections=shifts.rejected + sessions.rejected,
        connection=(
            None if database_file is None else _open_database_file(database_file)
        ),
    )
    try:
        report = analyse(connection)
    finally:
        connection.close()

    html = render_report(
        report,
        [shifts, sessions],
        generated_at=generated_at,
        version=__version__,
        sample_data=sample_data,
    )
    return PipelineOutput(
        report=report,
        reference_files=(centres_csv, rules_csv),
        data_files=(DataFile(rosters_csv, shifts), DataFile(sessions_csv, sessions)),
        html=html,
    )


def summary_lines(output: PipelineOutput, out_file: Path) -> list[str]:
    """Return the lines of the terminal summary for one run.

    One line per data file, a note for each file read with a fallback
    encoding or with ignored columns, then the understaffing result and
    where the report was written.
    """
    lines = [_data_file_line(data_file) for data_file in output.data_files]
    every_csv = [
        *output.reference_files,
        *(data_file.csv for data_file in output.data_files),
    ]
    for csv_file in every_csv:
        lines.extend(_file_notes(csv_file))
    kpis = output.report.kpis
    lines.append(
        f"Understaffed sessions: {kpis.understaffed_sessions} of "
        f"{kpis.sessions_analysed} ({percent_text(kpis.understaffed_percent)})"
    )
    lines.append(f"Report written to {out_file}")
    return lines


def _data_file_line(data_file: DataFile) -> str:
    """Describe what happened to the rows of one data file."""
    csv_file = data_file.csv
    result = data_file.result
    # Cleaning fixes a row; any other warning, such as attendance above
    # capacity, only flags it. A row can carry both and is then counted in
    # both, so rows are counted rather than warnings.
    auto_fixed = {
        warning.line_number
        for warning in result.warnings
        if warning.reason == CLEANED_REASON
    }
    flagged = {
        warning.line_number
        for warning in result.warnings
        if warning.reason != CLEANED_REASON
    }
    parts = [
        f"{_count(len(csv_file.rows), 'row', 'rows')} read",
        f"{len(result.rejected)} rejected",
    ]
    if auto_fixed:
        parts.append(f"{len(auto_fixed)} auto-fixed")
    if flagged:
        parts.append(f"{len(flagged)} flagged")
    if csv_file.blank_lines:
        parts.append(
            f"{_count(csv_file.blank_lines, 'blank line', 'blank lines')} skipped"
        )
    return f"{csv_file.file_name}: {', '.join(parts)}"


def _file_notes(csv_file: CsvFile) -> list[str]:
    """Return the notes for a file read with a fallback encoding or extra columns."""
    notes = []
    if csv_file.used_fallback_encoding:
        notes.append(
            f"Note: {csv_file.file_name} was read as Windows-1252 "
            "because it is not valid UTF-8"
        )
    if csv_file.ignored_columns:
        notes.append(
            f"Note: {csv_file.file_name} columns ignored: "
            f"{', '.join(csv_file.ignored_columns)}"
        )
    return notes


def _count(number: int, singular: str, plural: str) -> str:
    """Return a number with the singular or plural noun, for example "1 row"."""
    return f"{number} {singular if number == 1 else plural}"


def _check_output_folder(path: Path) -> None:
    """Raise ``InputError`` if the folder an output file goes in does not exist."""
    if not path.parent.is_dir():
        message = f"Folder not found for {path}"
        raise InputError(message)


def _check_different_files(out_file: Path, database_file: Path) -> None:
    """Raise ``InputError`` if the report and the database would share a file.

    Paths are resolved first, so a relative and an absolute path to the same
    file are caught.
    """
    if out_file.resolve() == database_file.resolve():
        message = "--out and --db-file must be different files"
        raise InputError(message)


def _open_database_file(path: Path) -> duckdb.DuckDBPyConnection:
    """Replace any existing database file and open a new, empty one.

    DuckDB keeps a write-ahead log beside the file, which is removed too.

    Raises:
        InputError: If the old file cannot be removed or the new one cannot
            be created.
    """
    for file in (path, path.with_name(f"{path.name}.wal")):
        try:
            file.unlink(missing_ok=True)
        except OSError:
            message = f"Could not replace {file}"
            raise InputError(message) from None
    try:
        return duckdb.connect(str(path))
    except duckdb.Error:
        message = f"Could not create {path}"
        raise InputError(message) from None


def _write_report(path: Path, html: str) -> None:
    """Write the report page, replacing any existing file."""
    try:
        path.write_text(html, encoding="utf-8")
    except OSError:
        message = f"Could not write {path}"
        raise InputError(message) from None


def _open_in_browser(path: Path) -> bool:
    """Open the report in the default browser and return whether that worked."""
    try:
        return webbrowser.open(path.resolve().as_uri())
    except webbrowser.Error:
        return False


def _unexpected_message(error: Exception) -> str:
    """Describe an unexpected error in one line."""
    detail = str(error).splitlines()[0] if str(error) else type(error).__name__
    return f"Unexpected error: {detail}. Run again with --debug for details."


def _fail(message: str, exit_code: int, *, debug: bool) -> int:
    """Print an error message, and the traceback when debugging; return the code."""
    print(message, file=sys.stderr)
    if debug:
        traceback.print_exc()
    return exit_code
