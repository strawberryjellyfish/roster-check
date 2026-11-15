"""Summarise: ask Claude for a short plain-English summary of the report figures.

Optional, used only with ``--summarise``. The prompt is built from
``ReportData`` alone: counts, centre names, activities, days and times, never
staff names or IDs. Any failure means "no summary", so this module never
raises and never prints. The API key is read from ``ANTHROPIC_API_KEY`` only,
and the ``anthropic`` package is imported only when a summary is requested.
"""

import importlib.util
import os
from collections.abc import Mapping
from typing import Any

from roster_check.charts import format_number
from roster_check.models import HeatmapCell, ReportData
from roster_check.report import (
    WEEKDAY_PLURALS,
    activity_label,
    format_date,
    format_period,
    percent_text,
    shortfall_text,
)

API_KEY_VARIABLE = "ANTHROPIC_API_KEY"
MODEL_VARIABLE = "ROSTER_CHECK_MODEL"
DEFAULT_MODEL = "claude-opus-5-5"

# A short factual summary needs little reasoning, so effort is kept low.
EFFORT = "low"
MAX_TOKENS = 16000
TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 1

# Server-side refusal fallback, sent only with the default model because a
# custom model may not support it.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

TOP_GAPS = 5
TOP_SESSIONS = 5

NO_API_KEY = "Skipping AI summary: no API key set"
NO_PACKAGE = (
    "Skipping AI summary: the anthropic package is not installed "
    "(install roster-check[ai])"
)

SYSTEM_PROMPT = (
    "You summarise a staffing report for the managers of a community "
    "recreation organisation. Write 3 to 5 plain sentences in Australian "
    "English. Use only the figures given; do not invent numbers, causes or "
    "advice. Cover the share of understaffed sessions, the most affected "
    "centre, when the largest gaps happened, and any rows that could not be "
    "used. No headings, lists, markdown or emojis."
)


def skip_reason(environ: Mapping[str, str] = os.environ) -> str | None:
    """Return why a summary cannot be requested, or ``None`` if it can.

    Args:
        environ: Environment variables to read the API key from.

    Returns:
        A one-line message for the terminal, or ``None`` when an API key is set
        and the ``anthropic`` package is installed.
    """
    if not environ.get(API_KEY_VARIABLE):
        return NO_API_KEY
    if importlib.util.find_spec("anthropic") is None:
        return NO_PACKAGE
    return None


def build_prompt(report: ReportData) -> str:
    """Write the user message: the report figures as labelled plain text.

    Only aggregated figures are included. Session IDs are left out as well as
    staff details, so nothing in the prompt identifies a person or a record.
    """
    kpis = report.kpis
    if report.period_start is None or report.period_end is None:
        period = "no sessions in the data"
    else:
        period = format_period(report.period_start, report.period_end)

    lines = [
        f"Staffing figures, {period}:",
        f"Sessions analysed: {format_number(kpis.sessions_analysed)}",
        f"Understaffed sessions: {format_number(kpis.understaffed_sessions)} "
        f"({percent_text(kpis.understaffed_percent)})",
        f"Staff hours rostered: {format_number(kpis.staff_hours)}",
        f"Total attendance: {format_number(kpis.total_attendance)}",
        f"Rows that could not be used: {format_number(kpis.rows_rejected)}",
        "",
        "Understaffing by centre:",
        *(
            f"- {centre.centre_name}: {centre.understaffed_sessions} of "
            f"{centre.sessions} sessions"
            for centre in report.centres
        ),
        "",
        "Largest gaps (day, starting hour, combined shortfall):",
        *(
            f"- {WEEKDAY_PLURALS[cell.weekday]} {cell.hour:02d}:00: "
            f"{cell.shortfall} staff"
            for cell in _largest_gaps(report)
        ),
        "",
        "Worst sessions (centre, activity, date, time, need):",
        *(
            f"- {session.centre_name}, {activity_label(session.activity)}, "
            f"{format_date(session.session_date)}, "
            f"{session.start_time:%H:%M}-{session.end_time:%H:%M}, "
            f"{shortfall_text(session).lower()}"
            for session in report.worst_sessions[:TOP_SESSIONS]
        ),
    ]
    return "\n".join(lines)


def summarise(
    report: ReportData,
    *,
    client: Any | None = None,
    environ: Mapping[str, str] = os.environ,
) -> str | None:
    """Ask Claude for a 3 to 5 sentence summary of the report figures.

    Args:
        report: The figures from ``analysis.analyse``.
        client: An Anthropic client to use. Tests pass a fake; when ``None``,
            a client is created with the key from ``ANTHROPIC_API_KEY``.
        environ: Environment variables to read the key and model from.

    Returns:
        The summary text, or ``None`` if it could not be produced for any
        reason, including a refusal or a response cut short.
    """
    # Any failure, from a missing key to a network error, means no summary.
    try:
        if client is None:
            client = _create_client(environ[API_KEY_VARIABLE])
        model = environ.get(MODEL_VARIABLE) or DEFAULT_MODEL
        response = client.beta.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_prompt(report)}],
            output_config={"effort": EFFORT},
            **_fallback_options(model),
        )
        return _summary_text(response)
    except Exception:
        return None


def _largest_gaps(report: ReportData) -> list[HeatmapCell]:
    """Return the heatmap cells with the largest shortfall, largest first.

    Ties go to the earlier day and hour, as in the rule-based summary.
    """
    cells = [cell for cell in report.heatmap if cell.shortfall > 0]
    cells.sort(key=lambda cell: (-cell.shortfall, cell.weekday, cell.hour))
    return cells[:TOP_GAPS]


def _create_client(api_key: str) -> Any:
    """Create an Anthropic client with a short timeout and few retries."""
    # Imported here because the package is an optional extra.
    import anthropic

    return anthropic.Anthropic(
        api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES
    )


def _fallback_options(model: str) -> dict[str, Any]:
    """Return the refusal fallback options for the default model, else none."""
    if model != DEFAULT_MODEL:
        return {}
    return {"betas": [FALLBACK_BETA], "fallbacks": "default"}


def _summary_text(response: Any) -> str | None:
    """Return the text of a response that finished normally, or ``None``.

    Only a response that ended on its own is used: a refusal or one cut off
    at the token limit gives no summary.
    """
    if response.stop_reason != "end_turn":
        return None
    text = " ".join(
        block.text.strip() for block in response.content if block.type == "text"
    )
    return text.strip() or None
