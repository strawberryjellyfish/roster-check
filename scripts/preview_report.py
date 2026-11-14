"""Write the HTML report for the bundled sample data.

A development aid for checking the report by eye until the command line can
write it (milestone M6).

Usage:
    uv run python scripts/preview_report.py [--out FILE]
"""

import argparse
from datetime import datetime
from importlib.resources import files
from pathlib import Path

from roster_check import __version__
from roster_check.analysis import analyse
from roster_check.db import create_database
from roster_check.ingest import read_csv
from roster_check.report import render_report
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

DEFAULT_OUT_FILE = Path("report-preview.html")


def main(argv: list[str] | None = None) -> int:
    """Build the report for the sample data and write it to a file.

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
        help="file to write the report to",
    )
    out_file: Path = parser.parse_args(argv).out

    out_file.write_text(sample_report(), encoding="utf-8")
    print(f"Wrote {out_file}")
    return 0


def sample_report() -> str:
    """Run the bundled sample data through the whole pipeline to HTML."""
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
        report = analyse(connection)
    finally:
        connection.close()
    return render_report(
        report,
        [shifts, sessions],
        generated_at=datetime.now(),
        version=__version__,
        sample_data=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
