"""Tests for gathering the report figures into ``ReportData``."""

from dataclasses import fields, is_dataclass
from datetime import date, time

import pytest
from builders import (
    WEDNESDAY,
    build_database,
    lifeguard,
    make_session,
    make_shift,
    run_sample,
)

from roster_check.analysis import analyse
from roster_check.models import Rejection, ReportData


def all_strings(value: object) -> list[str]:
    """Return every string held anywhere inside nested dataclasses and tuples."""
    if isinstance(value, str):
        return [value]
    if is_dataclass(value):
        return [
            text
            for field in fields(value)
            for text in all_strings(getattr(value, field.name))
        ]
    if isinstance(value, tuple):
        return [text for item in value for text in all_strings(item)]
    return []


def test_headline_numbers() -> None:
    sessions = [make_session("SE-00001", attendance=9), make_session("SE-00002")]
    shifts = [make_shift("SH-1", staff_id="S-1"), lifeguard()]
    rejection = Rejection("sessions.csv", 9, "bad", "Missing activity")

    report = analyse(build_database(sessions, shifts, rejections=[rejection]))

    assert report.period_start == WEDNESDAY
    assert report.period_end == WEDNESDAY
    assert report.kpis.sessions_analysed == 2
    assert report.kpis.understaffed_sessions == 1
    assert report.kpis.understaffed_percent == 50.0
    assert report.kpis.staff_hours == 4.0
    assert report.kpis.total_attendance == 17
    assert report.kpis.rows_rejected == 1


def test_staff_hours_count_every_role_including_front_desk() -> None:
    shifts = [
        make_shift(
            "SH-1", staff_id="S-1", role="front_desk", start="05:15", end="13:00"
        )
    ]

    report = analyse(build_database([], shifts))

    assert report.kpis.staff_hours == 7.75


def test_centre_with_no_sessions_is_listed_with_zero() -> None:
    report = analyse(build_database([make_session(attendance=0)], []))

    northgate = next(c for c in report.centres if c.centre_code == "NTH")
    assert northgate.centre_name == "Northgate"
    assert northgate.sessions == 0
    assert northgate.understaffed_percent == 0.0
    assert [c.centre_code for c in report.centres] == ["NTH", "RBC"]


def test_heatmap_places_each_session_in_the_hour_it_starts() -> None:
    sessions = [
        make_session("SE-00001", start="16:00", end="16:45", attendance=0),
        make_session("SE-00002", start="16:45", end="17:30", attendance=0),
    ]

    report = analyse(build_database(sessions, []))

    assert len(report.heatmap) == 1
    cell = report.heatmap[0]
    assert (cell.weekday, cell.hour) == (2, 16)
    assert cell.sessions == 2
    assert cell.understaffed_sessions == 2
    assert cell.shortfall == 4


def test_daily_totals_include_days_with_shifts_but_no_sessions() -> None:
    thursday = date(2026, 11, 5)
    shifts = [
        lifeguard(),
        make_shift(
            "SH-2", staff_id="S-2", shift_date=thursday, start="06:00", end="07:30"
        ),
    ]

    report = analyse(build_database([make_session(attendance=8)], shifts))

    assert [(d.day, d.attendance, d.staff_hours) for d in report.daily] == [
        (WEDNESDAY, 8, 2.0),
        (thursday, 0, 1.5),
    ]


def test_worst_sessions_are_ranked_with_a_fixed_tie_break() -> None:
    sessions = [
        make_session("SE-00004", attendance=9),
        make_session("SE-00003", attendance=9),
        make_session("SE-00002", attendance=17),
        make_session("SE-00001", attendance=9, start="09:00", end="09:45"),
    ]
    shifts = [
        make_shift("SH-1", staff_id="S-1", start="08:00", end="18:00"),
        make_shift(
            "SH-2", staff_id="S-2", role="lifeguard", start="08:00", end="18:00"
        ),
    ]

    report = analyse(build_database(sessions, shifts))

    # SE-00002 is short by 2. The rest are short by 1 with equal attendance,
    # so they follow start time, then session ID.
    assert [s.session_id for s in report.worst_sessions] == [
        "SE-00002",
        "SE-00001",
        "SE-00003",
        "SE-00004",
    ]


def test_worst_sessions_are_limited_to_ten() -> None:
    sessions = [make_session(f"SE-{n:05d}", attendance=0) for n in range(1, 13)]

    report = analyse(build_database(sessions, []))

    assert len(report.worst_sessions) == 10


def test_worst_sessions_list_only_the_roles_that_were_short() -> None:
    session = make_session(attendance=20, start="16:00", end="16:45")
    report = analyse(
        build_database([session], [make_shift("SH-1", staff_id="S-1"), lifeguard()])
    )

    worst = report.worst_sessions[0]
    assert worst.centre_name == "Riverbend Central"
    assert worst.start_time == time(16, 0)
    assert worst.shortfall == 2
    assert [(r.role, r.required, r.present) for r in worst.roles] == [
        ("swim_instructor", 3, 1)
    ]


def test_staffing_rules_are_included_for_the_footer() -> None:
    report = analyse(build_database([], []))

    assert [(r.activity, r.role) for r in report.staffing_rules] == [
        ("lap_swim", "lifeguard"),
        ("swim_lesson", "lifeguard"),
        ("swim_lesson", "swim_instructor"),
    ]


def test_no_sessions_gives_empty_figures_not_an_error() -> None:
    report = analyse(build_database([], []))

    assert report.period_start is None
    assert report.period_end is None
    assert report.kpis.sessions_analysed == 0
    assert report.kpis.understaffed_percent == 0.0
    assert report.heatmap == ()
    assert report.daily == ()
    assert report.worst_sessions == ()


def test_report_data_holds_no_staff_names_or_ids() -> None:
    shifts = [
        make_shift("SH-1", staff_id="S-SECRET", staff_name="Unique Testname"),
        lifeguard(staff_id="S-HIDDEN"),
    ]
    report = analyse(build_database([make_session(attendance=20)], shifts))

    strings = all_strings(report)
    assert strings
    for private in ["S-SECRET", "S-HIDDEN", "Unique Testname"]:
        assert private not in strings


@pytest.fixture(scope="module")
def sample_report() -> ReportData:
    """The report figures for the bundled sample data."""
    report, _ = run_sample()
    return report


def test_golden_headline_numbers_for_the_sample(sample_report: ReportData) -> None:
    assert sample_report.period_start == date(2026, 11, 2)
    assert sample_report.period_end == date(2026, 11, 15)
    assert sample_report.kpis.sessions_analysed == 281
    assert sample_report.kpis.understaffed_sessions == 43
    assert sample_report.kpis.staff_hours == 2165.5
    assert sample_report.kpis.total_attendance == 7234
    assert sample_report.kpis.rows_rejected == 17


def test_golden_centre_numbers_for_the_sample(sample_report: ReportData) -> None:
    assert [
        (c.centre_code, c.sessions, c.understaffed_sessions)
        for c in sample_report.centres
    ] == [("HLS", 70, 7), ("LKV", 70, 9), ("NTH", 70, 17), ("RBC", 71, 10)]
