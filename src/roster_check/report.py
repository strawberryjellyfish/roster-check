"""Report: render the analysis results as one self-contained HTML page.

The template, stylesheet and script are packaged files, inlined into the page
so it makes no external requests. Jinja2 escapes every value; only the SVG
produced by ``charts`` is marked safe. Writing the page to disk is left to the
command line.
"""

from collections.abc import Sequence
from datetime import date, datetime
from importlib.resources import files
from typing import Any

from jinja2 import Environment, FunctionLoader, StrictUndefined
from markupsafe import Markup

from roster_check.charts import (
    WEEKDAY_NAMES,
    centre_bar_chart,
    daily_chart,
    format_day,
    format_number,
    heatmap,
    shortfall_bar,
)
from roster_check.models import (
    CentreSummary,
    HeatmapCell,
    Rejection,
    ReportData,
    RowWarning,
    UnderstaffedSession,
    ValidationResult,
)

ORGANISATION_NAME = "Riverbend Community Recreation"
TEMPLATE_FILE = "report.html.j2"

WEEKDAY_PLURALS = (
    "Mondays",
    "Tuesdays",
    "Wednesdays",
    "Thursdays",
    "Fridays",
    "Saturdays",
    "Sundays",
)

# Singular and plural wording for each role, used in "Needs 3 swim
# instructors, had 1". Covers every role in section 4.1 of the brief.
ROLE_LABELS = {
    "lifeguard": ("lifeguard", "lifeguards"),
    "swim_instructor": ("swim instructor", "swim instructors"),
    "gym_supervisor": ("gym supervisor", "gym supervisors"),
    "group_fitness": ("group fitness instructor", "group fitness instructors"),
    "front_desk": ("front desk staff member", "front desk staff"),
}


def render_report(
    report: ReportData,
    data_files: Sequence[ValidationResult[Any]],
    *,
    generated_at: datetime,
    version: str,
    sample_data: bool,
    ai_summary: str | None = None,
    ai_summary_unavailable: bool = False,
) -> str:
    """Render the full HTML report.

    Args:
        report: The figures from ``analysis.analyse``.
        data_files: The validation result for each data file, in the order
            their problems should be listed.
        generated_at: When the report was made, shown in the header.
        version: The tool version, shown in the footer.
        sample_data: True when the bundled sample data was used, which adds
            a note that all data in the report is fictional.
        ai_summary: Claude's summary, shown labelled as AI-generated in place
            of the rule-based summary. ``None`` shows the rule-based summary.
        ai_summary_unavailable: True when an AI summary was asked for but not
            produced, which adds a note under the rule-based summary.

    Returns:
        The complete HTML page.
    """
    environment = Environment(
        loader=FunctionLoader(_load_template),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template(TEMPLATE_FILE)
    return template.render(
        organisation=ORGANISATION_NAME,
        period=_period_text(report),
        generated=f"{format_date(generated_at.date())} at {generated_at:%H:%M}",
        version=version,
        sample_data=sample_data,
        badge=badge_text(report.kpis.rows_rejected),
        all_rows_used=report.kpis.rows_rejected == 0,
        kpis=_kpi_tiles(report),
        summary=rule_based_summary(report),
        ai_summary=ai_summary,
        ai_summary_unavailable=ai_summary_unavailable,
        centre_chart=_chart(centre_bar_chart(report.centres)),
        heatmap_chart=_chart(heatmap(report.heatmap)),
        daily_chart=_chart(daily_chart(report.daily)),
        centres=[_centre_row(centre) for centre in report.centres],
        heatmap_cells=[_heatmap_row(cell) for cell in report.heatmap],
        daily=[
            (
                format_day(total.day),
                format_number(total.attendance),
                format_number(total.staff_hours),
            )
            for total in report.daily
        ],
        worst_sessions=_worst_session_rows(report.worst_sessions),
        problem_files=_problem_files(data_files),
        empty_files=_empty_file_names(data_files),
        staffing_rules=[
            (
                activity_label(rule.activity),
                _role_label(rule.role, 1).capitalize(),
                rule.participants_per_staff,
                rule.minimum_staff,
            )
            for rule in report.staffing_rules
        ],
    )


def format_date(day: date) -> str:
    """Return a date with the year, for example ``Mon 2 Nov 2026``."""
    return f"{format_day(day)} {day.year}"


def format_period(start: date, end: date) -> str:
    """Return a date range, giving the year once when both dates share it.

    For example ``Mon 2 Nov to Sun 15 Nov 2026``.
    """
    if start == end:
        return format_date(start)
    if start.year == end.year:
        return f"{format_day(start)} to {format_date(end)}"
    return f"{format_date(start)} to {format_date(end)}"


def badge_text(rows_rejected: int) -> str:
    """Return the data-quality badge wording for the report header."""
    if rows_rejected == 0:
        return "All rows used"
    if rows_rejected == 1:
        return "1 row needs attention"
    return f"{rows_rejected} rows need attention"


def rule_based_summary(report: ReportData) -> list[str]:
    """Write a short plain-English summary of the figures, one sentence each.

    The sentences cover the share of understaffed sessions, the centre with
    the highest share, the day and hour with the largest total shortfall, and
    the rows that could not be used. Sentences that would say nothing useful
    are left out.

    Args:
        report: The figures from ``analysis.analyse``.

    Returns:
        Between one and four sentences.
    """
    kpis = report.kpis
    period = _period_text(report)
    if kpis.sessions_analysed == 0 or period is None:
        return ["No sessions could be analysed.", _rows_sentence(kpis.rows_rejected)]

    if kpis.understaffed_sessions == 0:
        sessions = (
            "the 1 session was"
            if kpis.sessions_analysed == 1
            else f"all {kpis.sessions_analysed} sessions were"
        )
        return [
            f"From {period}, {sessions} fully staffed.",
            _rows_sentence(kpis.rows_rejected),
        ]

    sentences = [
        f"From {period}, {kpis.understaffed_sessions} of {kpis.sessions_analysed} "
        f"sessions ({percent_text(kpis.understaffed_percent)}) "
        f"{'was' if kpis.understaffed_sessions == 1 else 'were'} understaffed."
    ]
    centre = _worst_centre(report.centres)
    sentences.append(
        f"{centre.centre_name} had the highest share, with "
        f"{centre.understaffed_sessions} of its {centre.sessions} sessions short "
        "of staff."
    )
    gap = _largest_gap(report.heatmap)
    if gap is not None:
        sentences.append(
            f"The largest gap was on {WEEKDAY_PLURALS[gap.weekday]} at "
            f"{gap.hour:02d}:00, with a combined shortfall of {_staff(gap.shortfall)}."
        )
    sentences.append(_rows_sentence(kpis.rows_rejected))
    return sentences


def percent_text(percent: float) -> str:
    """Return a percentage rounded to a whole number for reading.

    A share above zero that would round to 0 is shown as "less than 1%", so a
    real problem never reads as none.
    """
    if 0 < percent <= 0.5:
        return "less than 1%"
    return f"{percent:.0f}%"


def shortfall_text(session: UnderstaffedSession) -> str:
    """Describe a session's shortfall, for example "Needs 3 swim instructors, had 1".

    Each short role gets its own clause, separated by semicolons.
    """
    return "; ".join(
        f"Needs {role.required} {_role_label(role.role, role.required)}, "
        f"had {role.present}"
        for role in session.roles
    )


def activity_label(activity: str) -> str:
    """Return an activity code as words, for example "Swim lesson"."""
    return activity.replace("_", " ").capitalize()


def _load_template(name: str) -> str:
    """Return the text of a packaged template file."""
    return files("roster_check").joinpath("templates", name).read_text(encoding="utf-8")


def _chart(svg: str) -> Markup:
    """Mark SVG from ``charts`` as safe to insert without escaping.

    This is the only place the report marks content safe. ``charts`` escapes
    every piece of text it writes into the SVG.
    """
    # Safe: charts.py escapes all text it embeds, and nothing else reaches here.
    return Markup(svg)  # noqa: S704


def _period_text(report: ReportData) -> str | None:
    """Return the period the report covers, or ``None`` with no sessions."""
    if report.period_start is None or report.period_end is None:
        return None
    return format_period(report.period_start, report.period_end)


def _kpi_tiles(report: ReportData) -> list[dict[str, Any]]:
    """Return the headline number tiles in display order.

    Each tile has a label, the raw value and its decimal places for the
    count-up animation, the formatted text, and an optional detail line.
    """
    kpis = report.kpis
    return [
        _tile("Sessions analysed", kpis.sessions_analysed),
        _tile(
            "Understaffed sessions",
            kpis.understaffed_sessions,
            detail=f"{percent_text(kpis.understaffed_percent)} of sessions",
        ),
        _tile("Staff hours rostered", kpis.staff_hours, decimals=1),
        _tile("Total attendance", kpis.total_attendance),
        _tile("Rows rejected", kpis.rows_rejected),
    ]


def _tile(
    label: str, value: float, *, decimals: int = 0, detail: str | None = None
) -> dict[str, Any]:
    """Return one headline number tile."""
    return {
        "label": label,
        "value": value,
        "decimals": decimals,
        "text": format_number(value),
        "detail": detail,
    }


def _centre_row(centre: CentreSummary) -> tuple[str, int, int, str]:
    """Return one row of the centre chart's data table."""
    return (
        centre.centre_name,
        centre.sessions,
        centre.understaffed_sessions,
        percent_text(centre.understaffed_percent),
    )


def _heatmap_row(cell: HeatmapCell) -> tuple[str, str, int, int, int]:
    """Return one row of the heatmap's data table."""
    return (
        WEEKDAY_NAMES[cell.weekday],
        f"{cell.hour:02d}:00",
        cell.sessions,
        cell.understaffed_sessions,
        cell.shortfall,
    )


def _worst_session_rows(
    sessions: Sequence[UnderstaffedSession],
) -> list[dict[str, Any]]:
    """Return the rows of the worst understaffed sessions table."""
    largest = max((session.shortfall for session in sessions), default=0)
    return [
        {
            "date": format_day(session.session_date),
            "centre": session.centre_name,
            "activity": activity_label(session.activity),
            "time": f"{session.start_time:%H:%M} to {session.end_time:%H:%M}",
            "attendance": format_number(session.attendance),
            "shortfall": shortfall_text(session),
            "bar": _chart(shortfall_bar(session.shortfall, largest)),
        }
        for session in sessions
    ]


def _problem_files(
    data_files: Sequence[ValidationResult[Any]],
) -> list[dict[str, Any]]:
    """Group rejected, auto-fixed and flagged rows by file, leaving out clean files.

    Returns:
        One entry per file with problems, each with its name, its rejected
        rows and its warnings, both in line order.
    """
    groups = []
    for result in data_files:
        rows: Sequence[Rejection | RowWarning] = result.rejected + result.warnings
        if not rows:
            continue
        groups.append(
            {
                "name": rows[0].file_name,
                "rejected": sorted(result.rejected, key=_line_number),
                "warnings": sorted(result.warnings, key=_line_number),
            }
        )
    return groups


def _empty_file_names(data_files: Sequence[ValidationResult[Any]]) -> list[str]:
    """Return the names of files in which every row was rejected (case 18)."""
    return [
        result.rejected[0].file_name
        for result in data_files
        if result.rejected and not result.valid
    ]


def _line_number(row: Rejection | RowWarning) -> int:
    """Return a row's line number, for sorting."""
    return row.line_number


def _worst_centre(centres: Sequence[CentreSummary]) -> CentreSummary:
    """Return the centre with the highest understaffed share.

    Ties go to the higher count, then to the earlier centre in report order.
    """
    return max(
        centres,
        key=lambda centre: (centre.understaffed_percent, centre.understaffed_sessions),
    )


def _largest_gap(cells: Sequence[HeatmapCell]) -> HeatmapCell | None:
    """Return the heatmap cell with the largest shortfall, or ``None`` if none.

    Ties go to the earlier day, then the earlier hour.
    """
    short = [cell for cell in cells if cell.shortfall > 0]
    if not short:
        return None
    return max(short, key=lambda cell: (cell.shortfall, -cell.weekday, -cell.hour))


def _rows_sentence(rows_rejected: int) -> str:
    """Return the summary sentence about rows that could not be used."""
    if rows_rejected == 0:
        return "Every row in the input files was used."
    if rows_rejected == 1:
        return "1 row could not be used and is listed under Data problems."
    return f"{rows_rejected} rows could not be used and are listed under Data problems."


def _role_label(role: str, count: int) -> str:
    """Return the singular or plural wording for a role."""
    singular, plural = ROLE_LABELS[role]
    return singular if count == 1 else plural


def _staff(count: int) -> str:
    """Return a number of staff in words, for example "1 staff member"."""
    return "1 staff member" if count == 1 else f"{count} staff"
