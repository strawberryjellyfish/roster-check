INSERT INTO shifts (
    shift_id, centre_code, staff_id, staff_name, role,
    shift_date, start_time, end_time, line_number
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
