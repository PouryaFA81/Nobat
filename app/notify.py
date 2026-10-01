# SPDX-License-Identifier: AGPL-3.0-or-later
"""Push notifications through the self-hosted ntfy server, and the
evening "you have sessions tomorrow" reminder."""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from . import db
from .jalali import fa, long_date

log = logging.getLogger("nobat.notify")

NTFY_URL = os.environ.get("NTFY_URL", "http://ntfy:80").rstrip("/")
NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "")
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
REMINDER_HOUR = int(os.environ.get("REMINDER_HOUR", "20"))

# All dates and times in the panel are in this time zone (default: Iran).
TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "Asia/Tehran"))


def now_local() -> datetime:
    """Current wall-clock time in the panel's time zone (naive datetime)."""
    return datetime.now(TIMEZONE).replace(tzinfo=None)


async def send(topic: str, title: str, message: str, tags: str = "calendar") -> bool:
    payload = {"topic": topic, "title": title, "message": message,
               "tags": [tags], "priority": 4}
    if BASE_URL:
        payload["click"] = BASE_URL + "/me"
    headers = {"Authorization": f"Bearer {NTFY_TOKEN}"} if NTFY_TOKEN else {}
    try:
        # trust_env=False: ntfy is on the internal Docker network, so never route
        # this request through an HTTP proxy set in the environment.
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            r = await client.post(NTFY_URL, json=payload, headers=headers)
        if r.status_code >= 300:
            log.warning("ntfy returned %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as e:  # never let a notification failure break the panel
        log.warning("ntfy send failed: %r", e)
        return False


def _when(day: str, time: str) -> str:
    return f"{long_date(datetime.strptime(day, '%Y-%m-%d').date())}، ساعت {fa(time)}"


async def appointment_event(kind: str, appt: dict, old: dict | None = None):
    """kind: new | moved | cancelled. appt/old are dicts with doctor topic info."""
    when = _when(appt["day"], appt["start_time"])
    if kind == "new":
        await send(appt["ntfy_topic"], "نوبت جدید", f"{appt['initials']} — {when}", "calendar")
    elif kind == "moved":
        before = _when(old["day"], old["start_time"])
        await send(appt["ntfy_topic"], "تغییر زمان نوبت",
                   f"{appt['initials']}\nقبلی: {before}\nجدید: {when}", "arrows_counterclockwise")
    elif kind == "cancelled":
        await send(appt["ntfy_topic"], "لغو نوبت", f"{appt['initials']} — {when}", "x")
    elif kind == "reassigned_away":
        await send(old["ntfy_topic"], "لغو نوبت",
                   f"{old['initials']} — {_when(old['day'], old['start_time'])}\n(به همکار دیگری منتقل شد)", "x")


async def _send_reminders_for_day(day_iso: str, *, kind: str) -> None:
    """Send one grouped reminder per staff for appointments on day_iso.

    kind: "tomorrow" (evening run) or "today" (catch-up after a missed evening).
    Idempotent via reminder_sent. Never includes appointment notes.
    """
    with db.db() as c:
        rows = c.execute(
            "SELECT a.id, a.initials, a.start_time, a.doctor_id, u.ntfy_topic "
            "FROM appointments a JOIN users u ON u.id = a.doctor_id "
            "WHERE a.day = ? AND a.status = 'active' AND a.reminder_sent = 0 AND u.active = 1 "
            "ORDER BY a.start_time", (day_iso,)).fetchall()
    if not rows:
        return
    by_doctor: dict[int, list] = {}
    for r in rows:
        by_doctor.setdefault(r["doctor_id"], []).append(r)
    when_word = "امروز" if kind == "today" else "فردا"
    day_label = long_date(datetime.strptime(day_iso, "%Y-%m-%d").date())
    for items in by_doctor.values():
        lines = [f"ساعت {fa(r['start_time'])} — {r['initials']}" for r in items]
        title = f"یادآوری: {when_word} {fa(len(items))} جلسه دارید"
        body = day_label + "\n" + "\n".join(lines)
        if await send(items[0]["ntfy_topic"], title, body, "bell"):
            with db.db() as c:
                c.executemany("UPDATE appointments SET reminder_sent = 1 WHERE id = ?",
                              [(r["id"],) for r in items])


async def send_due_reminders():
    """Evening reminders for the next calendar day, plus catch-up for misses.

    Normal: from REMINDER_HOUR onward, send each staff member one message
    listing tomorrow's sessions (reminder_sent stays the idempotency key).

    Catch-up: if the process was down past midnight, appointments for *today*
    may still have reminder_sent = 0 (the "tomorrow" window already passed).
    Until REMINDER_HOUR that morning/day, send those once, worded as امروز.
    Same-day bookings already set reminder_sent via reminder_flag, so they
    are not re-notified. Notes are never included.
    """
    now = now_local()
    today = now.date()
    # Catch-up window: before tonight's REMINDER_HOUR, recover missed "evening before".
    if now.hour < REMINDER_HOUR:
        await _send_reminders_for_day(today.isoformat(), kind="today")
    if now.hour >= REMINDER_HOUR:
        tomorrow = (today + timedelta(days=1)).isoformat()
        await _send_reminders_for_day(tomorrow, kind="tomorrow")


async def reminder_loop():
    while True:
        try:
            await send_due_reminders()
        except Exception:
            log.exception("reminder loop error")
        await asyncio.sleep(60)
