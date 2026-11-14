"""Database: load validated records into DuckDB and read the analysis views.

All SQL lives in ``.sql`` files under ``roster_check/sql``. Values always reach
the database as bound parameters; the only SQL built in Python selects from a
view whose name is checked against a fixed list.
"""

from collections.abc import Sequence
from dataclasses import astuple
from importlib.resources import files
from typing import Any, TypeAlias

import duckdb

from roster_check.models import Centre, Rejection, Session, Shift, StaffingRule

TABLES_FILE = "00_tables.sql"
VIEW_FILES = (
    "01_required_staff.sql",
    "02_staff_on_session.sql",
    "03_understaffed.sql",
    "04_kpis.sql",
)
VIEW_NAMES = frozenset(
    {
        "required_staff",
        "staff_present",
        "role_shortfall",
        "session_shortfall",
        "report_kpis",
        "report_centres",
        "report_heatmap",
        "report_daily",
        "report_worst_sessions",
        "report_worst_roles",
        "report_rules",
    }
)

Record: TypeAlias = Centre | StaffingRule | Shift | Session | Rejection


def create_database(
    *,
    centres: Sequence[Centre],
    rules: Sequence[StaffingRule],
    shifts: Sequence[Shift],
    sessions: Sequence[Session],
    rejections: Sequence[Rejection],
) -> duckdb.DuckDBPyConnection:
    """Create an in-memory database holding the records and the analysis views.

    Args:
        centres: Known centres.
        rules: Staffing rules.
        shifts: Valid shifts.
        sessions: Valid sessions.
        rejections: Rejected rows from every file.

    Returns:
        An open connection. The caller closes it when finished.
    """
    connection = duckdb.connect()
    run_sql_file(connection, TABLES_FILE)
    load_records(connection, "load_centres.sql", centres)
    load_records(connection, "load_rules.sql", rules)
    load_records(connection, "load_shifts.sql", shifts)
    load_records(connection, "load_sessions.sql", sessions)
    load_records(connection, "load_rejections.sql", rejections)
    for name in VIEW_FILES:
        run_sql_file(connection, name)
    return connection


def read_sql(name: str) -> str:
    """Return the text of a packaged SQL file."""
    return files("roster_check").joinpath("sql", name).read_text(encoding="utf-8")


def run_sql_file(connection: duckdb.DuckDBPyConnection, name: str) -> None:
    """Run every statement in a packaged SQL file."""
    connection.execute(read_sql(name))


def load_records(
    connection: duckdb.DuckDBPyConnection,
    name: str,
    records: Sequence[Record],
) -> None:
    """Insert records using the parameterised statement in a packaged SQL file.

    Each record's fields are bound in dataclass field order, which matches the
    column order in ``00_tables.sql``.
    """
    if records:
        connection.executemany(read_sql(name), [astuple(record) for record in records])


def fetch_view(
    connection: duckdb.DuckDBPyConnection, view: str
) -> list[dict[str, Any]]:
    """Return every row of an analysis view as a dictionary keyed by column.

    Raises:
        ValueError: If ``view`` is not one of ``VIEW_NAMES``.
    """
    if view not in VIEW_NAMES:
        message = f"Unknown view '{view}'"
        raise ValueError(message)
    # Safe: the name has been checked against a fixed list of views.
    cursor = connection.execute(f"SELECT * FROM {view}")  # noqa: S608
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
