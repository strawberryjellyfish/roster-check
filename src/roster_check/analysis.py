"""Analysis: read the analysis views and gather the results into ``ReportData``.

The calculations themselves are in the SQL files; this module only converts
view rows into the dataclasses the report and the AI summary use.
"""

import duckdb

from roster_check.db import fetch_view
from roster_check.models import (
    CentreSummary,
    DailyTotal,
    HeatmapCell,
    Kpis,
    ReportData,
    RoleShortfall,
    StaffingRule,
    UnderstaffedSession,
)


def analyse(connection: duckdb.DuckDBPyConnection) -> ReportData:
    """Collect every figure the report needs from a loaded database.

    Args:
        connection: A database created by ``db.create_database``.

    Returns:
        The report figures. Contains no staff names or IDs.
    """
    kpi_row = fetch_view(connection, "report_kpis")[0]
    return ReportData(
        period_start=kpi_row["period_start"],
        period_end=kpi_row["period_end"],
        kpis=Kpis(
            sessions_analysed=kpi_row["sessions_analysed"],
            understaffed_sessions=kpi_row["understaffed_sessions"],
            staff_hours=kpi_row["staff_hours"],
            total_attendance=kpi_row["total_attendance"],
            rows_rejected=kpi_row["rows_rejected"],
        ),
        centres=tuple(
            CentreSummary(**row) for row in fetch_view(connection, "report_centres")
        ),
        heatmap=tuple(
            HeatmapCell(**row) for row in fetch_view(connection, "report_heatmap")
        ),
        daily=tuple(
            DailyTotal(**row) for row in fetch_view(connection, "report_daily")
        ),
        worst_sessions=_worst_sessions(connection),
        staffing_rules=tuple(
            StaffingRule(**row) for row in fetch_view(connection, "report_rules")
        ),
    )


def _worst_sessions(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[UnderstaffedSession, ...]:
    """Return the worst understaffed sessions, each with its short roles."""
    roles: dict[str, list[RoleShortfall]] = {}
    for row in fetch_view(connection, "report_worst_roles"):
        session_id = row.pop("session_id")
        roles.setdefault(session_id, []).append(RoleShortfall(**row))

    return tuple(
        UnderstaffedSession(**row, roles=tuple(roles.get(row["session_id"], [])))
        for row in fetch_view(connection, "report_worst_sessions")
    )
