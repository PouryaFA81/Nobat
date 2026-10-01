# SPDX-License-Identifier: AGPL-3.0-or-later
"""Working hours, blocked days, and appointment status helpers."""
from __future__ import annotations

import re

# Clinic-wide sentinel (not a users.id).
CLINIC = 0

DEFAULT_START = "06:00"
DEFAULT_END = "24:00"

# Statuses that still occupy the staff member's slot (overlap check).
# Only cancelled frees the slot for rebooking.
STATUSES = ("active", "arrived", "no_show", "completed", "cancelled")
SLOT_BLOCKING = frozenset({"active", "arrived", "no_show", "completed"})
STATUS_LABELS = {
    "active": "فعال",
    "arrived": "حاضر",
    "no_show": "نیامد",
    "completed": "انجام شد",
    "cancelled": "لغو شده",
}

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_hhmm(s: str) -> int | None:
    """Return minutes from midnight, or None if invalid. Accepts 24:00."""
    m = _TIME_RE.match((s or "").strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h == 24 and mi == 0:
        return 24 * 60
    if not (0 <= h < 24 and 0 <= mi < 60):
        return None
    return h * 60 + mi


def fmt_hhmm(minutes: int) -> str:
    if minutes >= 24 * 60:
        return "24:00"
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def ensure_clinic_hours(c) -> None:
    """Guarantee a clinic-default row exists (fail-safe for empty tables)."""
    c.execute(
        "INSERT OR IGNORE INTO working_hours (doctor_id, start_time, end_time) VALUES (?, ?, ?)",
        (CLINIC, DEFAULT_START, DEFAULT_END),
    )


def get_hours(c, doctor_id: int) -> tuple[str, str]:
    """Return (start_time, end_time) for staff, falling back to clinic default, then builtins."""
    ensure_clinic_hours(c)
    row = c.execute(
        "SELECT start_time, end_time FROM working_hours WHERE doctor_id = ?",
        (doctor_id,),
    ).fetchone()
    if row:
        return row["start_time"], row["end_time"]
    row = c.execute(
        "SELECT start_time, end_time FROM working_hours WHERE doctor_id = ?",
        (CLINIC,),
    ).fetchone()
    if row:
        return row["start_time"], row["end_time"]
    return DEFAULT_START, DEFAULT_END


def set_hours(c, doctor_id: int, start_time: str, end_time: str) -> None:
    c.execute(
        "INSERT INTO working_hours (doctor_id, start_time, end_time) VALUES (?, ?, ?) "
        "ON CONFLICT(doctor_id) DO UPDATE SET start_time = excluded.start_time, "
        "end_time = excluded.end_time",
        (doctor_id, start_time, end_time),
    )


def clear_staff_hours(c, doctor_id: int) -> None:
    if doctor_id == CLINIC:
        return
    c.execute("DELETE FROM working_hours WHERE doctor_id = ?", (doctor_id,))


def is_blocked(c, day_iso: str, doctor_id: int) -> tuple[bool, str]:
    """True if day is blocked for this staff member (clinic-wide or personal)."""
    rows = c.execute(
        "SELECT reason, doctor_id FROM blocked_days WHERE day = ? AND doctor_id IN (?, ?)",
        (day_iso, CLINIC, doctor_id),
    ).fetchall()
    if not rows:
        return False, ""
    # Prefer staff-specific reason if present.
    for r in rows:
        if r["doctor_id"] == doctor_id:
            return True, r["reason"] or ""
    return True, rows[0]["reason"] or ""


def list_blocked(c, limit: int = 200):
    return c.execute(
        "SELECT b.*, u.name AS doctor_name FROM blocked_days b "
        "LEFT JOIN users u ON u.id = b.doctor_id AND b.doctor_id != 0 "
        "ORDER BY b.day, b.doctor_id LIMIT ?",
        (limit,),
    ).fetchall()


def add_blocked(c, day_iso: str, doctor_id: int, reason: str) -> None:
    c.execute(
        "INSERT INTO blocked_days (day, doctor_id, reason) VALUES (?, ?, ?) "
        "ON CONFLICT(day, doctor_id) DO UPDATE SET reason = excluded.reason",
        (day_iso, doctor_id, reason[:200]),
    )


def remove_blocked(c, blocked_id: int) -> None:
    c.execute("DELETE FROM blocked_days WHERE id = ?", (blocked_id,))


def validate_within_hours(start_hhmm: str, duration_min: int, open_hhmm: str, close_hhmm: str) -> str | None:
    """Return Persian error or None if the appointment fits the working window."""
    s = parse_hhmm(start_hhmm)
    o = parse_hhmm(open_hhmm)
    cl = parse_hhmm(close_hhmm)
    if s is None or o is None or cl is None:
        return "ساعت کاری نامعتبر است."
    if o >= cl:
        return "بازهٔ ساعت کاری نامعتبر است."
    end = s + duration_min
    if s < o or end > cl:
        return (f"خارج از ساعت کاری ({open_hhmm} تا {close_hhmm}). "
                f"نوبت باید داخل این بازه تمام شود.")
    return None


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status or "نامشخص")


def is_slot_blocking(status: str) -> bool:
    """Unknown/legacy statuses block the slot (fail-safe). Only cancelled frees it."""
    if status == "cancelled":
        return False
    if status in SLOT_BLOCKING:
        return True
    return True  # unknown → treat as occupying
