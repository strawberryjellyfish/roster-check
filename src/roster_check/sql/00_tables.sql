-- Tables for the validated input, loaded by db.py with bound parameters.
-- Column order matches the field order of the dataclasses in models.py.

CREATE TABLE centres (
    centre_code VARCHAR PRIMARY KEY,
    centre_name VARCHAR NOT NULL
);

CREATE TABLE rules (
    activity VARCHAR NOT NULL,
    role VARCHAR NOT NULL,
    participants_per_staff INTEGER NOT NULL,
    minimum_staff INTEGER NOT NULL,
    PRIMARY KEY (activity, role)
);

CREATE TABLE shifts (
    shift_id VARCHAR PRIMARY KEY,
    centre_code VARCHAR NOT NULL,
    staff_id VARCHAR NOT NULL,
    staff_name VARCHAR,
    role VARCHAR NOT NULL,
    shift_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    line_number INTEGER NOT NULL
);

CREATE TABLE sessions (
    session_id VARCHAR PRIMARY KEY,
    centre_code VARCHAR NOT NULL,
    activity VARCHAR NOT NULL,
    session_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    capacity INTEGER NOT NULL,
    attendance INTEGER NOT NULL,
    line_number INTEGER NOT NULL
);

CREATE TABLE rejections (
    file_name VARCHAR NOT NULL,
    line_number INTEGER NOT NULL,
    raw_text VARCHAR NOT NULL,
    reason VARCHAR NOT NULL
);
