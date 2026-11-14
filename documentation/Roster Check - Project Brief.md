# Roster Check: Project Brief

**Author:** Robert Miller
**Date:** 14 November 2026
**Status:** Ready to build

---

## 1. The idea in one paragraph

Roster Check is a small Python command-line tool for a fictional multi-site recreation organisation, "Riverbend Community Recreation". It reads two CSV exports that a centre would plausibly have lying around (a staff roster and a list of programme sessions with attendance), loads them into DuckDB, and uses plain SQL to find sessions that were understaffed against simple staffing ratios. It then writes a single, self-contained HTML report that a centre manager can open in any browser: headline numbers, animated charts, the worst understaffed sessions, and a clear "data problems" section that lists every CSV row it could not use and why. An optional `--summarise` flag asks Claude to write a short plain-English summary of the findings when an API key is available, and is skipped cleanly when it is not.

It runs with almost no setup: `uv run roster-check` (or `pip install .` then `roster-check`). No Docker, no cloud account, no API key required. All data is fake.

## 2. Purpose

Roster Check is a worked example of building a small, well-tested data tool with AI coding agents, Python and SQL. It mirrors, at a deliberately small scope, the pipeline shape of a common modern data stack such as BigQuery, Airbyte, Dagster, Cube and Evidence.dev:

| Modern data stack | Roster Check equivalent |
|---|---|
| Airbyte (extract and load) | CSV ingest with row-level validation |
| BigQuery (warehouse, SQL) | DuckDB with plain `.sql` files |
| Dagster (orchestrated steps) | A small, ordered pipeline of pure functions |
| Cube (metrics layer) | One SQL file that defines the KPIs |
| Evidence.dev (reports from SQL) | A generated HTML report for a non-technical reader |

It is also meant to demonstrate:

- **Python and SQL**, used properly and tested.
- **Automating a manual check.** Someone at a real centre eyeballs rosters against bookings every week. This does it in a second.
- **Data quality thinking.** Bad rows are expected, handled, and shown to the user instead of silently dropped.
- **Writing for non-technical people.** The output is a one-page report for a centre manager, not a terminal dump.
- **Working with AI coding tools in a disciplined way.** One feature per branch, tests before merge, CI, and automated review (CodeRabbit). The README will say plainly how Claude Code was used.
- **Sensible AI use.** The Claude summary is optional, sends only aggregated numbers (no names), and never breaks the tool if it fails.

The domain (recreation centres, swim lessons, gym supervision) is a generic community recreation setting. The organisation and all of its data are invented.

## 3. Technology stack

Keep dependencies few and boring.

| Purpose | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | CI tests 3.11, 3.12 and 3.13 |
| Packaging and running | `uv` with `pyproject.toml` and a committed `uv.lock` | `pip install .` must also work |
| Database | `duckdb` (in-memory) | No server, no files left behind |
| Templating | `jinja2` | One HTML template, CSS and JS inlined at render time |
| Charts | Hand-built inline SVG from Python | No chart library, no CDN, works offline, easy to test |
| CLI | `argparse` (standard library) | No extra dependency |
| Optional AI summary | `anthropic` SDK, as an optional extra `roster-check[ai]` | Only imported when `--summarise` is used |
| Tests | `pytest`, `pytest-cov` | Coverage gate in CI |
| Lint and format | `ruff` (check and format) | Enforced in CI |
| CI | GitHub Actions | Runs on every push and pull request |
| Code review | CodeRabbit | Reviews every pull request |
| Licence | MIT | `LICENSE` file in the repository root, declared in `pyproject.toml` |

Runtime dependencies are only `duckdb` and `jinja2`. Everything else is dev-only or optional.

## 4. The data

All data is invented. Staff names come from a fixed list of obviously fictional names, IDs are synthetic, and there are no phone numbers, emails or addresses anywhere.

The sample data covers **4 centres over 2 weeks** (288 sessions and 563 shifts, from Monday 2 to Sunday 15 November 2026), which is enough to make the charts interesting but small enough to read.

Centres: `RBC` Riverbend Central, `NTH` Northgate, `HLS` Hillside, `LKV` Lakeview. These are held as reference data in `centres.csv` (see 4.3).

The organisation is Australian, so dates in the CSV files are normally written `DD/MM/YYYY`, as an Australian Excel export would produce. Accepted formats are set out in 4.5.

### 4.1 `rosters.csv`: who was rostered on

| Column | Type | Example | Rules |
|---|---|---|---|
| `shift_id` | text | `SH-00412` | Required, unique |
| `centre_code` | text | `RBC` | Required, must be a known centre |
| `staff_id` | text | `S-017` | Required |
| `staff_name` | text | `Jordan Placeholder` | Optional, never sent to the AI |
| `role` | text | `lifeguard` | Required, one of `lifeguard`, `swim_instructor`, `gym_supervisor`, `group_fitness`, `front_desk` |
| `shift_date` | date | `03/11/2026` | Required, format as in 4.5 |
| `start_time` | time | `06:00` | Required, 24-hour, format as in 4.5 |
| `end_time` | time | `10:30` | Required, after `start_time` |

### 4.2 `sessions.csv`: what was running and who came

| Column | Type | Example | Rules |
|---|---|---|---|
| `session_id` | text | `SE-00131` | Required, unique |
| `centre_code` | text | `NTH` | Required, must be a known centre |
| `activity` | text | `swim_lesson` | Required, must exist in the staffing rules |
| `session_date` | date | `04/11/2026` | Required, format as in 4.5 |
| `start_time` | time | `16:00` | Required, 24-hour, format as in 4.5 |
| `end_time` | time | `16:45` | Required, after `start_time` |
| `capacity` | integer | `24` | Required, greater than 0 |
| `attendance` | integer | `19` | Required, 0 or more |

### 4.3 Reference data: `staffing_rules.csv` and `centres.csv`

These two small files are version-controlled reference data. Keeping them as data rather than code means the SQL stays generic and a manager could change a ratio or add a centre without touching Python.

They pass through the same ingest and validation as the other CSVs, but any bad row in either file is fatal (exit code 2), with a message naming the file, line and problem. Reference data must be fully correct before any analysis can be trusted.

`centres.csv` lists the known centres:

| `centre_code` | `centre_name` |
|---|---|
| `RBC` | Riverbend Central |
| `NTH` | Northgate |
| `HLS` | Hillside |
| `LKV` | Lakeview |

`staffing_rules.csv` says how many of which role each activity needs:

| `activity` | `role` | `participants_per_staff` | `minimum_staff` |
|---|---|---|---|
| `swim_lesson` | `swim_instructor` | 8 | 1 |
| `swim_lesson` | `lifeguard` | 30 | 1 |
| `lap_swim` | `lifeguard` | 25 | 1 |
| `gym_floor` | `gym_supervisor` | 25 | 1 |
| `group_fitness` | `group_fitness` | 30 | 1 |

`participants_per_staff` must be a whole number greater than 0, and `minimum_staff` a whole number of 0 or more. Any other value, including a blank, zero or negative ratio, is a fatal reference-data error, so the required-staff calculation can never divide by zero.

How these rules are applied is set out in 4.6.

### 4.4 Deliberate bad data and how each case is handled

The sample CSVs contain about 20 bad rows spread across both files, so the "data problems" section of the report is always populated in the demo. Every row-level case (1 to 14) appears in the sample, and case 15 is covered by writing `rosters.csv` as an Excel export. Cases 16 to 18 would stop the sample run from producing a report, so they are covered by fixtures in `tests/fixtures/` instead. Each case below has its own test.

Rows fall into three outcomes:

- **Rejected:** the row is excluded and listed in the report with file, line number, the raw text, and a plain-English reason.
- **Fixed with a warning:** the row is cleaned, used, and listed in a collapsible "auto-fixed" list.
- **Fatal:** the whole file cannot be used. The tool prints a clear message and exits with code 2. No report is written.

| # | Case | Example | Outcome | Reason shown to the user |
|---|---|---|---|---|
| 1 | Required field blank | `staff_id` is empty | Rejected | "Missing staff ID" |
| 2 | Impossible date | `2026-02-30` | Rejected | "Date 2026-02-30 does not exist" |
| 3 | Two-digit year | `04/11/26` | Rejected | "Could not read session date '04/11/26'" |
| 4 | Unreadable date or time | `next tues`, `25:00` | Rejected | "Could not read start time '25:00'" |
| 5 | End before start | `start 14:00, end 09:00` | Rejected | "Shift ends before it starts" |
| 6 | Non-numeric number | `attendance = twelve` | Rejected | "Attendance 'twelve' is not a number" |
| 7 | Negative number | `attendance = -3` | Rejected | "Attendance cannot be negative" |
| 8 | Attendance over capacity | `31` of `24` | Kept, flagged | "Attendance is above capacity (31 of 24)" |
| 9 | Unknown centre | `centre_code = XYZ` | Rejected | "Unknown centre 'XYZ'" |
| 10 | Unknown role or activity | `role = cleaner` | Rejected | "Unknown role 'cleaner'" |
| 11 | Duplicate ID | second `SH-00412` | First kept, later rejected | "Duplicate shift ID, first seen on line 88" |
| 12 | Wrong number of columns | 6 fields instead of 8 | Rejected | "Expected 8 columns, found 6" |
| 13 | Stray whitespace or case | `" Lifeguard "`, `rbc` | Fixed with warning | "Cleaned spacing and capitals" |
| 14 | Blank line | empty line mid-file | Silently skipped | Not shown (counted in the log) |
| 15 | Byte-order mark or Windows line endings | Excel export | Handled silently | Not shown |
| 16 | Missing or renamed header column | `staffid` instead of `staff_id` | Fatal | "rosters.csv is missing column 'staff_id'" |
| 17 | File missing or empty | | Fatal | "rosters.csv not found" or "has no rows" |
| 18 | Every row rejected | | Report still renders | Banner: "No usable rows in sessions.csv" |

The tool must never crash with a Python traceback on bad input. Any unexpected error is caught at the top level, reported in one line, and exits with code 1. `--debug` shows the traceback.

### 4.5 Validation and cleaning rules

- **Dates.** `DD/MM/YYYY` (single-digit day or month allowed) and `YYYY-MM-DD` are both normal formats and are accepted without a warning. US-style `MM/DD/YYYY` is never assumed: `11/30/2026` is rejected as a date that does not exist (case 2). Two-digit years are rejected (case 3).
- **Times.** `HH:MM`, `H:MM` and `HH:MM:00` are accepted without a warning. Anything else is rejected, including `24:00`. Shifts and sessions never cross midnight.
- **Cleaning (case 13).** Every field has surrounding spaces removed. Centre codes and IDs are converted to upper case; roles and activities to lower case. Staff names are only trimmed. A row changed by cleaning gets one "Cleaned spacing and capitals" warning.
- **Several problems in one row.** Only the first problem is reported, checking columns from left to right, so each rejected row has one clear reason.
- **Duplicate IDs (case 11).** The first row with an ID claims it, even if that row is rejected for another reason. Later rows with the same ID are rejected.
- **Headers.** Column names are matched ignoring case and surrounding spaces, and columns may appear in any order. Extra columns are ignored and noted once in the terminal summary. The column count check (case 12) compares each row with the header.
- **Encoding.** Files are read as UTF-8, with or without a byte-order mark. If that fails, the file is read as Windows-1252 and a one-line note is added to the terminal summary.

### 4.6 How understaffing is calculated

- **Required staff** for a session and role = `max(minimum_staff, ceil(attendance / participants_per_staff))`.
- **Who counts.** A staff member counts towards a session when a single shift on the same date, at the same centre, in the right role, fully covers the session's time window. Two back-to-back shifts that only cover it together do not count.
- **Distinct staff.** Staff present are counted by distinct `staff_id`, so overlapping shifts for one person never count them twice.
- **Concurrent sessions.** Each session is assessed on its own. A staff member whose shift covers two sessions running at the same time counts towards both. This is a known simplification, stated in the report footer.
- **Shortfall.** For each session, the sum over its roles of `max(0, required - present)`. A session is understaffed when its shortfall is greater than 0.
- **Staff hours** count every valid shift in every role, including `front_desk`.

## 5. The HTML report

### 5.1 Principles

- **One file, fully self-contained.** All CSS, JS and SVG is inlined. No external requests of any kind, so it works offline, by email attachment, or from a USB stick. A test enforces this.
- **One page.** Designed to read top to bottom on a laptop screen, and to print on one A4 page landscape via print CSS (animations off, details collapsed).
- **Appealing but calm.** A clean card layout, a restrained palette with one accent colour, good typography from the system font stack, and light and dark mode via `prefers-color-scheme`.
- **Animated where it helps.** Animations make the report feel alive on first open but never hide information.
- **Accessible.** Every chart has a text alternative and a visible data table nearby. Colour is never the only signal. `prefers-reduced-motion` turns all animation off.
- **Australian dates.** Dates are shown with the month spelled out, for example "Tue 4 Nov 2026", so they cannot be misread whichever date convention the reader is used to.

### 5.2 Sections, top to bottom

1. **Header.** Organisation name, date range covered, when the report was generated, and a data-quality badge ("All rows used" in green, or "14 rows need attention" in amber, linking to the Data problems section, item 8 below).
2. **Headline numbers (KPI tiles).** Sessions analysed; understaffed sessions (count and percent); total staff hours rostered; total attendance; rows rejected. Numbers count up from zero on load.
3. **Summary.** If `--summarise` ran, Claude's 3 to 5 sentence summary in a highlighted panel, labelled as AI-generated. Otherwise a short rule-based summary built from the numbers, so the report never looks empty.
4. **Understaffed sessions by centre.** Horizontal bar chart, one bar per centre, bars grow in on load with a slight stagger. Shows both the count and the percentage of that centre's sessions.
5. **When the gaps happen.** Heatmap of day of week (rows) by hour of day (columns), cell shade showing the staff shortfall. Each session is placed in the hour it starts, and a cell's value is the total shortfall of the sessions starting in that day and hour. Cells fade in. Hovering a cell shows the exact numbers (native SVG `<title>` tooltip, no library).
6. **Attendance versus staffing over time.** Daily line chart with two lines (total attendance, and total staff hours scaled to a second axis or shown as bars). Lines draw themselves on load using the SVG stroke-dash technique.
7. **Worst ten understaffed sessions.** A table: date, centre, activity, time, attendance, and the shortfall in plain words ("Needs 3 swim instructors, had 1"). Shortfall shown with a small inline bar. Ranked by shortfall (highest first), then attendance (highest first), then date, start time and session ID, so ties always appear in the same order.
8. **Data problems.** Grouped by file. A table of rejected rows with line number, reason, and the raw row text in monospace so the user can find and fix it in their spreadsheet. A collapsible "auto-fixed" list beneath. If there are no problems, a short green "All rows were usable" message.
9. **Footer.** How the numbers were calculated (one short paragraph plus the staffing rules table, including the concurrent-sessions simplification from 4.6), tool version, and "All data in this report is fictional."

### 5.3 How the visuals are built

- Charts are produced by small pure Python functions in `charts.py` that take plain data and return an SVG string. This makes them unit-testable (valid XML, correct number of bars, widths proportional to values) and keeps the report dependency-free.
- Animation is CSS first: `@keyframes` for bar growth (`transform: scaleX`), fade-ins with staggered `animation-delay`, and line drawing via `stroke-dashoffset`. The only JavaScript is a tiny inline script (under 40 lines) for KPI count-ups and an `IntersectionObserver` so charts animate when scrolled into view. With JavaScript disabled, every number and chart still shows its final state.
- Colours are defined once as CSS custom properties, with a dark-mode override.

## 6. Architecture

A linear pipeline of small modules, each with one job and its own tests. Data flows one way; no module reaches back into an earlier one.

```
CSV files ──► ingest ──► validate ──► db (DuckDB) ──► analysis (SQL) ──► charts ──► report ──► report.html
                              │                                               ▲
                              └──────────── rejected rows ────────────────────┘
                                                         summarise (optional) ─┘
```

Rejected rows are also loaded into DuckDB as a `rejections` table, so that `--db-file` saves them alongside the cleaned data (see 9.1).

### 6.1 Repository layout

```
roster-check/
├── pyproject.toml
├── uv.lock
├── README.md
├── LICENSE                       # MIT
├── CLAUDE.md                     # rules for the coding agent (see section 8)
├── .coderabbit.yaml
├── .github/
│   ├── workflows/ci.yml
│   └── pull_request_template.md
├── scripts/
│   └── make_sample_data.py       # seeded generator, plus the fixed list of bad rows
├── dashboard/                    # STRETCH (M9): optional Evidence.dev project, needs Node
│   ├── package.json
│   ├── sources/roster_check/     # DuckDB connection to the --db-file output
│   └── pages/index.md
├── src/roster_check/
│   ├── __init__.py               # __version__, read from installed package metadata
│   ├── __main__.py               # python -m roster_check
│   ├── cli.py                    # argparse, exit codes, top-level error handling
│   ├── models.py                 # dataclasses: see 6.2.1
│   ├── data/                     # bundled data, loaded with importlib.resources
│   │   ├── centres.csv
│   │   ├── staffing_rules.csv
│   │   └── sample/
│   │       ├── rosters.csv
│   │       └── sessions.csv
│   ├── ingest.py                 # read raw CSV text, keep line numbers, header checks
│   ├── validate.py               # per-field parsers and row rules -> (valid, rejected, warnings)
│   ├── db.py                     # DuckDB connection, load tables, run a .sql file
│   ├── sql/
│   │   ├── 01_required_staff.sql
│   │   ├── 02_staff_on_session.sql
│   │   ├── 03_understaffed.sql
│   │   └── 04_kpis.sql
│   ├── analysis.py               # runs the SQL, returns a ReportData dataclass
│   ├── charts.py                 # pure functions -> SVG strings
│   ├── summarise.py              # optional Claude summary, never raises
│   ├── report.py                 # Jinja2 render, inlines CSS/JS
│   └── templates/
│       ├── report.html.j2
│       ├── report.css
│       └── report.js
└── tests/
    ├── conftest.py
    ├── fixtures/                 # tiny CSVs, one per bad-data case
    ├── test_ingest.py
    ├── test_validate.py
    ├── test_db.py
    ├── test_sql.py
    ├── test_analysis.py
    ├── test_charts.py
    ├── test_summarise.py
    ├── test_report.py
    └── test_cli.py
```

### 6.2 Module contracts

| Module | Input | Output | Notes |
|---|---|---|---|
| `ingest` | file path | header plus list of `(line_number, raw_text, fields)` | Handles BOM, line endings, blank lines. Raises `InputError` for fatal cases. |
| `validate` | raw rows, known centres, rules | `ValidationResult(valid, rejected, warnings)` | Pure functions, no I/O. One parser per field type. |
| `db` | valid rows, rejections | DuckDB connection with `shifts`, `sessions`, `rules`, `rejections` tables | Uses explicit column types. Reads SQL files via `importlib.resources`. |
| `analysis` | connection | `ReportData` dataclass | All numbers the report needs, nothing else. |
| `charts` | plain lists and dicts | SVG strings | No DuckDB, no Jinja. |
| `summarise` | `ReportData` | `str` or `None` | Sends aggregates only. Returns `None` on any failure. |
| `report` | `ReportData`, charts, rejections, summary | HTML string | Writing to disk happens in `cli`. |
| `cli` | argv | exit code | The only module that prints or touches the filesystem for output. |

### 6.2.1 Data structures

Defined in `models.py` as frozen dataclasses. Field names follow the CSV columns in section 4; dates and times are `datetime.date` and `datetime.time` values.

| Dataclass | Fields |
|---|---|
| `Shift` | `shift_id`, `centre_code`, `staff_id`, `staff_name` (`str \| None`), `role`, `shift_date`, `start_time`, `end_time`, `line_number` |
| `Session` | `session_id`, `centre_code`, `activity`, `session_date`, `start_time`, `end_time`, `capacity`, `attendance`, `line_number` |
| `StaffingRule` | `activity`, `role`, `participants_per_staff`, `minimum_staff` |
| `Centre` | `centre_code`, `centre_name` |
| `Rejection` | `file_name`, `line_number`, `raw_text`, `reason` |
| `RowWarning` | `file_name`, `line_number`, `raw_text`, `reason` |

`RowWarning` is named to avoid clashing with Python's built-in `Warning` class. `ReportData` is defined at the start of M3, when the analysis outputs are built, and confirmed before use.

### 6.3 Command line

```
roster-check [--rosters PATH] [--sessions PATH] [--rules PATH]
             [--out PATH] [--db-file PATH] [--summarise] [--strict] [--open]
             [--debug] [--version]
```

- With no arguments it uses the bundled sample data and writes `roster-check-report.html`, so the first run always works.
- `--strict` exits with code 1 if any row was rejected (useful in an automated pipeline).
- `--open` opens the report in the default browser.
- `--version` prints the tool version and exits. The version is defined once, in `pyproject.toml`, and `__init__.py` reads it with `importlib.metadata.version`.
- `--db-file PATH` saves the DuckDB database to a file instead of keeping it in memory. Off by default. It exists so the optional Evidence.dev dashboard (section 9.1) can read the same tables.
- Exit codes: `0` success, `1` unexpected error or `--strict` failure, `2` fatal input problem.
- Prints a short summary to the terminal: rows read, rows rejected, understaffed sessions, report path.

### 6.4 The optional Claude summary

- Enabled only by `--summarise`. If `ANTHROPIC_API_KEY` is not set or the `anthropic` package is not installed, print one line ("Skipping AI summary: no API key set") and continue.
- Uses the official `anthropic` Python SDK. Model is configurable with `ROSTER_CHECK_MODEL`, defaulting to `claude-opus-5-5`.
- The prompt contains only aggregated numbers and the top understaffed sessions (centre, activity, day, time, shortfall). No staff names or IDs are ever sent. A test asserts this.
- Short timeout, check `stop_reason` before reading the text, and treat any error as "no summary". The report notes when the summary was unavailable.
- Tests use a fake client. CI never calls the real API.

## 7. Testing strategy

The goal is that every feature is proven by tests before it is merged, and that the full suite runs in under 30 seconds with no network.

**Unit tests**

- `validate`: one parametrised test per bad-data case in section 4.4, asserting both the outcome and the exact reason text. Plus happy-path tests for each field parser.
- `ingest`: BOM, CRLF, blank lines, missing header column, empty file, missing file.
- `sql`: each SQL file run against a tiny hand-built DuckDB fixture with a known answer (for example, "8 swimmers and 1 instructor: not understaffed; 9 swimmers and 1 instructor: short by 1"). Edge cases: shift that only partly overlaps a session does not count; wrong centre does not count; zero attendance still needs the minimum staff.
- `charts`: output parses as XML, has the expected number of bars or cells, values map to proportional sizes, empty data returns a friendly "no data" SVG.
- `summarise`: skipped without a key; fake client success; fake client raising an error returns `None`; prompt contains no staff names.

**Integration and end-to-end tests**

- `report`: render with the sample data and check with Python's `html.parser` that every section exists, that there are no `http://` or `https://` resource references (`src`, `href` to stylesheets, `@import`), and that rejected rows appear with their line numbers.
- `cli`: run the real command through `subprocess` on the sample data and on each fatal fixture. Assert exit codes, terminal messages, that the report file is written, and that no traceback is ever printed without `--debug`.
- A golden test on the sample data's headline numbers (for example "37 understaffed sessions") so any accidental change in logic is caught.

**Quality gates**

- `ruff check` and `ruff format --check` must pass.
- Coverage must be at least 90 percent (`--cov-fail-under=90`).
- Tests must not depend on the current date, time zone or locale. Report "generated at" time is injectable for tests.

**Stretch (only if time allows):** a Playwright smoke test that opens the report in headless Chromium and checks there are no console errors.

### 7.1 GitHub Actions

`.github/workflows/ci.yml` runs on every push and every pull request:

- **Matrix:** Ubuntu with Python 3.11, 3.12 and 3.13, plus Windows and macOS on 3.12. This is what proves "runs flawlessly" on a reviewer's machine, whatever they use.
- **Steps:** checkout, `astral-sh/setup-uv`, `uv sync --locked --all-extras`, `uv run ruff check`, `uv run ruff format --check`, `uv run pytest --cov`, then run `uv run roster-check` on the sample data.
- **Artifact:** upload the generated sample report so a reviewer can download and open it straight from the pull request.
- Branch protection on `main` requires CI to pass before merging.

## 8. Development workflow

- **`main` is always green and always runnable.** Nobody (human or agent) commits directly to `main`.
- **One branch per feature,** named after its milestone, for example `feat/m2-validation`.
- **Self-contained commits.** Each commit holds one coherent change with its tests, and is only made once the tests for that change pass locally. Commit messages follow Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `ci:`, `chore:`).
- **One pull request per milestone.** The PR template asks: what changed, how it was tested, screenshots of the report if it changed, and anything the reviewer should look at closely.
- **CodeRabbit reviews every PR.** Its comments are either fixed in a new commit on the branch or answered with a reason. A `.coderabbit.yaml` gives it project-specific guidance (for example: "flag any network access in the report", "flag any staff name passed to summarise.py", "SQL must stay in `src/roster_check/sql/`").
- **Merge** with squash once CI is green and the review is resolved. Delete the branch.
- **`CLAUDE.md`** in the repo root tells the coding agent the rules above: stay inside the current milestone, write tests first or alongside, run `uv run pytest` and `uv run ruff check` before every commit, never commit to `main`, never add a runtime dependency without saying why, and keep all data fictional.
- **Honesty about AI use.** The README has a short "How this was built" section describing the Claude Code workflow, CodeRabbit review, and what the developer decided and checked personally.

## 9. Milestone plan

Each milestone is one branch and one pull request. Milestones are built in order and each is merged before the next begins. Phase 1 (M0 to M5) produces a working analysis and report; phase 2 (M6 to M8) adds the full command line, the optional AI summary and the release. M9 is a stretch goal, attempted only after M8.

| # | Milestone | Done when | Phase |
|---|---|---|---|
| M0 | **Project skeleton.** `pyproject.toml`, `uv.lock`, `LICENSE` (MIT), `src/` layout, ruff, pytest, CI workflow, `CLAUDE.md`, `.coderabbit.yaml`, PR template, a `roster-check --version` command with a test. | CI green on all five matrix jobs. | 1 |
| M1 | **Sample data.** `staffing_rules.csv`, `centres.csv`, seeded generator script, committed sample CSVs including every bad-data case in 4.4, a test that the generator is deterministic. | Sample files committed and documented in the README. | 1 |
| M2 | **Ingest and validation.** `models.py`, `ingest.py`, `validate.py` with every case in 4.4 tested. | Each bad-data case has a passing test with its exact message. | 1 |
| M3 | **DuckDB and SQL analysis.** `db.py`, the four SQL files, `analysis.py` returning `ReportData`, SQL tests with known answers, golden numbers for the sample data. | Correct understaffing results on fixtures and sample data. | 1 |
| M4 | **Charts.** Bar chart, heatmap, line chart and inline shortfall bars as SVG, with tests. | Charts render and are tested; a preview HTML shows them. | 1 |
| M5 | **HTML report.** Template, CSS, animations, dark mode, print styles, data problems section, accessibility, no-external-requests test. | Sample report looks finished in Chrome, Firefox and Safari. | 1 |
| M6 | **CLI and polish.** All flags, exit codes, terminal summary, top-level error handling, end-to-end tests, CI uploads the report artifact. | `uv run roster-check` works from a fresh clone on all CI platforms. | 2 |
| M7 | **Optional Claude summary.** `summarise.py`, `[ai]` extra, fake-client tests, privacy test. | Works with a key, skips cleanly without one. | 2 |
| M8 | **Release.** README with screenshot or GIF, quick start, how it works, "How this was built", how it would map to a BigQuery and Dagster setup (a short paragraph, not code). Tag `v1.0.0`. Optionally publish the sample report on GitHub Pages as a live example. | Public repository ready to share, with the README and live example in place. | 2 |
| M9 | **Stretch: Evidence.dev dashboard.** See 9.1. | `npm run dev` in `dashboard/` shows the dashboard from the sample data. | Stretch |

If scope needs to be reduced, cut in this order: the Evidence.dev dashboard (M9), GitHub Pages, the Playwright smoke test, the line chart (section 5.2 item 6), then M7. M0 to M6 on their own are a complete, credible project.

### 9.1 Stretch goal: Evidence.dev dashboard

Evidence.dev is a common tool for publishing reports from SQL, so a small dashboard built on the same data shows how the analysis carries over to a BI tool. It is strictly optional and kept apart from the core project.

- **Separate folder.** It lives in `dashboard/` with its own `package.json`. The Python tool never needs Node, and `uv run roster-check` works whether or not this folder is used. CI for the core project ignores it.
- **Same data, no duplication.** Running `roster-check --db-file roster_check.duckdb` saves the cleaned tables (`shifts`, `sessions`, `rules`, `rejections`) to a DuckDB file. Evidence's DuckDB source points at that file. The dashboard's queries reuse the same logic as `src/roster_check/sql/` (copied into Evidence `.sql` source queries, or written as views in the database file so the logic lives in one place; views are preferred).
- **Contents.** One page in Evidence Markdown: the KPI numbers, understaffed sessions by centre, a day-by-hour heatmap, a filterable table of understaffed sessions (dropdown for centre and activity), and the rejected rows table. Evidence's built-in components provide the charts and filters.
- **How it fits the story.** The HTML report is the zero-setup output for a centre manager. The Evidence dashboard shows the same analysis as an interactive BI page, which is how many data teams publish their work.
- **Testing.** One Python test checks that `--db-file` writes the expected tables and views. One extra, separate GitHub Actions job runs `npm ci` and `npm run build` in `dashboard/` so a broken dashboard is caught, without slowing or blocking the core matrix. Don't attempt more testing than that.
- **Done when.** `npm install && npm run sources && npm run dev` in `dashboard/` shows the dashboard from the sample data, and the README has a screenshot plus three lines of instructions.

### 9.2 Why Airbyte is left out

Airbyte is a common choice for the extract-and-load step, but it is deliberately not used here. It is built to sync data from many SaaS systems and databases into a warehouse, and self-hosting it means running a set of services in Docker or Kubernetes with several GB of memory. For two local CSV files that is far more machinery than the job needs, and it would break the "runs with almost no setup" goal. The README should say this in a sentence or two, and note that in a real deployment the `ingest` step is where Airbyte (or a similar connector) would plug in, landing the roster and booking exports in the warehouse before the same SQL runs.

## 10. Out of scope

To keep this finished and reliable, v1 does not include: a web server or dashboard app, a database file on disk by default (the optional `--db-file` flag exists only for the stretch dashboard), real integrations with rostering or booking systems, user accounts, scheduling, Docker, or Airbyte (see 9.2). The Evidence.dev dashboard is a stretch goal only (see 9.1). These can be mentioned in the README as natural next steps.

## 11. Definition of done for v1.0

- A fresh clone runs with `uv run roster-check` and produces the report in under five seconds, on Linux, macOS and Windows.
- CI is green on every matrix job; coverage is at least 90 percent; ruff is clean.
- Every bad-data case is handled without a traceback and shown in the report where relevant.
- The report is one self-contained file with no external requests, animated charts, a readable data problems section, and sensible print and reduced-motion behaviour.
- Every change reached `main` through a reviewed pull request.
- The README explains the project to a non-technical reader in the first screen.

## 12. Decision log

Decisions made after the first draft of this brief, before sample data and validation were built. Each is applied in the section shown, which is the authoritative wording.

| # | Decision | Reason | Section |
|---|---|---|---|
| D1 | Data structures defined as frozen dataclasses; `Warning` renamed `RowWarning`. `ReportData` deferred to the start of M3. | Code is written against agreed structures, not guesses. Avoids shadowing a Python built-in. | 6.2.1 |
| D2 | Known centres held in `centres.csv`. | Keeps reference data as data, like the staffing rules, and supplies centre names for the report. | 4.3 |
| D3 | A bad row in either reference file is fatal. | Analysis cannot be trusted if the rules or centres are wrong. | 4.3 |
| D4 | Only the first problem in a row is reported. | One clear, testable reason per row. | 4.5 |
| D5 | The first row with an ID claims it, even if rejected. | Nothing is silently kept in place of a bad row. | 4.5 |
| D6 | `DD/MM/YYYY` and `YYYY-MM-DD` are both normal date formats; US-style dates are never assumed; two-digit years are rejected. Report dates spell out the month. | The organisation is Australian and its exports use Australian dates. | 4.5, 5.1 |
| D7 | Cleaning trims all fields and normalises the case of codes, IDs, roles and activities. | Predictable matching against reference data without losing rows to formatting. | 4.5 |
| D8 | Headers matched ignoring case, spacing and order; extra columns ignored; UTF-8 with Windows-1252 fallback. | Tolerates common spreadsheet exports without guessing at content. | 4.5 |
| D9 | Each session is assessed on its own; concurrent sessions can share a staff member. | Keeps the SQL simple and close to real pool supervision practice. Stated in the report. | 4.6 |
| D10 | A single shift must fully cover a session. | Simple, testable rule; split shifts are rare. | 4.6 |
| D11 | Staff present are counted by distinct staff ID. | Overlapping shifts cannot double count one person. | 4.6 |
| D12 | Shortfall is summed across roles; the worst ten are ranked with a fixed tie-break order. | Deterministic results for tests and readers. | 4.6, 5.2 |
| D13 | Staff hours include every role. | "Rostered hours" means all rostered hours. | 4.6 |
| D14 | Heatmap places each session in its starting hour. | Every session appears exactly once. | 5.2 |
| D15 | Bundled data lives inside the package, in `src/roster_check/data/`. | `pip install .` includes it, so running with no arguments works after a normal install, not only from a clone. | 6.1 |
| D16 | The sample covers every row-level bad-data case; fatal cases 16 to 18 are covered by test fixtures. CSV files are stored byte for byte in git. | A fatal case in the sample would stop the demo report. Git line-ending conversion would otherwise remove case 15. | 4.4 |

### Still open

These are decided at the start of the milestone that needs them:

- The line chart's layout (5.2 item 6): second axis, bars, or two aligned charts. Before M4.
- The wording of the rule-based summary and the Claude prompt (5.2 item 3, 6.4). Before M5 and M7.
- CLI edge cases: overwriting an existing report, which exit code wins when `--strict` and a fatal error both apply, and `--open` when no browser is available. Before M6.
