-- Staff present for each session and role (brief 4.6). A staff member counts
-- when a single shift on the same date, at the same centre, in the right role,
-- fully covers the session. Staff are counted once however many of their
-- shifts cover the session, and a shift may count towards concurrent sessions.

CREATE VIEW staff_present AS
SELECT
    required_staff.session_id,
    required_staff.role,
    CAST(COUNT(DISTINCT shifts.staff_id) AS INTEGER) AS present
FROM required_staff
JOIN sessions ON sessions.session_id = required_staff.session_id
LEFT JOIN shifts
    ON shifts.shift_date = sessions.session_date
    AND shifts.centre_code = sessions.centre_code
    AND shifts.role = required_staff.role
    AND shifts.start_time <= sessions.start_time
    AND shifts.end_time >= sessions.end_time
GROUP BY required_staff.session_id, required_staff.role;
