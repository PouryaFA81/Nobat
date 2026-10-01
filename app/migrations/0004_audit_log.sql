-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Append-only audit log for coordinator actions (Phase 2.1).
-- actor_user_id may be NULL if the user row is later removed; username is kept.
-- appointment_id is optional; detail is free-form JSON/text (no private notes).

CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY,
    actor_user_id   INTEGER,
    actor_username  TEXT NOT NULL DEFAULT '',
    action          TEXT NOT NULL,
    appointment_id  INTEGER,
    detail          TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action, created_at);
