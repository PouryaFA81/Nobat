# SPDX-License-Identifier: AGPL-3.0-or-later
"""Soft waitlist queue. Auto-promote on cancel is intentional and tested."""
from __future__ import annotations

import sqlite3
from typing import Any

from . import schedule

STATUS_WAITING = "waiting"
STATUS_PROMOTED = "promoted"
STATUS_CANCELLED = "cancelled"


def ensure_table(c: sqlite3.Connection) -> None:
    c.executescript(
        """
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
        """
    )


def list_for_day(c: sqlite3.Connection, day_iso: str, doctor_id: int | None = None):
    q = (
        "SELECT w.*, u.name AS doctor_name FROM waitlist w "
        "JOIN users u ON u.id = w.doctor_id "
        "WHERE w.day = ? AND w.status = ?"
    )
    args: list[Any] = [day_iso, STATUS_WAITING]
    if doctor_id:
        q += " AND w.doctor_id = ?"
        args.append(doctor_id)
    return c.execute(q + " ORDER BY w.id", args).fetchall()


def add_entry(
    c: sqlite3.Connection,
    *,
    doctor_id: int,
    day_iso: str,
    initials: str,
    preferred_time: str = "",
    duration_min: int = 60,
    note: str = "",
    created_by: int | None = None,
) -> int:
    cur = c.execute(
        "INSERT INTO waitlist (doctor_id, day, preferred_time, duration_min, initials, note, "
        "created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (doctor_id, day_iso, preferred_time or "", int(duration_min),
         initials[:30], (note or "")[:1000], created_by),
    )
    return cur.lastrowid


def cancel_entry(c: sqlite3.Connection, entry_id: int) -> bool:
    cur = c.execute(
        "UPDATE waitlist SET status = ?, updated_at = datetime('now') "
        "WHERE id = ? AND status = ?",
        (STATUS_CANCELLED, entry_id, STATUS_WAITING),
    )
    return cur.rowcount > 0


def next_waiting(c: sqlite3.Connection, doctor_id: int, day_iso: str):
    return c.execute(
        "SELECT * FROM waitlist WHERE doctor_id = ? AND day = ? AND status = ? "
        "ORDER BY id ASC LIMIT 1",
        (doctor_id, day_iso, STATUS_WAITING),
    ).fetchone()


def mark_promoted(c: sqlite3.Connection, entry_id: int, appointment_id: int) -> None:
    c.execute(
        "UPDATE waitlist SET status = ?, promoted_appointment_id = ?, "
        "updated_at = datetime('now') WHERE id = ?",
        (STATUS_PROMOTED, appointment_id, entry_id),
    )


def choose_promote_time(entry, freed_start: str) -> str:
    """Prefer waitlist preferred_time when set; else the cancelled slot's start."""
    pref = (entry["preferred_time"] or "").strip()
    if pref and schedule.parse_hhmm(pref) is not None:
        return pref if len(pref) == 5 else f"{int(pref.split(':')[0]):02d}:{int(pref.split(':')[1]):02d}"
    return freed_start
