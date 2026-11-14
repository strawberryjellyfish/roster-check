"""Validate: turn raw CSV rows into checked records.

Pure functions with no I/O. Each data row is cleaned, checked column by column
in the order the brief lists them, and either becomes a record or is rejected
with the first problem found. The rules are in sections 4.4 and 4.5 of the
project brief.

Problems in the reference files (centres and staffing rules) are fatal and
raise ``InputError``.
"""

import re
from collections.abc import Callable, Collection, Sequence
from datetime import date, time
from typing import TypeVar

from roster_check.models import (
    Centre,
    CsvFile,
    InputError,
    Rejection,
    RowWarning,
    Session,
    Shift,
    StaffingRule,
    ValidationResult,
)

T = TypeVar("T")

ROSTER_COLUMNS = (
    "shift_id",
    "centre_code",
    "staff_id",
    "staff_name",
    "role",
    "shift_date",
    "start_time",
    "end_time",
)
SESSION_COLUMNS = (
    "session_id",
    "centre_code",
    "activity",
    "session_date",
    "start_time",
    "end_time",
    "capacity",
    "attendance",
)
CENTRE_COLUMNS = ("centre_code", "centre_name")
STAFFING_RULE_COLUMNS = ("activity", "role", "participants_per_staff", "minimum_staff")

KNOWN_ROLES = frozenset(
    {"lifeguard", "swim_instructor", "gym_supervisor", "group_fitness", "front_desk"}
)

# Plain-English names for columns, used in messages shown to the user.
COLUMN_LABELS = {
    "shift_id": "shift ID",
    "session_id": "session ID",
    "centre_code": "centre code",
    "centre_name": "centre name",
    "staff_id": "staff ID",
    "staff_name": "staff name",
    "role": "role",
    "activity": "activity",
    "shift_date": "shift date",
    "session_date": "session date",
    "start_time": "start time",
    "end_time": "end time",
    "capacity": "capacity",
    "attendance": "attendance",
    "participants_per_staff": "participants per staff",
    "minimum_staff": "minimum staff",
}

UPPER_CASE_COLUMNS = frozenset({"shift_id", "session_id", "staff_id", "centre_code"})
LOWER_CASE_COLUMNS = frozenset({"role", "activity"})

CLEANED_REASON = "Cleaned spacing and capitals"

DAY_FIRST_DATE = re.compile(r"([0-9]{1,2})/([0-9]{1,2})/([0-9]{4})")
ISO_DATE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
CLOCK_TIME = re.compile(r"([0-9]{1,2}):([0-9]{2})(?::00)?")
WHOLE_NUMBER = re.compile(r"-?[0-9]+")
DECIMAL_NUMBER = re.compile(r"-?[0-9]*\.[0-9]+")


class RowError(Exception):
    """A problem that rejects a row. The message is the reason shown to the user."""


def validate_shifts(
    csv_file: CsvFile,
    centre_codes: Collection[str],
) -> ValidationResult[Shift]:
    """Validate every row of ``rosters.csv``.

    Args:
        csv_file: The ingested file.
        centre_codes: Codes of the known centres.

    Returns:
        Valid shifts, rejected rows and warnings.
    """

    def build(values: dict[str, str], line_number: int) -> tuple[Shift, list[str]]:
        shift_id = require(values, "shift_id")
        centre_code = require_known(values, "centre_code", centre_codes, "centre")
        staff_id = require(values, "staff_id")
        staff_name = values["staff_name"] or None
        role = require_known(values, "role", KNOWN_ROLES, "role")
        shift_date = parse_date(require(values, "shift_date"), "shift date")
        start_time = parse_time(require(values, "start_time"), "start time")
        end_time = parse_time(require(values, "end_time"), "end time")
        check_time_order(start_time, end_time, "Shift")
        shift = Shift(
            shift_id=shift_id,
            centre_code=centre_code,
            staff_id=staff_id,
            staff_name=staff_name,
            role=role,
            shift_date=shift_date,
            start_time=start_time,
            end_time=end_time,
            line_number=line_number,
        )
        return shift, []

    return _validate_rows(csv_file, ROSTER_COLUMNS, ("shift_id",), "shift ID", build)


def validate_sessions(
    csv_file: CsvFile,
    centre_codes: Collection[str],
    activities: Collection[str],
) -> ValidationResult[Session]:
    """Validate every row of ``sessions.csv``.

    Args:
        csv_file: The ingested file.
        centre_codes: Codes of the known centres.
        activities: Activities that have staffing rules.

    Returns:
        Valid sessions, rejected rows and warnings. Attendance above capacity
        is kept and flagged with a warning.
    """

    def build(values: dict[str, str], line_number: int) -> tuple[Session, list[str]]:
        session_id = require(values, "session_id")
        centre_code = require_known(values, "centre_code", centre_codes, "centre")
        activity = require_known(values, "activity", activities, "activity")
        session_date = parse_date(require(values, "session_date"), "session date")
        start_time = parse_time(require(values, "start_time"), "start time")
        end_time = parse_time(require(values, "end_time"), "end time")
        check_time_order(start_time, end_time, "Session")
        capacity = parse_whole_number(require(values, "capacity"), "capacity")
        if capacity <= 0:
            raise RowError("Capacity must be greater than 0")
        attendance = parse_whole_number(require(values, "attendance"), "attendance")
        if attendance < 0:
            raise RowError("Attendance cannot be negative")

        warnings = []
        if attendance > capacity:
            warnings.append(
                f"Attendance is above capacity ({attendance} of {capacity})"
            )
        session = Session(
            session_id=session_id,
            centre_code=centre_code,
            activity=activity,
            session_date=session_date,
            start_time=start_time,
            end_time=end_time,
            capacity=capacity,
            attendance=attendance,
            line_number=line_number,
        )
        return session, warnings

    return _validate_rows(
        csv_file, SESSION_COLUMNS, ("session_id",), "session ID", build
    )


def validate_centres(csv_file: CsvFile) -> list[Centre]:
    """Validate ``centres.csv``.

    Values are cleaned silently; reference files produce no warnings.

    Raises:
        InputError: If any row is not valid. Reference data must be correct.
    """

    def build(values: dict[str, str], _line_number: int) -> tuple[Centre, list[str]]:
        centre = Centre(
            centre_code=require(values, "centre_code"),
            centre_name=require(values, "centre_name"),
        )
        return centre, []

    result = _validate_rows(
        csv_file, CENTRE_COLUMNS, ("centre_code",), "centre code", build
    )
    return _reference_records(result)


def validate_staffing_rules(csv_file: CsvFile) -> list[StaffingRule]:
    """Validate ``staffing_rules.csv``.

    Values are cleaned silently; reference files produce no warnings.

    Raises:
        InputError: If any row is not valid. Reference data must be correct.
    """

    def build(
        values: dict[str, str],
        _line_number: int,
    ) -> tuple[StaffingRule, list[str]]:
        activity = require(values, "activity")
        role = require_known(values, "role", KNOWN_ROLES, "role")
        participants_per_staff = parse_whole_number(
            require(values, "participants_per_staff"), "participants per staff"
        )
        if participants_per_staff <= 0:
            raise RowError("Participants per staff must be greater than 0")
        minimum_staff = parse_whole_number(
            require(values, "minimum_staff"), "minimum staff"
        )
        if minimum_staff < 0:
            raise RowError("Minimum staff cannot be negative")
        rule = StaffingRule(
            activity=activity,
            role=role,
            participants_per_staff=participants_per_staff,
            minimum_staff=minimum_staff,
        )
        return rule, []

    result = _validate_rows(
        csv_file,
        STAFFING_RULE_COLUMNS,
        ("activity", "role"),
        "staffing rule",
        build,
    )
    return _reference_records(result)


def require(values: dict[str, str], column: str) -> str:
    """Return a column's value, rejecting the row if it is blank."""
    value = values[column]
    if not value:
        raise RowError(f"Missing {COLUMN_LABELS[column]}")
    return value


def require_known(
    values: dict[str, str],
    column: str,
    known: Collection[str],
    description: str,
) -> str:
    """Return a required column's value, rejecting it if it is not in ``known``.

    Args:
        values: The row's cleaned values by column name.
        column: The column to read.
        known: Accepted values.
        description: Word used in the message, for example ``"centre"``.
    """
    value = require(values, column)
    if value not in known:
        raise RowError(f"Unknown {description} '{value}'")
    return value


def parse_date(text: str, label: str) -> date:
    """Parse a ``DD/MM/YYYY`` or ``YYYY-MM-DD`` date.

    Args:
        text: The cleaned value.
        label: Column name used in the message, for example ``"shift date"``.

    Raises:
        RowError: If the text is not in an accepted format, or names a
            date that does not exist.
    """
    if match := DAY_FIRST_DATE.fullmatch(text):
        day, month, year = (int(part) for part in match.groups())
    elif match := ISO_DATE.fullmatch(text):
        year, month, day = (int(part) for part in match.groups())
    else:
        raise RowError(f"Could not read {label} '{text}'")
    try:
        return date(year, month, day)
    except ValueError:
        raise RowError(f"Date {text} does not exist") from None


def parse_time(text: str, label: str) -> time:
    """Parse a 24-hour ``HH:MM``, ``H:MM`` or ``HH:MM:00`` time.

    Raises:
        RowError: If the text is not an accepted time. ``24:00`` is not
            accepted, because shifts and sessions never cross midnight.
    """
    match = CLOCK_TIME.fullmatch(text)
    if match is None:
        raise RowError(f"Could not read {label} '{text}'")
    hour, minute = (int(part) for part in match.groups())
    if hour > 23 or minute > 59:
        raise RowError(f"Could not read {label} '{text}'")
    return time(hour, minute)


def parse_whole_number(text: str, label: str) -> int:
    """Parse a whole number, which may be negative.

    Raises:
        RowError: If the text is a decimal, not a number at all, or has more
            digits than Python will convert.
    """
    if WHOLE_NUMBER.fullmatch(text):
        try:
            return int(text)
        except ValueError:
            raise RowError(f"{label.capitalize()} is too long to be a number") from None
    if DECIMAL_NUMBER.fullmatch(text):
        raise RowError(f"{label.capitalize()} '{text}' is not a whole number")
    raise RowError(f"{label.capitalize()} '{text}' is not a number")


def check_time_order(start_time: time, end_time: time, subject: str) -> None:
    """Reject a row whose end time is not after its start time.

    Args:
        start_time: When it starts.
        end_time: When it ends.
        subject: ``"Shift"`` or ``"Session"``, used in the message.
    """
    if end_time < start_time:
        raise RowError(f"{subject} ends before it starts")
    if end_time == start_time:
        raise RowError(f"{subject} starts and ends at the same time")


def clean_value(column: str, value: str) -> str:
    """Trim a value and normalise its case according to its column."""
    value = value.strip()
    if column in UPPER_CASE_COLUMNS:
        return value.upper()
    if column in LOWER_CASE_COLUMNS:
        return value.lower()
    return value


def _validate_rows(
    csv_file: CsvFile,
    columns: Sequence[str],
    key_columns: Sequence[str],
    key_description: str,
    build: Callable[[dict[str, str], int], tuple[T, list[str]]],
) -> ValidationResult[T]:
    """Apply the checks shared by every file, then build a record per row.

    In order, each row is checked for a parsing problem from ``ingest`` and
    for its column count, cleaned, checked for a duplicate key, and passed to
    ``build``. The first row with a key claims it, even if that row is later
    rejected. Rows that could not be parsed, rows with the wrong number of
    columns and rows with a blank key claim nothing.

    Args:
        csv_file: The ingested file.
        columns: The file's required columns, in the brief's order.
        key_columns: Columns that together must be unique.
        key_description: Name of the key in messages, for example "shift ID".
        build: Checks the cleaned values and returns the record and any
            warning reasons. Raises ``RowError`` to reject the row.

    Returns:
        Valid records, rejected rows and warnings, in file order.
    """
    position = {name: index for index, name in enumerate(csv_file.header)}
    first_seen: dict[tuple[str, ...], int] = {}
    valid: list[T] = []
    rejected: list[Rejection] = []
    warnings: list[RowWarning] = []

    for row in csv_file.rows:
        try:
            if row.problem is not None:
                raise RowError(row.problem)
            if len(row.fields) != len(csv_file.header):
                message = (
                    f"Expected {len(csv_file.header)} columns, found {len(row.fields)}"
                )
                raise RowError(message)

            raw_values = {name: row.fields[position[name]] for name in columns}
            values = {name: clean_value(name, raw) for name, raw in raw_values.items()}

            key = tuple(values[name] for name in key_columns)
            if all(key):
                if key in first_seen:
                    message = (
                        f"Duplicate {key_description}, "
                        f"first seen on line {first_seen[key]}"
                    )
                    raise RowError(message)
                first_seen[key] = row.line_number

            record, warning_reasons = build(values, row.line_number)
        except RowError as error:
            rejected.append(
                Rejection(csv_file.file_name, row.line_number, row.raw_text, str(error))
            )
            continue

        valid.append(record)
        if values != raw_values:
            warning_reasons.insert(0, CLEANED_REASON)
        warnings.extend(
            RowWarning(csv_file.file_name, row.line_number, row.raw_text, reason)
            for reason in warning_reasons
        )

    return ValidationResult(tuple(valid), tuple(rejected), tuple(warnings))


def _reference_records(result: ValidationResult[T]) -> list[T]:
    """Return a reference file's records, or raise for its first rejected row.

    Raises:
        InputError: Naming the file, line and problem of the first bad row.
    """
    if result.rejected:
        first = result.rejected[0]
        message = f"{first.file_name} line {first.line_number}: {first.reason}"
        raise InputError(message)
    return list(result.valid)
