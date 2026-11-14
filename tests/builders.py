"""Builders for small hand-made records used by the database and analysis tests."""

from collections.abc import Sequence
from datetime import date, time

import duckdb

from roster_check.db import create_database
from roster_check.models import Centre, Rejection, Session, Shift, StaffingRule

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
