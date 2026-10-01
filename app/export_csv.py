# SPDX-License-Identifier: AGPL-3.0-or-later
"""CSV export helpers for clinic appointment lists (UTF-8 BOM for Excel)."""
from __future__ import annotations

import csv
import io
from datetime import date

from . import jalali, schedule

# Notes are private; default export excludes them (never sent via ntfy either).
CSV_COLUMNS = ("date", "time", "staff", "initials", "status", "created_by")
CSV_HEADERS_FA = {
    "date": "تاریخ",
    "time": "ساعت",
    "staff": "همکار",
    "initials": "حروف اول",
    "status": "وضعیت",
    "created_by": "ثبت‌کننده",
    "notes": "یادداشت",
}


def fetch_rows(c, day_from: str, day_to: str, doctor_id: int | None = None):
    """Return appointment rows for Gregorian inclusive range, with staff/creator names."""
    q = (
        "SELECT a.day, a.start_time, a.initials, a.status, a.description, "
        "u.name AS staff_name, cu.name AS created_by_name "
        "FROM appointments a "
        "JOIN users u ON u.id = a.doctor_id "
        "LEFT JOIN users cu ON cu.id = a.created_by "
        "WHERE a.day >= ? AND a.day <= ?"
    )
    args: list = [day_from, day_to]
    if doctor_id is not None:
        q += " AND a.doctor_id = ?"
        args.append(doctor_id)
    q += " ORDER BY a.day, a.start_time, a.id"
    return c.execute(q, args).fetchall()


def build_csv(rows, *, staff_header: str = "همکار", include_notes: bool = False) -> bytes:
    """Build UTF-8 BOM CSV bytes. Notes off by default for privacy."""
    cols = list(CSV_COLUMNS)
    headers = [CSV_HEADERS_FA["date"], CSV_HEADERS_FA["time"], staff_header,
               CSV_HEADERS_FA["initials"], CSV_HEADERS_FA["status"], CSV_HEADERS_FA["created_by"]]
    if include_notes:
        cols.append("notes")
        headers.append(CSV_HEADERS_FA["notes"])

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        day = r["day"] if isinstance(r, dict) or hasattr(r, "keys") else r[0]
        # sqlite Row supports both
        day_s = r["day"]
        try:
            jdate = jalali.jstr(date.fromisoformat(day_s))
        except Exception:
            jdate = day_s
        line = [
            jdate,
            r["start_time"],
            r["staff_name"] or "",
            r["initials"] or "",
            schedule.status_label(r["status"] or "active"),
            r["created_by_name"] or "",
        ]
        if include_notes:
            line.append(r["description"] or "")
        w.writerow(line)
    # Excel-friendly UTF-8 with BOM
    return ("\ufeff" + buf.getvalue()).encode("utf-8")
