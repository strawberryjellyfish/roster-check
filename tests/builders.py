"""Builders for the records and databases used by the tests.

Small hand-made records cover single rules; ``run_sample`` runs the bundled
sample data through the pipeline for end-to-end checks.
"""

from collections.abc import Sequence
from datetime import date, time
from importlib.resources import files
from pathlib import Path
from typing import Any

import duckdb

from roster_check.analysis import analyse
from roster_check.db import create_database
from roster_check.ingest import read_csv
from roster_check.models import (
    Centre,
    Rejection,
    ReportData,
    Session,
    Shift,
    StaffingRule,
    ValidationResult,
)
from roster_check.validate import (
    CENTRE_COLUMNS,
    ROSTER_COLUMNS,
    SESSION_COLUMNS,
    STAFFING_RULE_COLUMNS,
    validate_centres,
    validate_sessions,
    validate_shifts,
    validate_staffing_rules,
)

WEDNESDAY = date(2026, 11, 4)

RULES = (
    StaffingRule("swim_lesson", "swim_instructor", 8, 1),
    StaffingRule("swim_lesson", "lifeguard", 30, 1),
    StaffingRule("lap_swim", "lifeguard", 25, 1),
)
CENTRES = (
    Centre("RBC", "Riverbend Central"),
    Centre("NTH", "Northgate"),
)


def make_session(
    session_id: str = "SE-00001",
    *,
    centre_code: str = "RBC",
    activity: str = "swim_lesson",
    session_date: date = WEDNESDAY,
    start: str = "16:00",
    end: str = "16:45",
    capacity: int = 24,
    attendance: int = 8,
) -> Session:
    """Build a valid session; by default a Wednesday swim lesson at Riverbend."""
    return Session(
        session_id=session_id,
        centre_code=centre_code,
        activity=activity,
        session_date=session_date,
        start_time=time.fromisoformat(start),
        end_time=time.fromisoformat(end),
        capacity=capacity,
        attendance=attendance,
        line_number=2,
    )


def make_shift(
    shift_id: str,
    *,
    staff_id: str,
    role: str = "swim_instructor",
    centre_code: str = "RBC",
    shift_date: date = WEDNESDAY,
    start: str = "15:45",
    end: str = "17:45",
    staff_name: str | None = "Jordan Placeholder",
) -> Shift:
    """Build a valid shift; by default one that covers the default session."""
    return Shift(
        shift_id=shift_id,
        centre_code=centre_code,
        staff_id=staff_id,
        staff_name=staff_name,
        role=role,
        shift_date=shift_date,
        start_time=time.fromisoformat(start),
        end_time=time.fromisoformat(end),
        line_number=2,
    )


def lifeguard(shift_id: str = "SH-LG", staff_id: str = "S-LG") -> Shift:
    """Build a lifeguard shift that covers the default session."""
    return make_shift(shift_id, staff_id=staff_id, role="lifeguard")


def build_database(
    sessions: Sequence[Session],
    shifts: Sequence[Shift],
    *,
    rejections: Sequence[Rejection] = (),
) -> duckdb.DuckDBPyConnection:
    """Create a database from the given records and the test rules and centres."""
    return create_database(
        centres=CENTRES,
        rules=RULES,
        shifts=shifts,
        sessions=sessions,
        rejections=rejections,
    )


def run_sample() -> tuple[ReportData, list[ValidationResult[Any]]]:
    """Run the bundled sample data through every stage up to analysis.

    Returns:
        The report figures and the validation results for the roster and
        session files, in that order.
    """
    data = Path(str(files("roster_check").joinpath("data")))
    centres = validate_centres(read_csv(data / "centres.csv", CENTRE_COLUMNS))
    rules = validate_staffing_rules(
        read_csv(data / "staffing_rules.csv", STAFFING_RULE_COLUMNS)
    )
    centre_codes = {centre.centre_code for centre in centres}
    shifts = validate_shifts(
        read_csv(data / "sample" / "rosters.csv", ROSTER_COLUMNS), centre_codes
    )
    sessions = validate_sessions(
        read_csv(data / "sample" / "sessions.csv", SESSION_COLUMNS),
        centre_codes,
        {rule.activity for rule in rules},
    )
    connection = create_database(
        centres=centres,
        rules=rules,
        shifts=shifts.valid,
        sessions=sessions.valid,
        rejections=shifts.rejected + sessions.rejected,
    )
    try:
        return analyse(connection), [shifts, sessions]
    finally:
        connection.close()
