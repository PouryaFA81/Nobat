# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase 4.3: recurring weekly series with overlap refusal."""
import asyncio
import logging
import os
import re
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

_tmp = tempfile.mkdtemp()
os.environ.update(DB_PATH=os.path.join(_tmp, "p4rec.db"), SECRET_KEY="t" * 40,
                  COOKIE_SECURE="0", STAFF_LABEL="مشاور", TIMEZONE="Asia/Tehran")

from starlette.testclient import TestClient  # noqa: E402

from app import db, jalali, main, notify, recurrence  # noqa: E402

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("nobat").setLevel(logging.WARNING)


async def fake_send(topic, title, message, tags="calendar"):
    return True


async def idle_loop():
    await asyncio.sleep(3600)


def csrf(resp) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', resp.text).group(1)


class RecurrenceHelpers(unittest.TestCase):
    def test_weekly_dates(self):
        d = date(2026, 10, 5)
        days = recurrence.weekly_dates(d, 4)
        self.assertEqual(len(days), 4)
        self.assertEqual(days[1], d + timedelta(weeks=1))
        self.assertEqual(recurrence.parse_repeat_weeks("99"), recurrence.MAX_REPEAT_WEEKS)
        self.assertEqual(recurrence.parse_repeat_weeks("x"), 1)


class RecurrencePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._db_dir = tempfile.mkdtemp()
        cls._old_db = db.DB_PATH
        db.DB_PATH = os.path.join(cls._db_dir, "p4rec.db")
        cls.patches = [mock.patch.object(notify, "send", fake_send),
                       mock.patch.object(notify, "reminder_loop", idle_loop)]
        for p in cls.patches:
            p.start()
        db.init()
        with db.db() as c:
            assert db.current_migration_version(c) == db.SCHEMA_VERSION
            cols = {r[1] for r in c.execute("PRAGMA table_info(appointments)")}
            assert "series_id" in cols
            cls.admin_id = db.create_user(c, "admin", "مدیر", "adminpass1",
                                          is_admin=True, is_doctor=True)
            cls.doc_id = db.create_user(c, "doc", "دکتر الف", "docpass12")

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()
        db.DB_PATH = cls._old_db

    def setUp(self):
        main._failures.clear()
        with db.db() as c:
            c.execute("DELETE FROM appointments")

    def _login(self, client):
        r = client.get("/login")
        client.post("/login", data={"csrf": csrf(r), "username": "admin",
                                    "password": "adminpass1"})

    def _book(self, client, day, hour=10, minute=0, repeat=1, initials="س.م"):
        jy, jm, jd = jalali.to_jalali(day)
        r = client.get("/appointments/new")
        return client.post("/appointments/new", data={
            "csrf": csrf(r), "doctor_id": str(self.doc_id), "initials": initials,
            "jy": str(jy), "jm": str(jm), "jd": str(jd),
            "hour": str(hour), "minute": str(minute), "duration": "60",
            "description": "یادداشت", "repeat_weeks": str(repeat),
        }, follow_redirects=False)

    def test_create_weekly_series(self):
        day = date.today() + timedelta(days=5)
        with TestClient(main.app) as client:
            self._login(client)
            r = self._book(client, day, repeat=4)
            self.assertEqual(r.status_code, 303)
        with db.db() as c:
            rows = c.execute(
                "SELECT * FROM appointments WHERE initials = 'س.م' ORDER BY day"
            ).fetchall()
            self.assertEqual(len(rows), 4)
            sid = rows[0]["series_id"]
            self.assertTrue(sid)
            self.assertTrue(all(r["series_id"] == sid for r in rows))
            self.assertEqual(rows[1]["day"], (day + timedelta(weeks=1)).isoformat())

    def test_overlap_refuses_entire_series(self):
        day = date.today() + timedelta(days=6)
        with TestClient(main.app) as client:
            self._login(client)
            self.assertEqual(self._book(client, day + timedelta(weeks=1),
                                        initials="مانع").status_code, 303)
            r = self._book(client, day, repeat=3, initials="سری")
            self.assertEqual(r.status_code, 400)
            self.assertIn("تداخل", r.text)
        with db.db() as c:
            n = c.execute("SELECT COUNT(*) FROM appointments WHERE initials = 'سری'").fetchone()[0]
            self.assertEqual(n, 0)

    def test_cancel_one_vs_series(self):
        day = date.today() + timedelta(days=7)
        with TestClient(main.app) as client:
            self._login(client)
            self._book(client, day, repeat=3, initials="لغو")
            with db.db() as c:
                rows = c.execute(
                    "SELECT id, series_id FROM appointments WHERE initials = 'لغو' ORDER BY day"
                ).fetchall()
                first_id, sid = rows[0]["id"], rows[0]["series_id"]
            day_page = client.get(f"/day/{jalali.jstr(day)}")
            tok = csrf(day_page)
            # cancel one
            client.post(f"/appointments/{first_id}/cancel",
                        data={"csrf": tok, "cancel_scope": "one"}, follow_redirects=False)
            with db.db() as c:
                st = [r["status"] for r in c.execute(
                    "SELECT status FROM appointments WHERE series_id = ? ORDER BY day", (sid,))]
            self.assertEqual(st[0], "cancelled")
            self.assertEqual(st[1], "active")
            # cancel rest of series from second
            with db.db() as c:
                second = c.execute(
                    "SELECT id FROM appointments WHERE series_id = ? AND status = 'active' "
                    "ORDER BY day", (sid,)).fetchone()["id"]
            day2 = day + timedelta(weeks=1)
            tok = csrf(client.get(f"/day/{jalali.jstr(day2)}"))
            client.post(f"/appointments/{second}/cancel",
                        data={"csrf": tok, "cancel_scope": "series"}, follow_redirects=False)
            with db.db() as c:
                left = c.execute(
                    "SELECT COUNT(*) FROM appointments WHERE series_id = ? AND status != 'cancelled'",
                    (sid,)).fetchone()[0]
            self.assertEqual(left, 0)


if __name__ == "__main__":
    unittest.main()
