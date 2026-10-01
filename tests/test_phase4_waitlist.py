# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase 4.4: waitlist soft queue and auto-promote on cancel."""
import asyncio
import logging
import os
import re
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

_tmp = tempfile.mkdtemp()
os.environ.update(DB_PATH=os.path.join(_tmp, "p4wl.db"), SECRET_KEY="t" * 40,
                  COOKIE_SECURE="0", STAFF_LABEL="مشاور", TIMEZONE="Asia/Tehran")

from starlette.testclient import TestClient  # noqa: E402

from app import db, jalali, main, notify, waitlist  # noqa: E402

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("nobat").setLevel(logging.WARNING)


async def fake_send(topic, title, message, tags="calendar"):
    return True


async def idle_loop():
    await asyncio.sleep(3600)


def csrf(resp) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', resp.text).group(1)


class WaitlistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._db_dir = tempfile.mkdtemp()
        cls._old_db = db.DB_PATH
        db.DB_PATH = os.path.join(cls._db_dir, "p4wl.db")
        cls.patches = [mock.patch.object(notify, "send", fake_send),
                       mock.patch.object(notify, "reminder_loop", idle_loop)]
        for p in cls.patches:
            p.start()
        db.init()
        with db.db() as c:
            self_ver = db.current_migration_version(c)
            assert self_ver == db.SCHEMA_VERSION == 7
            tables = {r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            assert "waitlist" in tables
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
            c.execute("DELETE FROM waitlist")

    def _login(self, client):
        r = client.get("/login")
        client.post("/login", data={"csrf": csrf(r), "username": "admin",
                                    "password": "adminpass1"})

    def test_add_waitlist_and_auto_promote_on_cancel(self):
        day = date.today() + timedelta(days=4)
        jy, jm, jd = jalali.to_jalali(day)
        with TestClient(main.app) as client:
            self._login(client)
            # book a slot
            r = client.get("/appointments/new")
            client.post("/appointments/new", data={
                "csrf": csrf(r), "doctor_id": str(self.doc_id), "initials": "اولی",
                "jy": str(jy), "jm": str(jm), "jd": str(jd),
                "hour": "11", "minute": "0", "duration": "60", "description": "",
                "repeat_weeks": "1",
            }, follow_redirects=False)
            # waitlist
            day_page = client.get(f"/day/{jalali.jstr(day)}")
            self.assertIn("فهرست انتظار", day_page.text)
            client.post("/waitlist/add", data={
                "csrf": csrf(day_page), "doctor_id": str(self.doc_id),
                "jy": str(jy), "jm": str(jm), "jd": str(jd),
                "initials": "منتظر", "hour": "11", "minute": "0",
                "duration": "60", "note": "یادداشت انتظار",
            }, follow_redirects=False)
            with db.db() as c:
                w = c.execute("SELECT * FROM waitlist WHERE initials = 'منتظر'").fetchone()
                self.assertEqual(w["status"], "waiting")
                appt = c.execute(
                    "SELECT id FROM appointments WHERE initials = 'اولی'").fetchone()
                appt_id = appt["id"]
            tok = csrf(client.get(f"/day/{jalali.jstr(day)}"))
            r2 = client.post(f"/appointments/{appt_id}/cancel",
                             data={"csrf": tok, "cancel_scope": "one"},
                             follow_redirects=True)
            self.assertIn("ارتقا", r2.text)
            with db.db() as c:
                w = c.execute("SELECT * FROM waitlist WHERE initials = 'منتظر'").fetchone()
                self.assertEqual(w["status"], "promoted")
                self.assertIsNotNone(w["promoted_appointment_id"])
                promo = c.execute(
                    "SELECT * FROM appointments WHERE id = ?",
                    (w["promoted_appointment_id"],)).fetchone()
                self.assertEqual(promo["initials"], "منتظر")
                self.assertEqual(promo["start_time"], "11:00")
                self.assertEqual(promo["status"], "active")
                # private note carried to appointment description for staff, OK
                self.assertEqual(promo["description"], "یادداشت انتظار")

    def test_choose_promote_time(self):
        entry = {"preferred_time": "15:30"}
        self.assertEqual(waitlist.choose_promote_time(entry, "09:00"), "15:30")
        entry = {"preferred_time": ""}
        self.assertEqual(waitlist.choose_promote_time(entry, "09:00"), "09:00")


if __name__ == "__main__":
    unittest.main()
