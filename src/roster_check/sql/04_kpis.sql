-- The figures shown in the report, one view per report section.

CREATE VIEW report_kpis AS
SELECT
    (SELECT COUNT(*) FROM session_shortfall) AS sessions_analysed,
    (SELECT COUNT(*) FROM session_shortfall WHERE shortfall > 0) AS understaffed_sessions,
    (
        SELECT CAST(COALESCE(SUM(date_diff('minute', start_time, end_time)), 0) AS DOUBLE) / 60
        FROM shifts
    ) AS staff_hours,
    (SELECT CAST(COALESCE(SUM(attendance), 0) AS INTEGER) FROM sessions) AS total_attendance,
    (SELECT COUNT(*) FROM rejections) AS rows_rejected,
    (SELECT MIN(session_date) FROM sessions) AS period_start,
    (SELECT MAX(session_date) FROM sessions) AS period_end;

CREATE VIEW report_centres AS
SELECT
    centres.centre_code,
    centres.centre_name,
    COUNT(session_shortfall.session_id) AS sessions,
    COUNT(session_shortfall.session_id) FILTER (
        WHERE session_shortfall.shortfall > 0
    ) AS understaffed_sessions
FROM centres
LEFT JOIN session_shortfall ON session_shortfall.centre_code = centres.centre_code
GROUP BY centres.centre_code, centres.centre_name
ORDER BY centres.centre_code;

-- Each session is placed in the hour it starts (brief 5.2). Monday is 0.
CREATE VIEW report_heatmap AS
SELECT
    isodow(session_date) - 1 AS weekday,
    hour(start_time) AS hour,
    COUNT(*) AS sessions,
    COUNT(*) FILTER (WHERE shortfall > 0) AS understaffed_sessions,
    CAST(SUM(shortfall) AS INTEGER) AS shortfall
FROM session_shortfall
GROUP BY weekday, hour
ORDER BY weekday, hour;

CREATE VIEW report_daily AS
WITH attendance_by_day AS (
    SELECT session_date AS day, SUM(attendance) AS attendance
    FROM sessions
    GROUP BY session_date
),
hours_by_day AS (
    SELECT
        shift_date AS day,
        CAST(SUM(date_diff('minute', start_time, end_time)) AS DOUBLE) / 60 AS staff_hours
    FROM shifts
    GROUP BY shift_date
)
SELECT
    COALESCE(attendance_by_day.day, hours_by_day.day) AS day,
    CAST(COALESCE(attendance_by_day.attendance, 0) AS INTEGER) AS attendance,
    COALESCE(hours_by_day.staff_hours, 0.0) AS staff_hours
FROM attendance_by_day
FULL OUTER JOIN hours_by_day ON hours_by_day.day = attendance_by_day.day
ORDER BY day;

-- Ranked by shortfall, then attendance, then date, start time and session ID,
-- so ties always appear in the same order (brief 5.2).
CREATE VIEW report_worst_sessions AS
SELECT
    session_shortfall.session_id,
    session_shortfall.session_date,
    centres.centre_name,
    session_shortfall.activity,
    session_shortfall.start_time,
    session_shortfall.end_time,
    session_shortfall.attendance,
    session_shortfall.shortfall
FROM session_shortfall
JOIN centres ON centres.centre_code = session_shortfall.centre_code
WHERE session_shortfall.shortfall > 0
ORDER BY
    session_shortfall.shortfall DESC,
    session_shortfall.attendance DESC,
    session_shortfall.session_date,
    session_shortfall.start_time,
    session_shortfall.session_id
LIMIT 10;

-- The roles that were short in each of the worst sessions.
CREATE VIEW report_worst_roles AS
SELECT
    role_shortfall.session_id,
    role_shortfall.role,
    role_shortfall.required,
    role_shortfall.present
FROM role_shortfall
JOIN report_worst_sessions
    ON report_worst_sessions.session_id = role_shortfall.session_id
WHERE role_shortfall.shortfall > 0
ORDER BY role_shortfall.session_id, role_shortfall.role;

-- The staffing rules, for the table in the report footer.
CREATE VIEW report_rules AS
SELECT activity, role, participants_per_staff, minimum_staff
FROM rules
ORDER BY activity, role;
