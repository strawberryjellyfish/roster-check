"""Known-answer tests for the understaffing SQL (section 4.6 of the brief).

Each test builds a tiny database by hand where the right answer is obvious.
"""

from datetime import date

import duckdb
from builders import build_database, lifeguard, make_session, make_shift

from roster_check.db import fetch_view


def roles_for(
    connection: duckdb.DuckDBPyConnection,
    session_id: str = "SE-00001",
) -> dict[str, tuple[int, int, int]]:
    """Return ``(required, present, shortfall)`` by role for one session."""
    return {
        row["role"]: (row["required"], row["present"], row["shortfall"])
        for row in fetch_view(connection, "role_shortfall")
        if row["session_id"] == session_id
    }


def session_shortfall(
    connection: duckdb.DuckDBPyConnection,
    session_id: str = "SE-00001",
) -> int:
    """Return the total shortfall for one session."""
    rows = fetch_view(connection, "session_shortfall")
    return next(row["shortfall"] for row in rows if row["session_id"] == session_id)


def test_eight_swimmers_and_one_instructor_is_not_understaffed() -> None:
    connection = build_database(
        [make_session(attendance=8)],
        [make_shift("SH-1", staff_id="S-1"), lifeguard()],
    )

    assert roles_for(connection)["swim_instructor"] == (1, 1, 0)
    assert session_shortfall(connection) == 0


def test_nine_swimmers_and_one_instructor_is_short_by_one() -> None:
    connection = build_database(
        [make_session(attendance=9)],
        [make_shift("SH-1", staff_id="S-1"), lifeguard()],
    )

    assert roles_for(connection)["swim_instructor"] == (2, 1, 1)
    assert session_shortfall(connection) == 1


def test_zero_attendance_still_needs_the_minimum_staff() -> None:
    connection = build_database([make_session(attendance=0)], [])

    assert roles_for(connection) == {
        "swim_instructor": (1, 0, 1),
        "lifeguard": (1, 0, 1),
    }
    assert session_shortfall(connection) == 2


def test_shortfall_is_summed_across_roles() -> None:
    connection = build_database([make_session(attendance=20)], [])

    assert roles_for(connection)["swim_instructor"] == (3, 0, 3)
    assert session_shortfall(connection) == 4


def test_shift_matching_the_session_exactly_counts() -> None:
    shift = make_shift("SH-1", staff_id="S-1", start="16:00", end="16:45")
    connection = build_database([make_session()], [shift, lifeguard()])

    assert roles_for(connection)["swim_instructor"] == (1, 1, 0)


def test_shift_that_only_partly_overlaps_does_not_count() -> None:
    shift = make_shift("SH-1", staff_id="S-1", start="15:45", end="16:30")
    connection = build_database([make_session()], [shift, lifeguard()])

    assert roles_for(connection)["swim_instructor"] == (1, 0, 1)


def test_shift_at_another_centre_does_not_count() -> None:
    shift = make_shift("SH-1", staff_id="S-1", centre_code="NTH")
    connection = build_database([make_session()], [shift, lifeguard()])

    assert roles_for(connection)["swim_instructor"] == (1, 0, 1)


def test_shift_on_another_date_does_not_count() -> None:
    shift = make_shift("SH-1", staff_id="S-1", shift_date=date(2026, 11, 5))
    connection = build_database([make_session()], [shift, lifeguard()])

    assert roles_for(connection)["swim_instructor"] == (1, 0, 1)


def test_shift_in_another_role_does_not_count() -> None:
    connection = build_database([make_session()], [lifeguard()])

    assert roles_for(connection)["swim_instructor"] == (1, 0, 1)
    assert roles_for(connection)["lifeguard"] == (1, 1, 0)


def test_split_shifts_that_only_cover_the_session_together_do_not_count() -> None:
    shifts = [
        make_shift("SH-1", staff_id="S-1", start="15:45", end="16:20"),
        make_shift("SH-2", staff_id="S-1", start="16:20", end="17:00"),
        lifeguard(),
    ]
    connection = build_database([make_session()], shifts)

    assert roles_for(connection)["swim_instructor"] == (1, 0, 1)


def test_one_person_with_overlapping_shifts_counts_once() -> None:
    shifts = [
        make_shift("SH-1", staff_id="S-1"),
        make_shift("SH-2", staff_id="S-1", start="16:00", end="17:00"),
        lifeguard(),
    ]
    connection = build_database([make_session(attendance=9)], shifts)

    assert roles_for(connection)["swim_instructor"] == (2, 1, 1)


def test_concurrent_sessions_can_share_a_staff_member() -> None:
    sessions = [
        make_session("SE-00001", activity="swim_lesson"),
        make_session("SE-00002", activity="lap_swim", attendance=10),
    ]
    connection = build_database(
        sessions, [make_shift("SH-1", staff_id="S-1"), lifeguard()]
    )

    assert roles_for(connection, "SE-00001")["lifeguard"] == (1, 1, 0)
    assert roles_for(connection, "SE-00002")["lifeguard"] == (1, 1, 0)


def test_lap_swim_needs_a_lifeguard_per_twenty_five() -> None:
    connection = build_database(
        [make_session(activity="lap_swim", attendance=26)],
        [lifeguard()],
    )

    assert roles_for(connection) == {"lifeguard": (2, 1, 1)}
