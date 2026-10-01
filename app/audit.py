# SPDX-License-Identifier: AGPL-3.0-or-later
"""Append-only audit log. Writes never raise into callers — booking stays fail-safe."""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from . import db

log = logging.getLogger("nobat.audit")

# Stable action keys recorded in audit_log.action
BOOK = "book"
MOVE = "move"
REASSIGN = "reassign"
CANCEL = "cancel"
RESTORE = "restore"
STATUS_CHANGE = "status_change"
USER_DEACTIVATE = "user_deactivate"
USER_ACTIVATE = "user_activate"
SCHEDULE_HOURS = "schedule_hours"
SCHEDULE_BLOCK = "schedule_block"

ACTION_LABELS = {
    BOOK: "ثبت نوبت",
    MOVE: "جابه‌جایی نوبت",
    REASSIGN: "انتقال نوبت",
    CANCEL: "لغو نوبت",
    RESTORE: "بازیابی نوبت",
    STATUS_CHANGE: "تغییر وضعیت",
    USER_DEACTIVATE: "غیرفعال‌سازی کاربر",
    USER_ACTIVATE: "فعال‌سازی کاربر",
    SCHEDULE_HOURS: "تغییر ساعات کاری",
    SCHEDULE_BLOCK: "تغییر روز بسته",
}


def action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action)


def _detail_text(detail: Any) -> str:
    if detail is None or detail == "":
        return ""
    if isinstance(detail, str):
        return detail[:2000]
    try:
        return json.dumps(detail, ensure_ascii=False, separators=(",", ":"))[:2000]
    except (TypeError, ValueError):
        return str(detail)[:2000]


def record(
    actor,
    action: str,
    *,
    appointment_id: int | None = None,
    detail: Any = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Append one audit row. Never raises; logs and returns on failure.

    Prefer passing ``conn`` when already inside a booking transaction so the
    audit row commits with the same connection when possible. If that write
    fails, the error is logged and the caller's transaction is left alone
    (SQLite savepoint) so the booking still succeeds.
    """
    try:
        actor_id = None
        username = ""
        if actor is not None:
            try:
                actor_id = int(actor["id"])
            except (KeyError, TypeError, ValueError):
                actor_id = None
            try:
                username = str(actor["username"] or "")[:80]
            except (KeyError, TypeError):
                username = ""
        text = _detail_text(detail)
        if conn is not None:
            try:
                conn.execute("SAVEPOINT audit_write")
                conn.execute(
                    "INSERT INTO audit_log (actor_user_id, actor_username, action, "
                    "appointment_id, detail) VALUES (?, ?, ?, ?, ?)",
                    (actor_id, username, action, appointment_id, text),
                )
                conn.execute("RELEASE SAVEPOINT audit_write")
            except Exception:
                try:
                    conn.execute("ROLLBACK TO SAVEPOINT audit_write")
                    conn.execute("RELEASE SAVEPOINT audit_write")
                except Exception:
                    pass
                raise
        else:
            with db.db() as c:
                c.execute(
                    "INSERT INTO audit_log (actor_user_id, actor_username, action, "
                    "appointment_id, detail) VALUES (?, ?, ?, ?, ?)",
                    (actor_id, username, action, appointment_id, text),
                )
    except Exception:
        log.exception("audit log write failed (action=%s); continuing", action)


def list_entries(
    c: sqlite3.Connection,
    *,
    day: str | None = None,
    actor_user_id: int | None = None,
    limit: int = 200,
) -> list[sqlite3.Row]:
    """Read recent audit rows. ``day`` is Gregorian YYYY-MM-DD (local calendar day of created_at UTC/local storage)."""
    clauses: list[str] = []
    args: list[Any] = []
    if day:
        # created_at is stored as UTC-ish datetime('now'); filter by calendar date prefix.
        clauses.append("date(created_at) = date(?)")
        args.append(day)
    if actor_user_id is not None:
        clauses.append("actor_user_id = ?")
        args.append(actor_user_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    args.append(max(1, min(int(limit), 500)))
    return list(
        c.execute(
            f"SELECT * FROM audit_log{where} ORDER BY id DESC LIMIT ?",
            args,
        ).fetchall()
    )
