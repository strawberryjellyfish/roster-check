-- Staff each session needs in each role it has a rule for (brief 4.6):
-- max(minimum_staff, ceil(attendance / participants_per_staff)).

CREATE VIEW required_staff AS
SELECT
    sessions.session_id,
    rules.role,
    GREATEST(
        rules.minimum_staff,
        CAST(
            CEIL(sessions.attendance / CAST(rules.participants_per_staff AS DOUBLE))
            AS INTEGER
        )
    ) AS required
FROM sessions
JOIN rules ON rules.activity = sessions.activity;
