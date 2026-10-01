# Phase 2 — Ops trust

## What changed

### 2.1 Audit log
- Append-only table `audit_log` (migration **0004**): actor user id/username, action, optional appointment id, detail JSON/text, timestamp.
- Recorded actions: `book`, `move`, `reassign`, `cancel`, `restore`, `status_change`, `user_deactivate`, `user_activate`, `schedule_hours`, `schedule_block`.
- Private appointment notes are **never** stored in audit detail.
- Fail-safe writes: audit failures are logged; booking / mutation still succeeds (SQLite savepoint when sharing a connection).
- Admin-only Persian UI: **گزارش فعالیت** at `/audit` — filter by Gregorian day (`YYYY-MM-DD`) and actor.

## How to view the audit log

1. Log in as admin.
2. Open **گزارش فعالیت** in the nav (or `/audit`).
3. Optionally filter by day and/or actor, then apply.

## How to run

```bash
python -m app.manage migrate
python -m unittest discover -s tests -t . -v
```

## Rollback notes

- **0004** is additive (`CREATE TABLE IF NOT EXISTS`). Rolling back app code leaves the table unused.
