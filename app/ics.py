# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build iCalendar (.ics) downloads. Privacy: never put private notes in ICS."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from . import notify

# Fold long lines per RFC 5545 (§3.1); keep under 75 octets.
_MAX_LINE = 73


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
        .replace("\r", "")
    )


def _fold(line: str) -> str:
    """Fold a single logical line into CRLF-separated physical lines."""
    # Work in bytes for octet counting (UTF-8).
    raw = line.encode("utf-8")
    if len(raw) <= _MAX_LINE:
        return line
    parts: list[str] = []
    while raw:
        chunk = raw[:_MAX_LINE]
        # Don't split a multi-byte UTF-8 character.
        while chunk and (chunk[-1] & 0xC0) == 0x80:
            chunk = chunk[:-1]
        if not chunk:
            chunk = raw[:1]
        parts.append(chunk.decode("utf-8"))
        raw = raw[len(chunk):]
        if raw:
            # Continuation lines start with a single space.
            raw = b" " + raw
    return "\r\n".join(parts)


def _fmt_local(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def _end_dt(day: str, start_time: str, duration_min: int) -> datetime:
    h, m = (int(x) for x in start_time.split(":"))
    start = datetime(int(day[:4]), int(day[5:7]), int(day[8:10]), h, m)
    return start + timedelta(minutes=int(duration_min))


def _start_dt(day: str, start_time: str) -> datetime:
    h, m = (int(x) for x in start_time.split(":"))
    return datetime(int(day[:4]), int(day[5:7]), int(day[8:10]), h, m)


def vevent_lines(appt: Any, *, tzid: str) -> list[str]:
    """Return unfolded ICS lines for one VEVENT (no private notes)."""
    day = appt["day"]
    start = appt["start_time"]
    duration = int(appt["duration_min"])
    initials = str(appt["initials"] or "").strip() or "نوبت"
    appt_id = appt["id"]
    status = str(appt["status"] or "active")
    uid = f"nobat-{appt_id}@nobat.local"
    summary = _escape(initials)
    # DESCRIPTION: public summary only — never private clinic notes.
    description = _escape("نوبت")
    dtstart = _fmt_local(_start_dt(day, start))
    dtend = _fmt_local(_end_dt(day, start, duration))
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTART;TZID={tzid}:{dtstart}",
        f"DTEND;TZID={tzid}:{dtend}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
    ]
    if status == "cancelled":
        lines.append("STATUS:CANCELLED")
    else:
        lines.append("STATUS:CONFIRMED")
    lines.append("END:VEVENT")
    return lines


def build_ics(
    appointments: Iterable[Any],
    *,
    calname: str = "نوبت",
    tzid: str | None = None,
) -> bytes:
    """Build a UTF-8 .ics calendar body (CRLF). No private notes."""
    tz = tzid or getattr(notify.TIMEZONE, "key", None) or os.environ.get("TIMEZONE", "Asia/Tehran")
    out: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Nobat//FA//",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(calname)}",
        f"X-WR-TIMEZONE:{tz}",
    ]
    for appt in appointments:
        out.extend(vevent_lines(appt, tzid=tz))
    out.append("END:VCALENDAR")
    folded = "\r\n".join(_fold(line) for line in out) + "\r\n"
    return folded.encode("utf-8")


def filename_for_day(d: date) -> str:
    return f"nobat-{d.isoformat()}.ics"


def filename_for_me() -> str:
    return "nobat-me.ics"
