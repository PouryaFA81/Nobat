-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Phase 4.4: soft waitlist queue; promote on appointment cancel.

CREATE TABLE IF NOT EXISTS waitlist (
    id                       INTEGER PRIMARY KEY,
    doctor_id                INTEGER NOT NULL REFERENCES users(id),
    day                      TEXT NOT NULL,
    preferred_time           TEXT NOT NULL DEFAULT '',
    duration_min             INTEGER NOT NULL DEFAULT 60,
    initials                 TEXT NOT NULL,
    note                     TEXT NOT NULL DEFAULT '',
    status                   TEXT NOT NULL DEFAULT 'waiting',
    created_by               INTEGER REFERENCES users(id),
    created_at               TEXT NOT NULL DEFAULT (datetime('now')),
    promoted_appointment_id  INTEGER,
    updated_at               TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_waitlist_queue
    ON waitlist(day, doctor_id, status, id);
