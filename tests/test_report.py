"""Tests for the HTML report and its plain-English wording."""

import re
from dataclasses import replace
from datetime import date, datetime, time
from html.parser import HTMLParser
from typing import Any

import pytest
from builders import run_sample

from roster_check.models import (
    CentreSummary,
    HeatmapCell,
    Kpis,
    Rejection,
    ReportData,
    RoleShortfall,
    RowWarning,
    UnderstaffedSession,
    ValidationResult,
)
from roster_check.report import (
    ROLE_LABELS,
    activity_label,
    badge_text,
    format_date,
    format_period,
    percent_text,
    render_report,
    rule_based_summary,
    shortfall_text,
)
from roster_check.validate import KNOWN_ROLES

GENERATED_AT = datetime(2026, 11, 16, 9, 5)
SECTION_HEADINGS = [
    "Summary",
    "Understaffed sessions by centre",
    "When the gaps happen",
    "Attendance and staffing over time",
    "Worst understaffed sessions",
    "Data problems",
    "How the numbers were calculated",
]


class PageParser(HTMLParser):
    """Collect headings, resource references and text from an HTML page."""

    def __init__(self) -> None:
        """Start with nothing collected."""
        super().__init__()
        self.headings: list[str] = []
        self.references: list[str] = []
        self.tags: list[str] = []
        self.styles: list[str] = []
        self._current: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record the tag and any attribute that could load a resource."""
        self.tags.append(tag)
        self._current = tag
        for name, value in attrs:
            if name in {"src", "href", "action", "xlink:href"} and value:
                self.references.append(value)

    def handle_data(self, data: str) -> None:
        """Record heading text and stylesheet contents."""
        if self._current in {"h1", "h2", "h3"} and data.strip():
            self.headings.append(data.strip())
        if self._current == "style":
            self.styles.append(data)

    def handle_endtag(self, tag: str) -> None:
        """Stop collecting text for the tag that has closed."""
        self._current = None


def parse_page(page: str) -> PageParser:
    """Parse a rendered report."""
    parser = PageParser()
    parser.feed(page)
    return parser


def make_report(**changes: Any) -> ReportData:
    """Build report figures for a small two-centre fortnight."""
    report = ReportData(
        period_start=date(2026, 11, 2),
        period_end=date(2026, 11, 15),
        kpis=Kpis(
            sessions_analysed=100,
            understaffed_sessions=15,
            staff_hours=812.5,
            total_attendance=2400,
            rows_rejected=3,
        ),
        centres=(
            CentreSummary("NTH", "Northgate", 50, 10),
            CentreSummary("RBC", "Riverbend Central", 50, 5),
        ),
        heatmap=(
            HeatmapCell(1, 16, 4, 3, 5),
            HeatmapCell(3, 16, 4, 2, 2),
        ),
        daily=(),
        worst_sessions=(),
        staffing_rules=(),
    )
    return replace(report, **changes)


def with_kpis(**changes: Any) -> ReportData:
    """Build report figures with some headline numbers changed."""
    report = make_report()
    return replace(report, kpis=replace(report.kpis, **changes))


def make_understaffed(*roles: RoleShortfall) -> UnderstaffedSession:
    """Build an understaffed swim lesson with the given short roles."""
    return UnderstaffedSession(
        session_id="SE-00001",
        session_date=date(2026, 11, 3),
        centre_name="Northgate",
        activity="swim_lesson",
        start_time=time(16, 0),
        end_time=time(16, 45),
        attendance=21,
        shortfall=sum(role.required - role.present for role in roles),
        roles=roles,
    )


def render(
    report: ReportData | None = None,
    data_files: list[ValidationResult[Any]] | None = None,
    *,
    sample_data: bool = False,
) -> str:
    """Render a report with fixed values for everything but the data."""
    return render_report(
        report or make_report(),
        data_files or [],
        generated_at=GENERATED_AT,
        version="9.9.9",
        sample_data=sample_data,
    )


def result(
    *,
    valid: tuple[Any, ...] = ("row",),
    rejected: tuple[Rejection, ...] = (),
    warnings: tuple[RowWarning, ...] = (),
) -> ValidationResult[Any]:
    """Build a validation result for one data file."""
    return ValidationResult(valid=valid, rejected=rejected, warnings=warnings)


def test_full_dates_include_the_year() -> None:
    assert format_date(date(2026, 11, 2)) == "Mon 2 Nov 2026"


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2026, 11, 2), date(2026, 11, 15), "Mon 2 Nov to Sun 15 Nov 2026"),
        (date(2026, 12, 28), date(2027, 1, 3), "Mon 28 Dec 2026 to Sun 3 Jan 2027"),
        (date(2026, 11, 2), date(2026, 11, 2), "Mon 2 Nov 2026"),
    ],
)
def test_period_gives_the_year_once_when_it_is_shared(
    start: date, end: date, expected: str
) -> None:
    assert format_period(start, end) == expected


@pytest.mark.parametrize(
    ("rows_rejected", "expected"),
    [
        (0, "All rows used"),
        (1, "1 row needs attention"),
        (14, "14 rows need attention"),
    ],
)
def test_badge_wording(rows_rejected: int, expected: str) -> None:
    assert badge_text(rows_rejected) == expected


@pytest.mark.parametrize(
    ("percent", "expected"),
    [
        (0.0, "0%"),
        (0.2, "less than 1%"),
        (0.5, "less than 1%"),
        (15.3, "15%"),
        (100.0, "100%"),
    ],
)
def test_percentages_are_whole_numbers_but_never_hide_a_problem(
    percent: float, expected: str
) -> None:
    assert percent_text(percent) == expected


def test_activity_codes_become_words() -> None:
    assert activity_label("swim_lesson") == "Swim lesson"
    assert activity_label("aqua_zumba_plus") == "Aqua zumba plus"


def test_every_known_role_has_wording() -> None:
    assert set(ROLE_LABELS) == KNOWN_ROLES


def test_shortfall_is_described_in_words() -> None:
    session = make_understaffed(RoleShortfall("swim_instructor", 3, 1))

    assert shortfall_text(session) == "Needs 3 swim instructors, had 1"


def test_shortfall_wording_uses_the_singular_for_one_and_lists_each_role() -> None:
    session = make_understaffed(
        RoleShortfall("lifeguard", 1, 0),
        RoleShortfall("swim_instructor", 2, 1),
    )

    assert shortfall_text(session) == (
        "Needs 1 lifeguard, had 0; Needs 2 swim instructors, had 1"
    )


def test_summary_covers_share_centre_gap_and_rejected_rows() -> None:
    assert rule_based_summary(make_report()) == [
        "From Mon 2 Nov to Sun 15 Nov 2026, 15 of 100 sessions (15%) were "
        "understaffed.",
        "Northgate had the highest share, with 10 of its 50 sessions short of staff.",
        "The largest gap was on Tuesdays at 16:00, with a combined shortfall of "
        "5 staff.",
        "3 rows could not be used and are listed under Data problems.",
    ]


def test_summary_when_nothing_was_understaffed() -> None:
    report = make_report(
        kpis=Kpis(100, 0, 812.5, 2400, 0),
        heatmap=(HeatmapCell(1, 16, 4, 0, 0),),
    )

    assert rule_based_summary(report) == [
        "From Mon 2 Nov to Sun 15 Nov 2026, all 100 sessions were fully staffed.",
        "Every row in the input files was used.",
    ]


def test_summary_for_a_single_fully_staffed_session() -> None:
    report = make_report(period_end=date(2026, 11, 2), kpis=Kpis(1, 0, 2.0, 8, 0))

    assert rule_based_summary(report)[0] == (
        "From Mon 2 Nov 2026, the 1 session was fully staffed."
    )


def test_summary_when_no_sessions_could_be_analysed() -> None:
    report = make_report(period_start=None, period_end=None, kpis=Kpis(0, 0, 0.0, 0, 1))

    assert rule_based_summary(report) == [
        "No sessions could be analysed.",
        "1 row could not be used and is listed under Data problems.",
    ]


def test_summary_uses_the_singular_for_one_understaffed_session() -> None:
    report = with_kpis(understaffed_sessions=1)

    assert "1 of 100 sessions (1%) was understaffed." in rule_based_summary(report)[0]


def test_summary_shows_a_tiny_share_as_less_than_one_percent() -> None:
    report = with_kpis(sessions_analysed=1000, understaffed_sessions=1)

    assert "(less than 1%)" in rule_based_summary(report)[0]


def test_summary_centre_tie_goes_to_the_higher_count_then_report_order() -> None:
    report = make_report(
        centres=(
            CentreSummary("HLS", "Hillside", 10, 2),
            CentreSummary("LKV", "Lakeview", 20, 4),
            CentreSummary("NTH", "Northgate", 20, 4),
        )
    )

    assert rule_based_summary(report)[1].startswith("Lakeview had the highest share")


def test_summary_gap_tie_goes_to_the_earlier_day_and_hour() -> None:
    report = make_report(
        heatmap=(
            HeatmapCell(3, 6, 1, 1, 4),
            HeatmapCell(1, 17, 1, 1, 4),
            HeatmapCell(1, 16, 1, 1, 4),
        )
    )

    assert rule_based_summary(report)[2].startswith(
        "The largest gap was on Tuesdays at 16:00"
    )


def test_summary_gap_of_one_says_one_staff_member() -> None:
    report = make_report(heatmap=(HeatmapCell(0, 6, 1, 1, 1),))

    assert rule_based_summary(report)[2].endswith(
        "with a combined shortfall of 1 staff member."
    )


def test_report_has_every_section() -> None:
    headings = parse_page(render()).headings

    for heading in SECTION_HEADINGS:
        assert heading in headings


def test_report_shows_the_header_details() -> None:
    page = render()

    assert "Riverbend Community Recreation" in page
    assert "Mon 2 Nov to Sun 15 Nov 2026" in page
    assert "Generated Mon 16 Nov 2026 at 09:05" in page
    assert "Roster Check 9.9.9" in page


def test_report_makes_no_external_requests() -> None:
    page = render(*run_sample())
    parsed = parse_page(page)

    assert all(reference.startswith("#") for reference in parsed.references)
    assert "link" not in parsed.tags
    assert not any("@import" in style for style in parsed.styles)
    assert not re.search(r"https?://", page)


def test_report_inlines_its_styles_and_script() -> None:
    page = render()

    assert "<style>" in page
    assert "--accent" in page
    assert "IntersectionObserver" in page


def test_headline_numbers_are_formatted_and_ready_to_count_up() -> None:
    page = render()

    assert 'data-value="812.5" data-decimals="1">812.5<' in page
    assert 'data-value="2400" data-decimals="0">2,400<' in page
    assert "15% of sessions" in page


def test_badge_links_to_data_problems_when_rows_were_rejected() -> None:
    page = render()

    assert (
        '<a class="badge badge-warn" href="#data-problems">3 rows need attention</a>'
        in page
    )


def test_clean_data_shows_the_all_clear() -> None:
    page = render(with_kpis(rows_rejected=0))

    assert '<p class="badge badge-good">All rows used</p>' in page
    assert "All rows were usable." in page


def test_rejected_rows_are_listed_by_file_with_line_numbers() -> None:
    rejected = (
        Rejection(
            "rosters.csv", 27, "SH-1,NTH,31/11/2026", "Date 31/11/2026 does not exist"
        ),
        Rejection("rosters.csv", 12, "SH-2,,", "Missing staff ID"),
    )

    page = render(data_files=[result(rejected=rejected)])

    assert "<h3>rosters.csv</h3>" in page
    assert '<td class="number">12</td><td>Missing staff ID</td>' in page
    assert page.index("Missing staff ID") < page.index("does not exist")
    assert "2 rows were left out." in page


def test_auto_fixed_rows_are_in_a_collapsed_list() -> None:
    warning = RowWarning(
        "sessions.csv", 9, " se-1 ,nth", "Cleaned spacing and capitals"
    )

    page = render(data_files=[result(warnings=(warning,))])

    assert "<summary>Auto-fixed (1)</summary>" in page
    assert "Cleaned spacing and capitals" in page


def test_raw_row_text_is_escaped() -> None:
    rejection = Rejection(
        "rosters.csv", 5, '<script>alert("x")</script>,&', "Missing staff ID"
    )

    page = render(data_files=[result(rejected=(rejection,))])

    assert "<script>alert" not in page
    assert "&lt;script&gt;alert(&#34;x&#34;)&lt;/script&gt;,&amp;" in page


def test_file_names_are_escaped() -> None:
    rejection = Rejection("<b>rosters</b>.csv", 5, "x", "Missing staff ID")

    page = render(data_files=[result(rejected=(rejection,))])

    assert "<b>rosters</b>" not in page


def test_file_with_no_usable_rows_shows_a_banner() -> None:
    rejection = Rejection("sessions.csv", 2, "x", "Missing activity")

    page = render(data_files=[result(valid=(), rejected=(rejection,))])

    assert "No usable rows in sessions.csv" in page


def test_no_banner_when_every_file_has_usable_rows() -> None:
    rejection = Rejection("sessions.csv", 2, "x", "Missing activity")

    page = render(data_files=[result(rejected=(rejection,))])

    assert "No usable rows" not in page


def test_worst_sessions_table_describes_each_shortfall() -> None:
    session = make_understaffed(RoleShortfall("swim_instructor", 3, 1))

    page = render(make_report(worst_sessions=(session,)))

    assert "Needs 3 swim instructors, had 1" in page
    assert "16:00 to 16:45" in page
    assert 'class="chart shortfall-bar"' in page


def test_no_understaffed_sessions_says_so() -> None:
    assert "No sessions were understaffed." in render()


def test_fictional_note_appears_only_for_the_sample_data() -> None:
    note = "All data in this report is fictional."

    assert note in render(sample_data=True)
    assert note not in render(sample_data=False)


def test_staffing_rules_are_shown_in_words() -> None:
    page = render(*run_sample())

    assert "<td>Swim lesson</td><td>Swim instructor</td>" in page


def test_sample_report_lists_the_planted_problems() -> None:
    page = render(*run_sample())

    assert "17 rows need attention" in page
    assert (
        '<td class="number">304</td><td>Duplicate shift ID, first seen on line 102</td>'
        in page
    )
    assert "Needs 3 swim instructors, had 1" in page


def test_summary_leaves_out_the_gap_when_no_cell_has_a_shortfall() -> None:
    report = make_report(heatmap=())

    assert not any("largest gap" in sentence for sentence in rule_based_summary(report))


def test_files_without_problems_are_not_listed() -> None:
    rejection = Rejection("sessions.csv", 2, "x", "Missing activity")

    page = render(data_files=[result(), result(rejected=(rejection,))])

    assert parse_page(page).headings.count("sessions.csv") == 1
    assert "<h3>" not in page.replace("<h3>sessions.csv</h3>", "")
