"""Generate the fictional sample data bundled with Roster Check.

Writes ``rosters.csv`` and ``sessions.csv`` for four centres over two weeks,
then plants a fixed set of bad rows covering the row-level cases in section
4.4 of the project brief. The same seed always produces byte-identical files.

``rosters.csv`` is written as an Excel export would be (byte-order mark and
Windows line endings) to cover case 15. ``sessions.csv`` is plain UTF-8.

Usage:
    uv run python scripts/make_sample_data.py [--out DIRECTORY]
"""

import argparse
import csv
import math
import random
from dataclasses import dataclass
from datetime import date, time, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "src" / "roster_check" / "data"
DEFAULT_OUT_DIR = DATA_DIR / "sample"

SEED = 20261102
FIRST_DAY = date(2026, 11, 2)
NUMBER_OF_DAYS = 14
DATE_FORMAT = "%d/%m/%Y"
TIME_FORMAT = "%H:%M"

ROSTER_COLUMNS = [
    "shift_id",
    "centre_code",
    "staff_id",
    "staff_name",
    "role",
    "shift_date",
    "start_time",
    "end_time",
]
SESSION_COLUMNS = [
    "session_id",
    "centre_code",
    "activity",
    "session_date",
    "start_time",
    "end_time",
    "capacity",
    "attendance",
]

CAPACITY = {"lap_swim": 40, "gym_floor": 60, "group_fitness": 30, "swim_lesson": 24}
LOWEST_ATTENDANCE_SHARE = 0.35
HIGHEST_ATTENDANCE_SHARE = 0.95

# Timetable for each type of day: (activity, start, end).
WEEKDAY_SESSIONS = [
    ("gym_floor", "05:30", "09:30"),
    ("lap_swim", "06:00", "07:30"),
    ("swim_lesson", "16:00", "16:45"),
    ("swim_lesson", "16:45", "17:30"),
    ("gym_floor", "16:00", "21:00"),
    ("group_fitness", "18:00", "18:45"),
]
SATURDAY_SESSIONS = [
    ("lap_swim", "07:00", "09:00"),
    ("gym_floor", "08:00", "12:00"),
    ("swim_lesson", "08:30", "09:15"),
    ("swim_lesson", "09:15", "10:00"),
]
SUNDAY_SESSIONS = [
    ("lap_swim", "08:00", "10:00"),
    ("group_fitness", "09:00", "09:45"),
]

# Shift blocks for each type of day: (role, start, end). Each block is staffed
# for the busiest session it fully covers.
WEEKDAY_SHIFTS = [
    ("front_desk", "05:15", "13:00"),
    ("gym_supervisor", "05:30", "09:30"),
    ("lifeguard", "05:45", "10:00"),
    ("front_desk", "13:00", "21:15"),
    ("lifeguard", "15:45", "18:00"),
    ("swim_instructor", "15:45", "17:45"),
    ("gym_supervisor", "16:00", "21:00"),
    ("group_fitness", "17:45", "19:00"),
]
SATURDAY_SHIFTS = [
    ("front_desk", "06:30", "12:30"),
    ("lifeguard", "06:45", "11:00"),
    ("gym_supervisor", "08:00", "12:00"),
    ("swim_instructor", "08:15", "10:15"),
]
SUNDAY_SHIFTS = [
    ("front_desk", "07:30", "12:00"),
    ("lifeguard", "07:45", "10:15"),
    ("group_fitness", "08:45", "10:00"),
]

# Roles with no staffing rule (front desk) roster this many staff per block.
UNRULED_ROLE_STAFF = 1

STAFF_PER_CENTRE = {
    "lifeguard": 4,
    "swim_instructor": 4,
    "gym_supervisor": 6,
    "group_fitness": 2,
    "front_desk": 3,
}

# Deliberate understaffing, so the report shows clear patterns rather than
# noise: (centre, role, weekdays, shift start, staff removed). Monday is 0.
UNDERSTAFFING_PATTERNS = [
    ("NTH", "swim_instructor", {0, 1, 2, 3}, "15:45", 1),
    ("HLS", "gym_supervisor", {5}, "08:00", 1),
    ("LKV", "lifeguard", {0}, "05:45", 1),
]
# Chance that any other shift block is one person short through absence.
ABSENCE_CHANCE = 0.04

FIRST_NAMES = [
    "Alex",
    "Bailey",
    "Casey",
    "Charlie",
    "Dakota",
    "Drew",
    "Eden",
    "Finley",
    "Harper",
    "Jamie",
    "Jordan",
    "Kai",
    "Morgan",
    "Parker",
    "Quinn",
    "Reese",
    "Riley",
    "Rowan",
    "Sam",
    "Taylor",
]
# Surnames are deliberately and obviously fictional.
LAST_NAMES = [
    "Placeholder",
    "Example",
    "Sample",
    "Specimen",
    "Fixture",
    "Mockridge",
    "Testwell",
    "Dummett",
    "Notreal",
    "Fictional",
]


@dataclass(frozen=True)
class StaffMember:
    """A fictional staff member who works one role at one centre."""

    staff_id: str
    staff_name: str
    centre_code: str
    role: str


@dataclass(frozen=True)
class PlannedSession:
    """A session on the timetable, with its generated attendance."""

    centre_code: str
    activity: str
    day: date
    start: time
    end: time
    capacity: int
    attendance: int


@dataclass(frozen=True)
class PlannedShift:
    """A shift worked by one staff member."""

    staff: StaffMember
    day: date
    start: time
    end: time


def main(argv: list[str] | None = None) -> int:
    """Generate the sample files and write them to the output directory.

    Args:
        argv: Arguments excluding the program name. Defaults to ``sys.argv[1:]``.

    Returns:
        The process exit code: 0 on success.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="directory to write rosters.csv and sessions.csv to",
    )
    out_dir: Path = parser.parse_args(argv).out

    rng = random.Random(SEED)  # noqa: S311 - reproducible sample data, not security
    centre_codes = load_centre_codes()
    rules = load_staffing_rules()

    staff = build_staff(rng, centre_codes)
    sessions = plan_sessions(rng, centre_codes)
    shifts = plan_shifts(rng, centre_codes, sessions, staff, rules)

    roster_rows = plant_roster_problems(format_roster_rows(shifts))
    session_rows = plant_session_problems(format_session_rows(sessions))

    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "rosters.csv", ROSTER_COLUMNS, roster_rows, excel_export=True)
    write_csv(out_dir / "sessions.csv", SESSION_COLUMNS, session_rows)
    print(f"Wrote {len(roster_rows)} roster rows and {len(session_rows)} session rows")
    print(f"to {out_dir}")
    return 0


def load_centre_codes() -> list[str]:
    """Read the known centre codes from the bundled ``centres.csv``."""
    with (DATA_DIR / "centres.csv").open(encoding="utf-8", newline="") as file:
        return [row["centre_code"] for row in csv.DictReader(file)]


def load_staffing_rules() -> dict[tuple[str, str], tuple[int, int]]:
    """Read the bundled ``staffing_rules.csv``.

    Returns:
        A mapping of ``(activity, role)`` to
        ``(participants_per_staff, minimum_staff)``.
    """
    with (DATA_DIR / "staffing_rules.csv").open(encoding="utf-8", newline="") as file:
        return {
            (row["activity"], row["role"]): (
                int(row["participants_per_staff"]),
                int(row["minimum_staff"]),
            )
            for row in csv.DictReader(file)
        }


def build_staff(
    rng: random.Random,
    centre_codes: list[str],
) -> dict[tuple[str, str], list[StaffMember]]:
    """Create the fictional staff for every centre and role.

    Returns:
        Staff grouped by ``(centre_code, role)``.
    """
    names = [f"{first} {last}" for first in FIRST_NAMES for last in LAST_NAMES]
    rng.shuffle(names)

    staff: dict[tuple[str, str], list[StaffMember]] = {}
    number = 0
    for centre_code in centre_codes:
        for role, count in STAFF_PER_CENTRE.items():
            members = []
            for _ in range(count):
                number += 1
                members.append(
                    StaffMember(f"S-{number:03d}", names[number - 1], centre_code, role)
                )
            staff[(centre_code, role)] = members
    return staff


def plan_sessions(rng: random.Random, centre_codes: list[str]) -> list[PlannedSession]:
    """Create every session in the sample period with a random attendance."""
    sessions = []
    for day in sample_days():
        session_template, _ = templates_for(day)
        for centre_code in centre_codes:
            for activity, start, end in session_template:
                capacity = CAPACITY[activity]
                attendance = rng.randint(
                    round(capacity * LOWEST_ATTENDANCE_SHARE),
                    round(capacity * HIGHEST_ATTENDANCE_SHARE),
                )
                sessions.append(
                    PlannedSession(
                        centre_code,
                        activity,
                        day,
                        time.fromisoformat(start),
                        time.fromisoformat(end),
                        capacity,
                        attendance,
                    )
                )
    return sessions


def plan_shifts(
    rng: random.Random,
    centre_codes: list[str],
    sessions: list[PlannedSession],
    staff: dict[tuple[str, str], list[StaffMember]],
    rules: dict[tuple[str, str], tuple[int, int]],
) -> list[PlannedShift]:
    """Roster staff for every shift block, applying planned understaffing.

    Raises:
        ValueError: If a centre has too few staff in a role to fill a day.
    """
    shifts = []
    for day in sample_days():
        _, shift_template = templates_for(day)
        for centre_code in centre_codes:
            sessions_here = [
                session
                for session in sessions
                if session.day == day and session.centre_code == centre_code
            ]
            working_today: set[str] = set()
            for role, start_text, end_text in shift_template:
                start = time.fromisoformat(start_text)
                end = time.fromisoformat(end_text)
                needed = staff_needed(role, start, end, sessions_here, rules)
                needed -= planned_shortfall(centre_code, role, day, start_text)
                if needed > 0 and rng.random() < ABSENCE_CHANCE:
                    needed -= 1
                needed = max(needed, 0)

                available = [
                    member
                    for member in staff[(centre_code, role)]
                    if member.staff_id not in working_today
                ]
                if needed > len(available):
                    message = f"Not enough {role} staff at {centre_code} on {day}"
                    raise ValueError(message)
                for member in rng.sample(available, needed):
                    working_today.add(member.staff_id)
                    shifts.append(PlannedShift(member, day, start, end))
    return shifts


def staff_needed(
    role: str,
    start: time,
    end: time,
    sessions: list[PlannedSession],
    rules: dict[tuple[str, str], tuple[int, int]],
) -> int:
    """Work out how many staff a shift block needs.

    Returns:
        The largest requirement among the sessions the block fully covers, or
        ``UNRULED_ROLE_STAFF`` for a role that no staffing rule mentions.
    """
    if not any(rule_role == role for _, rule_role in rules):
        return UNRULED_ROLE_STAFF

    needed = 0
    for session in sessions:
        rule = rules.get((session.activity, role))
        if rule is None or not (start <= session.start and session.end <= end):
            continue
        participants_per_staff, minimum_staff = rule
        required = max(
            minimum_staff,
            math.ceil(session.attendance / participants_per_staff),
        )
        needed = max(needed, required)
    return needed


def planned_shortfall(centre_code: str, role: str, day: date, start: str) -> int:
    """Return how many staff the deliberate understaffing removes from a block."""
    for (
        pattern_centre,
        pattern_role,
        weekdays,
        pattern_start,
        removed,
    ) in UNDERSTAFFING_PATTERNS:
        if (
            pattern_centre == centre_code
            and pattern_role == role
            and day.weekday() in weekdays
            and pattern_start == start
        ):
            return removed
    return 0


def sample_days() -> list[date]:
    """List every date in the sample period, in order."""
    return [FIRST_DAY + timedelta(days=offset) for offset in range(NUMBER_OF_DAYS)]


def templates_for(
    day: date,
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Return the session and shift templates for the type of day."""
    match day.weekday():
        case 5:
            return SATURDAY_SESSIONS, SATURDAY_SHIFTS
        case 6:
            return SUNDAY_SESSIONS, SUNDAY_SHIFTS
        case _:
            return WEEKDAY_SESSIONS, WEEKDAY_SHIFTS


def format_session_rows(sessions: list[PlannedSession]) -> list[list[str]]:
    """Sort sessions, assign session IDs and format them as CSV fields."""
    ordered = sorted(
        sessions,
        key=lambda session: (
            session.day,
            session.centre_code,
            session.start,
            session.activity,
        ),
    )
    return [
        [
            f"SE-{number:05d}",
            session.centre_code,
            session.activity,
            session.day.strftime(DATE_FORMAT),
            session.start.strftime(TIME_FORMAT),
            session.end.strftime(TIME_FORMAT),
            str(session.capacity),
            str(session.attendance),
        ]
        for number, session in enumerate(ordered, start=1)
    ]


def format_roster_rows(shifts: list[PlannedShift]) -> list[list[str]]:
    """Sort shifts, assign shift IDs and format them as CSV fields."""
    ordered = sorted(
        shifts,
        key=lambda shift: (
            shift.day,
            shift.staff.centre_code,
            shift.start,
            shift.staff.role,
            shift.staff.staff_id,
        ),
    )
    return [
        [
            f"SH-{number:05d}",
            shift.staff.centre_code,
            shift.staff.staff_id,
            shift.staff.staff_name,
            shift.staff.role,
            shift.day.strftime(DATE_FORMAT),
            shift.start.strftime(TIME_FORMAT),
            shift.end.strftime(TIME_FORMAT),
        ]
        for number, shift in enumerate(ordered, start=1)
    ]


def plant_roster_problems(rows: list[list[str]]) -> list[list[str]]:
    """Return a copy of the roster rows with the deliberate bad rows planted.

    Comments give the case number from section 4.4 of the project brief.
    An empty list is written as a blank line.
    """
    rows = [row.copy() for row in rows]
    column = ROSTER_COLUMNS.index

    rows[10][column("staff_id")] = ""  # 1: required field blank
    rows[25][column("shift_date")] = "31/11/2026"  # 2: impossible date
    rows[40][column("start_time")] = "25:00"  # 4: unreadable time
    swap_times(rows[55], column("start_time"), column("end_time"))  # 5
    rows[70][column("centre_code")] = "XYZ"  # 9: unknown centre
    rows[85][column("role")] = "cleaner"  # 10: unknown role
    rows[120] = rows[120][:6]  # 12: wrong number of columns
    messy = rows[130]  # 13: stray whitespace and capitals
    messy[column("role")] = f" {messy[column('role')].capitalize()} "
    messy[column("centre_code")] = messy[column("centre_code")].lower()
    rows[160][column("shift_date")] = "05/11/26"  # 3: two-digit year

    # Insertions run from the end so earlier positions stay valid.
    rows.insert(301, rows[100].copy())  # 11: duplicate shift ID
    rows.insert(151, [])  # 14: blank line
    return rows


def plant_session_problems(rows: list[list[str]]) -> list[list[str]]:
    """Return a copy of the session rows with the deliberate bad rows planted.

    Comments give the case number from section 4.4 of the project brief.
    An empty list is written as a blank line.
    """
    rows = [row.copy() for row in rows]
    column = SESSION_COLUMNS.index

    rows[12][column("activity")] = ""  # 1: required field blank
    rows[30][column("session_date")] = "next tues"  # 4: unreadable date
    swap_times(rows[45], column("start_time"), column("end_time"))  # 5
    rows[60][column("attendance")] = "twelve"  # 6: non-numeric number
    rows[75][column("attendance")] = "-3"  # 7: negative number
    over_capacity = int(rows[90][column("capacity")]) + 7
    rows[90][column("attendance")] = str(over_capacity)  # 8: above capacity
    rows[105][column("activity")] = "aqua_zumba"  # 10: unknown activity
    rows[120].append("extra")  # 12: wrong number of columns
    messy = rows[135]  # 13: stray whitespace and capitals
    messy[column("activity")] = f" {messy[column('activity')].title()} "

    # Insertions run from the end so earlier positions stay valid.
    rows.insert(221, [])  # 14: blank line
    rows.insert(201, rows[180].copy())  # 11: duplicate session ID
    return rows


def swap_times(row: list[str], start_column: int, end_column: int) -> None:
    """Swap a row's start and end times so that it ends before it starts."""
    row[start_column], row[end_column] = row[end_column], row[start_column]


def write_csv(
    path: Path,
    header: list[str],
    rows: list[list[str]],
    *,
    excel_export: bool = False,
) -> None:
    """Write rows to a CSV file.

    Args:
        path: File to write.
        header: Column names for the first line.
        rows: Data rows; an empty row is written as a blank line.
        excel_export: Write a byte-order mark and Windows line endings, as
            Excel does, instead of plain UTF-8 with LF line endings.
    """
    encoding = "utf-8-sig" if excel_export else "utf-8"
    line_ending = "\r\n" if excel_export else "\n"
    with path.open("w", encoding=encoding, newline="") as file:
        writer = csv.writer(file, lineterminator=line_ending)
        writer.writerow(header)
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
