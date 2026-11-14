"""Tests for row validation, field parsers and the reference files.

Each row-level bad-data case in section 4.4 of the project brief has a test
asserting both its outcome and its exact reason text.
"""

import csv
from datetime import date, time
from importlib.resources import files
from pathlib import Path

import pytest

from roster_check.ingest import read_csv
from roster_check.models import (
    CsvFile,
    InputError,
    RawRow,
    Session,
    Shift,
    ValidationResult,
)
from roster_check.validate import (
    CENTRE_COLUMNS,
    ROSTER_COLUMNS,
    SESSION_COLUMNS,
    STAFFING_RULE_COLUMNS,
    RowError,
    parse_date,
    parse_time,
    parse_whole_number,
    validate_centres,
    validate_sessions,
    validate_shifts,
    validate_staffing_rules,
)

CENTRE_CODES = {"RBC", "NTH", "HLS", "LKV"}
ACTIVITIES = {"swim_lesson", "lap_swim", "gym_floor", "group_fitness"}

GOOD_SHIFT = "SH-00001,RBC,S-001,Jordan Placeholder,lifeguard,03/11/2026,06:00,10:30"
GOOD_SESSION = "SE-00001,NTH,swim_lesson,04/11/2026,16:00,16:45,24,19"


def make_file(
    lines: list[str],
    header: tuple[str, ...],
    file_name: str = "test.csv",
) -> CsvFile:
    """Build an ingested file from data lines, numbered from line 2."""
    rows = tuple(
        RawRow(line_number, line, tuple(next(csv.reader([line]))))
        for line_number, line in enumerate(lines, start=2)
    )
    return CsvFile(file_name, header, rows, 0, (), False)


def shift_with(**changes: str) -> str:
    """Return the good shift row with some columns replaced."""
    values = dict(zip(ROSTER_COLUMNS, GOOD_SHIFT.split(","), strict=True))
    values.update(changes)
    return ",".join(values[column] for column in ROSTER_COLUMNS)


def session_with(**changes: str) -> str:
    """Return the good session row with some columns replaced."""
    values = dict(zip(SESSION_COLUMNS, GOOD_SESSION.split(","), strict=True))
    values.update(changes)
    return ",".join(values[column] for column in SESSION_COLUMNS)


def check_shifts(*lines: str) -> ValidationResult[Shift]:
    """Validate roster lines against the known centres."""
    return validate_shifts(make_file(list(lines), ROSTER_COLUMNS), CENTRE_CODES)


def check_sessions(*lines: str) -> ValidationResult[Session]:
    """Validate session lines against the known centres and activities."""
    return validate_sessions(
        make_file(list(lines), SESSION_COLUMNS), CENTRE_CODES, ACTIVITIES
    )


def shift_reason(line: str) -> str:
    """Validate one roster line and return the reason it was rejected."""
    result = check_shifts(line)
    assert result.valid == ()
    return result.rejected[0].reason


def session_reason(line: str) -> str:
    """Validate one session line and return the reason it was rejected."""
    result = check_sessions(line)
    assert result.valid == ()
    return result.rejected[0].reason


# Valid rows


def test_valid_shift_becomes_a_record() -> None:
    result = check_shifts(GOOD_SHIFT)

    assert result.rejected == ()
    assert result.warnings == ()
    shift = result.valid[0]
    assert shift.shift_id == "SH-00001"
    assert shift.staff_name == "Jordan Placeholder"
    assert shift.shift_date == date(2026, 11, 3)
    assert shift.start_time == time(6, 0)
    assert shift.end_time == time(10, 30)
    assert shift.line_number == 2


def test_valid_session_becomes_a_record() -> None:
    result = check_sessions(GOOD_SESSION)

    assert result.rejected == ()
    session = result.valid[0]
    assert session.activity == "swim_lesson"
    assert session.capacity == 24
    assert session.attendance == 19


def test_blank_staff_name_is_allowed_and_stored_as_none() -> None:
    result = check_shifts(shift_with(staff_name=""))

    assert result.valid[0].staff_name is None


def test_zero_attendance_is_valid() -> None:
    result = check_sessions(session_with(attendance="0"))

    assert result.valid[0].attendance == 0


# Case 1: required field blank


@pytest.mark.parametrize(
    ("column", "reason"),
    [
        ("shift_id", "Missing shift ID"),
        ("centre_code", "Missing centre code"),
        ("staff_id", "Missing staff ID"),
        ("role", "Missing role"),
        ("shift_date", "Missing shift date"),
        ("start_time", "Missing start time"),
        ("end_time", "Missing end time"),
    ],
)
def test_case_1_blank_required_shift_field_is_rejected(
    column: str, reason: str
) -> None:
    assert shift_reason(shift_with(**{column: ""})) == reason


@pytest.mark.parametrize(
    ("column", "reason"),
    [
        ("session_id", "Missing session ID"),
        ("activity", "Missing activity"),
        ("session_date", "Missing session date"),
        ("capacity", "Missing capacity"),
        ("attendance", "Missing attendance"),
    ],
)
def test_case_1_blank_required_session_field_is_rejected(
    column: str,
    reason: str,
) -> None:
    assert session_reason(session_with(**{column: ""})) == reason


# Case 2: impossible date


@pytest.mark.parametrize("text", ["31/11/2026", "2026-02-30", "29/02/2026"])
def test_case_2_impossible_date_is_rejected(text: str) -> None:
    assert shift_reason(shift_with(shift_date=text)) == f"Date {text} does not exist"


# Case 3: two-digit year


def test_case_3_two_digit_year_is_rejected() -> None:
    line = session_with(session_date="04/11/26")

    assert session_reason(line) == "Could not read session date '04/11/26'"


# Case 4: unreadable date or time


def test_case_4_unreadable_date_is_rejected() -> None:
    line = session_with(session_date="next tues")

    assert session_reason(line) == "Could not read session date 'next tues'"


@pytest.mark.parametrize("text", ["25:00", "24:00", "12:60", "noon", "06:00:30"])
def test_case_4_unreadable_time_is_rejected(text: str) -> None:
    line = shift_with(start_time=text)

    assert shift_reason(line) == f"Could not read start time '{text}'"


# Case 5: end before start


def test_case_5_shift_ending_before_it_starts_is_rejected() -> None:
    line = shift_with(start_time="14:00", end_time="09:00")

    assert shift_reason(line) == "Shift ends before it starts"


def test_case_5_session_ending_before_it_starts_is_rejected() -> None:
    line = session_with(start_time="16:45", end_time="16:00")

    assert session_reason(line) == "Session ends before it starts"


def test_shift_with_no_length_is_rejected() -> None:
    line = shift_with(start_time="09:00", end_time="09:00")

    assert shift_reason(line) == "Shift starts and ends at the same time"


# Case 6: non-numeric number


def test_case_6_non_numeric_attendance_is_rejected() -> None:
    line = session_with(attendance="twelve")

    assert session_reason(line) == "Attendance 'twelve' is not a number"


def test_decimal_attendance_is_rejected() -> None:
    line = session_with(attendance="12.5")

    assert session_reason(line) == "Attendance '12.5' is not a whole number"


# Case 7: negative number


def test_case_7_negative_attendance_is_rejected() -> None:
    assert (
        session_reason(session_with(attendance="-3")) == "Attendance cannot be negative"
    )


@pytest.mark.parametrize("text", ["0", "-5"])
def test_capacity_must_be_greater_than_zero(text: str) -> None:
    line = session_with(capacity=text)

    assert session_reason(line) == "Capacity must be greater than 0"


# Case 8: attendance over capacity


def test_case_8_attendance_over_capacity_is_kept_and_flagged() -> None:
    result = check_sessions(session_with(capacity="24", attendance="31"))

    assert result.valid[0].attendance == 31
    assert result.rejected == ()
    assert [warning.reason for warning in result.warnings] == [
        "Attendance is above capacity (31 of 24)"
    ]


# Case 9: unknown centre


def test_case_9_unknown_centre_is_rejected() -> None:
    assert shift_reason(shift_with(centre_code="XYZ")) == "Unknown centre 'XYZ'"


# Case 10: unknown role or activity


def test_case_10_unknown_role_is_rejected() -> None:
    assert shift_reason(shift_with(role="cleaner")) == "Unknown role 'cleaner'"


def test_case_10_unknown_activity_is_rejected() -> None:
    line = session_with(activity="aqua_zumba")

    assert session_reason(line) == "Unknown activity 'aqua_zumba'"


# Case 11: duplicate ID


def test_case_11_duplicate_id_keeps_first_and_rejects_later() -> None:
    result = check_shifts(GOOD_SHIFT, GOOD_SHIFT)

    assert [shift.line_number for shift in result.valid] == [2]
    assert result.rejected[0].line_number == 3
    assert result.rejected[0].reason == "Duplicate shift ID, first seen on line 2"


def test_case_11_rejected_row_still_claims_its_id() -> None:
    result = check_sessions(session_with(attendance="twelve"), GOOD_SESSION)

    assert result.valid == ()
    assert result.rejected[1].reason == "Duplicate session ID, first seen on line 2"


def test_case_11_id_is_compared_after_cleaning() -> None:
    result = check_shifts(GOOD_SHIFT, shift_with(shift_id=" sh-00001 "))

    assert result.rejected[0].reason == "Duplicate shift ID, first seen on line 2"


def test_row_with_wrong_column_count_does_not_claim_its_id() -> None:
    short_row = ",".join(GOOD_SHIFT.split(",")[:6])

    result = check_shifts(short_row, GOOD_SHIFT)

    assert [shift.line_number for shift in result.valid] == [3]


def test_blank_id_claims_nothing() -> None:
    result = check_shifts(shift_with(shift_id=""), shift_with(shift_id=""))

    assert [rejection.reason for rejection in result.rejected] == [
        "Missing shift ID",
        "Missing shift ID",
    ]


# Case 12: wrong number of columns


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        (",".join(GOOD_SHIFT.split(",")[:6]), "Expected 8 columns, found 6"),
        (f"{GOOD_SHIFT},extra", "Expected 8 columns, found 9"),
    ],
)
def test_case_12_wrong_number_of_columns_is_rejected(line: str, reason: str) -> None:
    assert shift_reason(line) == reason


# Case 13: stray whitespace or case


def test_case_13_spacing_and_capitals_are_cleaned_with_a_warning() -> None:
    line = shift_with(shift_id=" sh-00001", centre_code="rbc", role=" Lifeguard ")

    result = check_shifts(line)

    shift = result.valid[0]
    assert shift.shift_id == "SH-00001"
    assert shift.centre_code == "RBC"
    assert shift.role == "lifeguard"
    assert [warning.reason for warning in result.warnings] == [
        "Cleaned spacing and capitals"
    ]


def test_case_13_staff_names_are_only_trimmed() -> None:
    result = check_shifts(shift_with(staff_name=" jordan PLACEHOLDER "))

    assert result.valid[0].staff_name == "jordan PLACEHOLDER"


def test_cleaning_and_over_capacity_give_two_warnings() -> None:
    line = session_with(activity=" Swim_Lesson ", attendance="30")

    result = check_sessions(line)

    assert [warning.reason for warning in result.warnings] == [
        "Cleaned spacing and capitals",
        "Attendance is above capacity (30 of 24)",
    ]


def test_rejected_row_gets_no_cleaning_warning() -> None:
    result = check_shifts(shift_with(centre_code="rbc", role="cleaner"))

    assert result.warnings == ()
    assert result.rejected[0].reason == "Unknown role 'cleaner'"


# Rules that apply across cases


def test_only_the_first_problem_is_reported() -> None:
    line = session_with(activity="aqua_zumba", attendance="twelve")

    assert session_reason(line) == "Unknown activity 'aqua_zumba'"


def test_first_problem_follows_the_brief_order_not_the_file_order() -> None:
    header = tuple(reversed(SESSION_COLUMNS))
    values = dict(zip(SESSION_COLUMNS, GOOD_SESSION.split(","), strict=True))
    values.update(session_date="next tues", attendance="twelve")
    line = ",".join(values[column] for column in header)

    result = validate_sessions(make_file([line], header), CENTRE_CODES, ACTIVITIES)

    assert result.rejected[0].reason == "Could not read session date 'next tues'"


def test_rejection_records_file_line_and_raw_text() -> None:
    line = shift_with(role="cleaner")

    result = validate_shifts(
        make_file([line], ROSTER_COLUMNS, "rosters.csv"), CENTRE_CODES
    )

    rejection = result.rejected[0]
    assert rejection.file_name == "rosters.csv"
    assert rejection.line_number == 2
    assert rejection.raw_text == line


# Lines the CSV reader could not parse


def test_row_ingest_could_not_parse_is_rejected_with_its_reason() -> None:
    bad = RawRow(2, 'SH-00001,RBC,"Jordan', (), "Row has an unfinished quoted field")
    good = RawRow(3, GOOD_SHIFT, tuple(GOOD_SHIFT.split(",")))
    csv_file = CsvFile("rosters.csv", ROSTER_COLUMNS, (bad, good), 0, (), False)

    result = validate_shifts(csv_file, CENTRE_CODES)

    assert [rejection.reason for rejection in result.rejected] == [
        "Row has an unfinished quoted field"
    ]
    assert [shift.line_number for shift in result.valid] == [3]


def test_number_too_long_to_convert_is_rejected() -> None:
    line = session_with(attendance="9" * 5000)

    assert session_reason(line) == "Attendance is too long to be a number"


# Case 18: every row rejected


def test_case_18_file_with_every_row_rejected_gives_no_valid_rows(
    fixtures_dir: Path,
) -> None:
    csv_file = read_csv(fixtures_dir / "sessions_all_rejected.csv", SESSION_COLUMNS)

    result = validate_sessions(csv_file, CENTRE_CODES, ACTIVITIES)

    assert result.valid == ()
    assert len(result.rejected) == 3


# Field parsers


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("04/11/2026", date(2026, 11, 4)),
        ("4/11/2026", date(2026, 11, 4)),
        ("2026-11-04", date(2026, 11, 4)),
    ],
)
def test_parse_date_accepts_australian_and_iso_formats(
    text: str, expected: date
) -> None:
    assert parse_date(text, "session date") == expected


def test_parse_date_never_reads_us_month_first_dates() -> None:
    with pytest.raises(RowError, match=r"^Date 11/30/2026 does not exist$"):
        parse_date("11/30/2026", "session date")


@pytest.mark.parametrize(
    ("text", "expected"),
    [("06:00", time(6, 0)), ("6:00", time(6, 0)), ("06:00:00", time(6, 0))],
)
def test_parse_time_accepts_supported_formats(text: str, expected: time) -> None:
    assert parse_time(text, "start time") == expected


@pytest.mark.parametrize(("text", "expected"), [("19", 19), ("0", 0), ("-3", -3)])
def test_parse_whole_number_reads_whole_numbers(text: str, expected: int) -> None:
    assert parse_whole_number(text, "attendance") == expected


# Reference files


def test_bundled_reference_files_are_valid() -> None:
    data = files("roster_check").joinpath("data")
    centres_path = Path(str(data.joinpath("centres.csv")))
    rules_path = Path(str(data.joinpath("staffing_rules.csv")))

    centres = validate_centres(read_csv(centres_path, CENTRE_COLUMNS))
    rules = validate_staffing_rules(read_csv(rules_path, STAFFING_RULE_COLUMNS))

    assert [centre.centre_code for centre in centres] == ["RBC", "NTH", "HLS", "LKV"]
    assert len(rules) == 5


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("swim_lesson,lifeguard,0,1", "Participants per staff must be greater than 0"),
        ("swim_lesson,lifeguard,-2,1", "Participants per staff must be greater than 0"),
        (
            "swim_lesson,lifeguard,8.5,1",
            "Participants per staff '8.5' is not a whole number",
        ),
        ("swim_lesson,lifeguard,,1", "Missing participants per staff"),
        ("swim_lesson,lifeguard,8,-1", "Minimum staff cannot be negative"),
        ("swim_lesson,cleaner,8,1", "Unknown role 'cleaner'"),
        (
            f"swim_lesson,lifeguard,{'9' * 5000},1",
            "Participants per staff is too long to be a number",
        ),
    ],
)
def test_bad_staffing_rule_is_fatal(line: str, message: str) -> None:
    csv_file = make_file([line], STAFFING_RULE_COLUMNS, "staffing_rules.csv")

    with pytest.raises(InputError) as error:
        validate_staffing_rules(csv_file)

    assert str(error.value) == f"staffing_rules.csv line 2: {message}"


def test_zero_minimum_staff_is_allowed() -> None:
    csv_file = make_file(["gym_floor,gym_supervisor,25,0"], STAFFING_RULE_COLUMNS)

    assert validate_staffing_rules(csv_file)[0].minimum_staff == 0


def test_duplicate_staffing_rule_is_fatal() -> None:
    lines = ["swim_lesson,lifeguard,30,1", "Swim_Lesson,lifeguard,25,1"]
    csv_file = make_file(lines, STAFFING_RULE_COLUMNS, "staffing_rules.csv")

    with pytest.raises(InputError) as error:
        validate_staffing_rules(csv_file)

    assert str(error.value) == (
        "staffing_rules.csv line 3: Duplicate staffing rule, first seen on line 2"
    )


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        (["RBC,"], "centres.csv line 2: Missing centre name"),
        (
            ["RBC,Riverbend Central", "rbc,Again"],
            ("centres.csv line 3: Duplicate centre code, first seen on line 2"),
        ),
    ],
)
def test_bad_centre_row_is_fatal(lines: list[str], message: str) -> None:
    csv_file = make_file(lines, CENTRE_COLUMNS, "centres.csv")

    with pytest.raises(InputError) as error:
        validate_centres(csv_file)

    assert str(error.value) == message


# The bundled sample data


def test_bundled_sample_gives_exactly_the_planted_problems() -> None:
    sample = Path(str(files("roster_check").joinpath("data", "sample")))
    shifts = validate_shifts(
        read_csv(sample / "rosters.csv", ROSTER_COLUMNS), CENTRE_CODES
    )
    sessions = validate_sessions(
        read_csv(sample / "sessions.csv", SESSION_COLUMNS), CENTRE_CODES, ACTIVITIES
    )

    assert [rejection.reason for rejection in shifts.rejected] == [
        "Missing staff ID",
        "Date 31/11/2026 does not exist",
        "Could not read start time '25:00'",
        "Shift ends before it starts",
        "Unknown centre 'XYZ'",
        "Unknown role 'cleaner'",
        "Expected 8 columns, found 6",
        "Could not read shift date '05/11/26'",
        "Duplicate shift ID, first seen on line 102",
    ]
    assert [warning.reason for warning in shifts.warnings] == [
        "Cleaned spacing and capitals"
    ]
    assert [rejection.reason for rejection in sessions.rejected] == [
        "Missing activity",
        "Could not read session date 'next tues'",
        "Session ends before it starts",
        "Attendance 'twelve' is not a number",
        "Attendance cannot be negative",
        "Unknown activity 'aqua_zumba'",
        "Expected 8 columns, found 9",
        "Duplicate session ID, first seen on line 182",
    ]
    assert [warning.reason for warning in sessions.warnings][1:] == [
        "Cleaned spacing and capitals"
    ]
    assert sessions.warnings[0].reason.startswith("Attendance is above capacity")
    assert len(shifts.valid) == 548
    assert len(sessions.valid) == 281
