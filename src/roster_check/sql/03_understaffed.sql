-- Shortfall for each session and role, and for each session as a whole.
-- A session is understaffed when its shortfall is greater than 0.

CREATE VIEW role_shortfall AS
SELECT
    required_staff.session_id,
    required_staff.role,
    required_staff.required,
    staff_present.present,
    GREATEST(required_staff.required - staff_present.present, 0) AS shortfall
FROM required_staff
JOIN staff_present
    ON staff_present.session_id = required_staff.session_id
    AND staff_present.role = required_staff.role;

CREATE VIEW session_shortfall AS
SELECT
    sessions.session_id,
    sessions.centre_code,
    sessions.activity,
    sessions.session_date,
    sessions.start_time,
    sessions.end_time,
    sessions.attendance,
    CAST(SUM(role_shortfall.shortfall) AS INTEGER) AS shortfall
FROM sessions
JOIN role_shortfall ON role_shortfall.session_id = sessions.session_id
GROUP BY
    sessions.session_id,
    sessions.centre_code,
    sessions.activity,
    sessions.session_date,
    sessions.start_time,
    sessions.end_time,
    sessions.attendance;
