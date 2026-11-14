"""Database: load validated records into DuckDB and read the analysis views.

The database is kept in memory unless the caller passes in a connection, for
example one backed by a file that the optional dashboard can read. Opening such
a file is left to the command line.

All SQL lives in ``.sql`` files under ``roster_check/sql``. Values always reach
the database as bound parameters, and views are read by name through DuckDB's
relation API, with the name checked against a fixed list. No SQL is built in
Python.
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
    connection: duckdb.DuckDBPyConnection | None = None,
) -> duckdb.DuckDBPyConnection:
    """Load the records and the analysis views into a database.

    Args:
        centres: Known centres.
        rules: Staffing rules.
        shifts: Valid shifts.
        sessions: Valid sessions.
        rejections: Rejected rows from every file.
        connection: An open connection to an empty database to load into,
            for example one backed by a file so other tools can read the same
            tables and views. When ``None``, a new in-memory database is used.

    Returns:
        The connection holding the loaded database. The caller closes it when
        finished.
    """
    if connection is None:
        connection = duckdb.connect(":memory:")
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
    relation = connection.table(view)
    columns = relation.columns
    return [dict(zip(columns, row, strict=True)) for row in relation.fetchall()]
