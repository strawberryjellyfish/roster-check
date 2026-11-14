"""Tests for loading records into DuckDB and reading the analysis views."""

from importlib.resources import files
from pathlib import Path

import duckdb
import pytest
from builders import (
    CENTRES,
    RULES,
    build_database,
    lifeguard,
    make_session,
    make_shift,
)

from roster_check.db import VIEW_FILES, VIEW_NAMES, create_database, fetch_view
from roster_check.models import Rejection

TABLES = frozenset({"centres", "rules", "shifts", "sessions", "rejections"})


def count_rows(connection: duckdb.DuckDBPyConnection, table: str) -> int:
    """Return the number of rows in one of the fixed tables."""
    assert table in TABLES
    # Safe: the table name has been checked against a fixed list.
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608


def test_records_are_loaded_into_their_tables() -> None:
    rejection = Rejection("rosters.csv", 5, "bad,row", "Expected 8 columns, found 2")
    connection = build_database(
        [make_session()],
        [make_shift("SH-1", staff_id="S-1"), lifeguard()],
        rejections=[rejection],
    )

    assert count_rows(connection, "centres") == 2
    assert count_rows(connection, "rules") == 3
    assert count_rows(connection, "shifts") == 2
    assert count_rows(connection, "sessions") == 1
    assert count_rows(connection, "rejections") == 1


def test_missing_staff_name_is_stored_as_null() -> None:
    connection = build_database(
        [], [make_shift("SH-1", staff_id="S-1", staff_name=None)]
    )

    assert connection.execute("SELECT staff_name FROM shifts").fetchone() == (None,)


def test_values_are_stored_as_given_not_interpreted_as_sql() -> None:
    name = "Robert'); DROP TABLE shifts; --"
    connection = build_database(
        [], [make_shift("SH-1", staff_id="S-1", staff_name=name)]
    )

    assert connection.execute("SELECT staff_name FROM shifts").fetchone() == (name,)


def test_empty_database_still_creates_every_view() -> None:
    connection = build_database([], [])

    for view in VIEW_NAMES:
        assert isinstance(fetch_view(connection, view), list)


@pytest.mark.parametrize("view", ["shifts", "report_kpis; DROP TABLE shifts", ""])
def test_fetch_view_refuses_names_outside_the_fixed_list(view: str) -> None:
    connection = build_database([], [])

    with pytest.raises(ValueError, match="Unknown view"):
        fetch_view(connection, view)


def test_fetch_view_returns_rows_keyed_by_column() -> None:
    connection = build_database([make_session(attendance=9)], [])

    rows = fetch_view(connection, "required_staff")

    assert {row["role"]: row["required"] for row in rows} == {
        "swim_instructor": 2,
        "lifeguard": 1,
    }


@pytest.mark.parametrize(
    "name",
    [
        "00_tables.sql",
        *VIEW_FILES,
        "load_centres.sql",
        "load_rules.sql",
        "load_shifts.sql",
        "load_sessions.sql",
        "load_rejections.sql",
    ],
)
def test_sql_files_are_bundled_in_the_package(name: str) -> None:
    assert files("roster_check").joinpath("sql", name).is_file()


def test_given_connection_is_loaded_and_returned(tmp_path: Path) -> None:
    database_file = tmp_path / "roster_check.duckdb"
    file_connection = duckdb.connect(str(database_file))

    connection = create_database(
        centres=CENTRES,
        rules=RULES,
        shifts=[lifeguard()],
        sessions=[make_session()],
        rejections=[],
        connection=file_connection,
    )
    connection.close()

    assert connection is file_connection

    # Reopening the closed file proves the tables and views were saved in it.
    with duckdb.connect(str(database_file), read_only=True) as reopened:
        for view in VIEW_NAMES:
            assert isinstance(fetch_view(reopened, view), list)
        assert count_rows(reopened, "shifts") == 1
        assert count_rows(reopened, "sessions") == 1
