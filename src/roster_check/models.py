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


def percentage(part: int, whole: int) -> float:
    """Return ``part`` as a percentage of ``whole``, or 0 when ``whole`` is 0."""
    return 0.0 if whole == 0 else 100 * part / whole


@dataclass(frozen=True)
class Kpis:
    """The headline numbers at the top of the report."""

    sessions_analysed: int
    understaffed_sessions: int
    staff_hours: float
    total_attendance: int
    rows_rejected: int

    @property
    def understaffed_percent(self) -> float:
        """Understaffed sessions as a percentage of sessions analysed."""
        return percentage(self.understaffed_sessions, self.sessions_analysed)


@dataclass(frozen=True)
class CentreSummary:
    """Understaffing at one centre."""

    centre_code: str
    centre_name: str
    sessions: int
    understaffed_sessions: int

    @property
    def understaffed_percent(self) -> float:
        """Understaffed sessions as a percentage of the centre's sessions."""
        return percentage(self.understaffed_sessions, self.sessions)


@dataclass(frozen=True)
class HeatmapCell:
    """Sessions starting in one hour of one day of the week.

    Attributes:
        weekday: Day of the week, Monday is 0.
        hour: Hour of the day the sessions start, 0 to 23.
        sessions: Sessions starting in this hour.
        understaffed_sessions: How many of them were understaffed.
        shortfall: Total staff missing across them.
    """

    weekday: int
    hour: int
    sessions: int
    understaffed_sessions: int
    shortfall: int


@dataclass(frozen=True)
class DailyTotal:
    """Total attendance and rostered staff hours on one day."""

    day: date
    attendance: int
    staff_hours: float


@dataclass(frozen=True)
class RoleShortfall:
    """Staff required and present in one role for one session."""

    role: str
    required: int
    present: int


@dataclass(frozen=True)
class UnderstaffedSession:
    """An understaffed session, with the roles that were short."""

    session_id: str
    session_date: date
    centre_name: str
    activity: str
    start_time: time
    end_time: time
    attendance: int
    shortfall: int
    roles: tuple[RoleShortfall, ...]


@dataclass(frozen=True)
class ReportData:
    """Every number the report needs, and nothing else.

    Holds no staff names or IDs, so it is safe to pass to the AI summary.

    Attributes:
        period_start: First session date, or ``None`` if there are no sessions.
        period_end: Last session date, or ``None`` if there are no sessions.
        kpis: The headline numbers.
        centres: Understaffing at each centre, ordered by centre code.
        heatmap: Sessions by day of the week and starting hour. Only cells
            with sessions are included.
        daily: Attendance and staff hours for each day, in date order.
        worst_sessions: Up to ten understaffed sessions, worst first.
        staffing_rules: The rules used, for the report footer.
    """

    period_start: date | None
    period_end: date | None
    kpis: Kpis
    centres: tuple[CentreSummary, ...]
    heatmap: tuple[HeatmapCell, ...]
    daily: tuple[DailyTotal, ...]
    worst_sessions: tuple[UnderstaffedSession, ...]
    staffing_rules: tuple[StaffingRule, ...]
