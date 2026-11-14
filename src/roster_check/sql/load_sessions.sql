INSERT INTO sessions (
    session_id, centre_code, activity, session_date, start_time,
    end_time, capacity, attendance, line_number
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
