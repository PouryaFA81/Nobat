# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase 4.1: ICS download — no private notes."""
import asyncio
import logging
import os
import re
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

_tmp = tempfile.mkdtemp()
os.environ.update(DB_PATH=os.path.join(_tmp, "p4ics.db"), SECRET_KEY="t" * 40,
                  COOKIE_SECURE="0", STAFF_LABEL="مشاور", TIMEZONE="Asia/Tehran")

from starlette.testclient import TestClient  # noqa: E402

from app import db, ics, main, notify  # noqa: E402

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("nobat").setLevel(logging.WARNING)

SENT: list[dict] = []


async def fake_send(topic, title, message, tags="calendar"):
    SENT.append({"topic": topic, "title": title, "message": message})
    return True


async def idle_loop():
    await asyncio.sleep(3600)


def csrf(resp) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', resp.text).group(1)


class IcsBuilderTests(unittest.TestCase):
    def test_no_private_notes_in_description(self):
        rows = [{
            "id": 1, "day": "2026-10-05", "start_time": "09:30",
            "duration_min": 60, "initials": "س.م", "status": "active",
            "description": "یادداشت محرمانه بیمار",
        }]
        raw = ics.build_ics(rows).decode("utf-8")
        self.assertIn("BEGIN:VCALENDAR", raw)
        self.assertIn("SUMMARY:س.م", raw)
        self.assertIn("DESCRIPTION:نوبت", raw)
        self.assertNotIn("محرمانه", raw)
        self.assertNotIn("یادداشت", raw)
        self.assertIn("DTSTART;TZID=Asia/Tehran:20261005T093000", raw)
        self.assertIn("DTEND;TZID=Asia/Tehran:20261005T103000", raw)

    def test_cancelled_status(self):
        rows = [{
            "id": 2, "day": "2026-10-05", "start_time": "10:00",
            "duration_min": 30, "initials": "الف", "status": "cancelled",
            "description": "",
        }]
        raw = ics.build_ics(rows).decode("utf-8")
        self.assertIn("STATUS:CANCELLED", raw)


class IcsRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._db_dir = tempfile.mkdtemp()
        cls._old_db = db.DB_PATH
        db.DB_PATH = os.path.join(cls._db_dir, "p4ics.db")
        cls.patches = [mock.patch.object(notify, "send", fake_send),
                       mock.patch.object(notify, "reminder_loop", idle_loop)]
        for p in cls.patches:
            p.start()
        db.init()
        with db.db() as c:
            cls.admin_id = db.create_user(c, "admin", "مدیر", "adminpass1",
                                          is_admin=True, is_doctor=True)
            cls.doc_id = db.create_user(c, "doc", "دکتر الف", "docpass12")

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()
        db.DB_PATH = cls._old_db

    def setUp(self):
        SENT.clear()
        main._failures.clear()
        with db.db() as c:
            c.execute("DELETE FROM appointments")
            day = (date.today() + timedelta(days=2)).isoformat()
            c.execute(
                "INSERT INTO appointments (doctor_id, initials, day, start_time, duration_min, "
                "description, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.doc_id, "س.م", day, "14:00", 60, "یادداشت محرمانه", self.admin_id),
            )
            self.day = day

    def _login(self, client, username, password):
        r = client.get("/login")
        return client.post("/login", data={"csrf": csrf(r), "username": username,
                                           "password": password}, follow_redirects=False)

    def test_me_ics_staff_only_own_no_notes(self):
        with TestClient(main.app) as client:
            self._login(client, "doc", "docpass12")
            r = client.get("/me.ics")
            self.assertEqual(r.status_code, 200)
            self.assertIn("text/calendar", r.headers.get("content-type", ""))
            body = r.text
            self.assertIn("SUMMARY:س.م", body)
            self.assertNotIn("محرمانه", body)
            me = client.get("/me")
            self.assertIn("/me.ics", me.text)

    def test_day_ics_admin(self):
        from app import jalali
        j = jalali.jstr(date.fromisoformat(self.day))
        with TestClient(main.app) as client:
            self._login(client, "admin", "adminpass1")
            r = client.get(f"/day/{j}/ics")
            self.assertEqual(r.status_code, 200)
            self.assertIn("SUMMARY:س.م", r.text)
            self.assertNotIn("محرمانه", r.text)
            day_page = client.get(f"/day/{j}")
            self.assertIn("/ics", day_page.text)

    def test_me_ics_requires_login(self):
        with TestClient(main.app) as client:
            r = client.get("/me.ics", follow_redirects=False)
            self.assertIn(r.status_code, (303, 302))


if __name__ == "__main__":
    unittest.main()
