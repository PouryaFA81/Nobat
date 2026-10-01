-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Working hours (clinic default + per-staff override) and blocked/holiday days.
-- doctor_id = 0 means clinic-wide (not a user FK).
-- Default window 06:00–24:00 matches the historical hour picker (starts 06..23).

CREATE TABLE IF NOT EXISTS working_hours (
    doctor_id  INTEGER NOT NULL PRIMARY KEY,  -- 0 = clinic default
    start_time TEXT NOT NULL DEFAULT '06:00', -- HH:MM inclusive
    end_time   TEXT NOT NULL DEFAULT '24:00'  -- HH:MM; appointment must finish by this
);

CREATE TABLE IF NOT EXISTS blocked_days (
    id         INTEGER PRIMARY KEY,
    day        TEXT NOT NULL,                 -- Gregorian YYYY-MM-DD
    doctor_id  INTEGER NOT NULL DEFAULT 0,    -- 0 = all staff
    reason     TEXT NOT NULL DEFAULT '',
    UNIQUE (day, doctor_id)
);

INSERT OR IGNORE INTO working_hours (doctor_id, start_time, end_time)
VALUES (0, '06:00', '24:00');
