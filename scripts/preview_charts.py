"""Write an HTML page showing every chart drawn from the bundled sample data.

A development aid for checking the charts by eye before the full report
exists. The page uses simple placeholder styles; the report's own stylesheet
replaces them in milestone M5.

Usage:
    uv run python scripts/preview_charts.py [--out FILE]
"""

import argparse
from importlib.resources import files
from pathlib import Path

from roster_check.analysis import analyse
from roster_check.charts import (
    centre_bar_chart,
    daily_chart,
    format_day,
    heatmap,
    shortfall_bar,
)
from roster_check.db import create_database
from roster_check.ingest import read_csv
from roster_check.models import ReportData
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

DEFAULT_OUT_FILE = Path("chart-preview.html")

PLACEHOLDER_STYLES = """
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 720px;
       color: #1f2933; background: #fff; }
.chart { width: 100%; height: auto; display: block; margin-bottom: 2rem; }
.chart text { font-size: 12px; fill: currentColor; }
.chart .title { font-weight: 600; }
.bar { fill: #2f6fb0; transform-box: fill-box; transform-origin: left;
       animation: grow 0.6s ease-out both; animation-delay: var(--delay); }
.cell rect { stroke: #fff; }
.cell.empty { fill: #f3f4f6; stroke: #fff; }
.shade-0 rect { fill: #e6eef7; }
.shade-1 rect { fill: #f9d9a8; }
.shade-2 rect { fill: #f3b26b; }
.shade-3 rect { fill: #e07b39; }
.shade-4 rect { fill: #b8461b; }
.shade-3 .cell-value, .shade-4 .cell-value { fill: #fff; }
.cell { animation: fade 0.5s ease-out both; animation-delay: var(--delay); }
.grid { stroke: #d5dbe1; }
.line { fill: none; stroke: #2f6fb0; stroke-width: 2; stroke-dasharray: 1;
        animation: draw 1.2s ease-out both; }
.point { fill: #2f6fb0; }
.shortfall-bar { width: 80px; display: inline-block; margin: 0; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
td, th { text-align: left; padding: 4px 8px; border-bottom: 1px solid #e5e7eb; }
@keyframes grow { from { transform: scaleX(0); } }
@keyframes fade { from { opacity: 0; } }
@keyframes draw { from { stroke-dashoffset: 1; } }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; } }
"""


def main(argv: list[str] | None = None) -> int:
    """Draw the charts for the sample data and write the preview page.

    Args:
        argv: Arguments excluding the program name. Defaults to ``sys.argv[1:]``.

    Returns:
        The process exit code: 0 on success.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_FILE,
        help="file to write the preview page to",
    )
    out_file: Path = parser.parse_args(argv).out

    out_file.write_text(preview_page(analyse_sample()), encoding="utf-8")
    print(f"Wrote {out_file}")
    return 0


def analyse_sample() -> ReportData:
    """Run the bundled sample data through every stage up to analysis."""
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
        return analyse(connection)
    finally:
        connection.close()


def preview_page(report: ReportData) -> str:
    """Return the preview page holding every chart for one set of figures."""
    largest = max((s.shortfall for s in report.worst_sessions), default=0)
    rows = "".join(
        f"<tr><td>{format_day(session.session_date)}</td>"
        f"<td>{session.shortfall}</td>"
        f"<td>{shortfall_bar(session.shortfall, largest)}</td></tr>"
        for session in report.worst_sessions
    )
    return (
        "<!doctype html>\n"
        '<html lang="en-AU"><head><meta charset="utf-8">'
        "<title>Chart preview</title>"
        f"<style>{PLACEHOLDER_STYLES}</style></head><body>"
        "<h1>Chart preview</h1>"
        "<h2>Understaffed sessions by centre</h2>"
        f"{centre_bar_chart(report.centres)}"
        "<h2>When the gaps happen</h2>"
        f"{heatmap(report.heatmap)}"
        "<h2>Attendance and staff hours</h2>"
        f"{daily_chart(report.daily)}"
        "<h2>Shortfall bars</h2>"
        "<table><tr><th>Date</th><th>Shortfall</th><th></th></tr>"
        f"{rows}</table>"
        "</body></html>\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
