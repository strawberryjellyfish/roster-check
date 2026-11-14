"""Data structures shared by the stages of the pipeline.

Field names follow the CSV columns in section 4 of the project brief. All
dataclasses are frozen so that a stage can never change data it was given.
"""

from dataclasses import dataclass
from datetime import date, time
from typing import Generic, TypeVar

T = TypeVar("T")


class InputError(Exception):
    """A fatal input problem: the file cannot be used and no report is written.

    The message is a single plain-English line shown to the user as it is.
    """


@dataclass(frozen=True)
class RawRow:
    """One non-blank data line from a CSV file, before validation.

    Attributes:
        line_number: Physical line in the file; the header is line 1.
        raw_text: The line exactly as it appears in the file, without its
            line ending. Shown in the report so users can find the row.
        fields: The line split into fields, in the file's column order.
            Empty if the line could not be parsed.
        problem: Why the line could not be parsed as CSV, or ``None``.
            Validation rejects the row with this reason.
    """

    line_number: int
    raw_text: str
    fields: tuple[str, ...]
    problem: str | None = None


@dataclass(frozen=True)
class CsvFile:
    """A CSV file that has passed the file-level checks in ``ingest``.

    Attributes:
        file_name: The file's name, used in messages.
        header: Column names in file order, trimmed and lower-cased.
        rows: Every non-blank data line.
        blank_lines: Number of blank lines skipped.
        ignored_columns: Columns present in the file but not used.
        used_fallback_encoding: True if the file was not valid UTF-8 and was
            read as Windows-1252 instead.
    """

    file_name: str
    header: tuple[str, ...]
    rows: tuple[RawRow, ...]
    blank_lines: int
    ignored_columns: tuple[str, ...]
    used_fallback_encoding: bool


@dataclass(frozen=True)
class Shift:
    """A validated row from ``rosters.csv``."""

    shift_id: str
    centre_code: str
    staff_id: str
    staff_name: str | None
    role: str
    shift_date: date
    start_time: time
    end_time: time
    line_number: int


@dataclass(frozen=True)
class Session:
    """A validated row from ``sessions.csv``."""

    session_id: str
    centre_code: str
    activity: str
    session_date: date
    start_time: time
    end_time: time
    capacity: int
    attendance: int
    line_number: int


@dataclass(frozen=True)
class StaffingRule:
    """How many staff of one role an activity needs."""

    activity: str
    role: str
    participants_per_staff: int
    minimum_staff: int


@dataclass(frozen=True)
class Centre:
    """A known centre."""

    centre_code: str
    centre_name: str


@dataclass(frozen=True)
class Rejection:
    """A row that could not be used, with the reason shown to the user."""

    file_name: str
    line_number: int
    raw_text: str
    reason: str


@dataclass(frozen=True)
class RowWarning:
    """A row that was used but changed or flagged, with the reason."""

    file_name: str
    line_number: int
    raw_text: str
    reason: str


@dataclass(frozen=True)
class ValidationResult(Generic[T]):
    """The outcome of validating every row of one file.

    Attributes:
        valid: Records built from the rows that passed.
        rejected: Rows that could not be used.
        warnings: Rows that were used but cleaned or flagged.
    """

    valid: tuple[T, ...]
    rejected: tuple[Rejection, ...]
    warnings: tuple[RowWarning, ...]
