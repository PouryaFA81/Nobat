# Phase 2 — Ops trust

## What changed

### 2.1 Audit log
- Append-only table `audit_log` (migration **0004**): actor user id/username, action, optional appointment id, detail JSON/text, timestamp.
- Recorded actions: `book`, `move`, `reassign`, `cancel`, `restore`, `status_change`, `user_deactivate`, `user_activate`, `schedule_hours`, `schedule_block`.
- Private appointment notes are **never** stored in audit detail.
- Fail-safe writes: audit failures are logged; booking / mutation still succeeds (SQLite savepoint when sharing a connection).
- Admin-only Persian UI: **گزارش فعالیت** at `/audit` — filter by Gregorian day (`YYYY-MM-DD`) and actor.

### 2.2 Reminder durability
- Evening loop still sends “tomorrow” reminders from `REMINDER_HOUR` onward (idempotent via `reminder_sent`).
- **Catch-up:** if the process was down past midnight, appointments for *today* with `reminder_sent = 0` are sent once before `REMINDER_HOUR`, worded as امروز.
- Same-day bookings already set `reminder_sent` via `reminder_flag`, so they are not re-notified. Notes never appear in notifications.

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
- Catch-up reminder behaviour is app-only; no schema change for 2.2.
