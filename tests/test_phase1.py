# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase 1: working hours, blocked days, appointment statuses."""
import asyncio
import logging
import os
import re
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

_tmp = tempfile.mkdtemp()
os.environ.update(DB_PATH=os.path.join(_tmp, "phase1.db"), SECRET_KEY="t" * 40,
                  COOKIE_SECURE="0", STAFF_LABEL="مشاور", TIMEZONE="Asia/Tehran")

from starlette.testclient import TestClient  # noqa: E402

from app import db, jalali, main, notify, schedule  # noqa: E402

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


class Phase1ScheduleHelpers(unittest.TestCase):
    def test_parse_hhmm_and_validate(self):
        self.assertEqual(schedule.parse_hhmm("06:00"), 360)
        self.assertEqual(schedule.parse_hhmm("24:00"), 1440)
        self.assertIsNone(schedule.parse_hhmm("25:00"))
        self.assertIsNone(schedule.validate_within_hours("08:00", 60, "06:00", "24:00"))
        self.assertIsNotNone(schedule.validate_within_hours("05:00", 60, "06:00", "24:00"))
        self.assertIsNotNone(schedule.validate_within_hours("23:00", 120, "06:00", "24:00"))
        self.assertIsNone(schedule.validate_within_hours("23:00", 60, "06:00", "24:00"))

    def test_slot_blocking(self):
        for st in ("active", "arrived", "no_show", "completed", "weird"):
            self.assertTrue(schedule.is_slot_blocking(st))
        self.assertFalse(schedule.is_slot_blocking("cancelled"))


class Phase1PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._db_dir = tempfile.mkdtemp()
        cls._old_db = db.DB_PATH
        db.DB_PATH = os.path.join(cls._db_dir, "phase1.db")
        cls.patches = [mock.patch.object(notify, "send", fake_send),
                       mock.patch.object(notify, "reminder_loop", idle_loop)]
        for p in cls.patches:
            p.start()
        db.init()
        with db.db() as c:
            cls.admin_id = db.create_user(c, "admin", "مدیر", "adminpass1", is_admin=True, is_doctor=True)
            cls.doc_id = db.create_user(c, "doc", "دکتر الف", "docpass12")
            ver = db.current_migration_version(c)
            assert ver == db.SCHEMA_VERSION, ver

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()
        db.DB_PATH = cls._old_db

    def setUp(self):
        SENT.clear()
        main._failures.clear()
        # Reset schedule to defaults between tests
        with db.db() as c:
            c.execute("DELETE FROM blocked_days")
            c.execute("DELETE FROM working_hours WHERE doctor_id != 0")
            schedule.set_hours(c, schedule.CLINIC, "06:00", "24:00")

    def client(self, username, password):
        c = TestClient(main.app, follow_redirects=False)
        c.__enter__()
        self.addCleanup(c.__exit__, None, None, None)
        r = c.get("/login")
        r = c.post("/login", data={"csrf": csrf(r), "username": username, "password": password})
        self.assertEqual(r.status_code, 303, "login failed")
        return c

    def future_day(self, days=10):
        d = notify.now_local().date() + timedelta(days=days)
        return d, jalali.to_jalali(d)

    def book(self, c, doctor_id, initials, days=10, hour=16, minute=0, duration=60):
        d, (jy, jm, jd) = self.future_day(days)
        r = c.get(f"/appointments/new?day={jalali.jstr(d)}")
        return c.post("/appointments/new", data={
            "csrf": csrf(r), "doctor_id": doctor_id, "initials": initials, "jy": jy, "jm": jm, "jd": jd,
            "hour": hour, "minute": minute, "duration": duration, "description": ""})

    def test_migration_creates_hours_tables(self):
        with db.db() as c:
            tables = {r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            self.assertIn("working_hours", tables)
            self.assertIn("blocked_days", tables)
            row = c.execute(
                "SELECT start_time, end_time FROM working_hours WHERE doctor_id = 0").fetchone()
            self.assertEqual(row["start_time"], "06:00")
            self.assertEqual(row["end_time"], "24:00")

    def test_booking_outside_hours_refused(self):
        a = self.client("admin", "adminpass1")
        with db.db() as c:
            schedule.set_hours(c, schedule.CLINIC, "08:00", "14:00")
        r = self.book(a, self.doc_id, "دیر", days=20, hour=16)
        self.assertEqual(r.status_code, 400)
        self.assertIn("ساعت کاری", r.text)
        r = self.book(a, self.doc_id, "خوب", days=20, hour=10)
        self.assertEqual(r.status_code, 303)

    def test_staff_hours_override(self):
        a = self.client("admin", "adminpass1")
        with db.db() as c:
            schedule.set_hours(c, schedule.CLINIC, "08:00", "18:00")
            schedule.set_hours(c, self.doc_id, "10:00", "12:00")
        r = self.book(a, self.doc_id, "خارج", days=21, hour=13)
        self.assertEqual(r.status_code, 400)
        r = self.book(a, self.doc_id, "داخل", days=21, hour=10)
        self.assertEqual(r.status_code, 303)

    def test_blocked_day_refuses_new_keeps_existing(self):
        a = self.client("admin", "adminpass1")
        r = self.book(a, self.doc_id, "قبلی", days=22, hour=10)
        self.assertEqual(r.status_code, 303)
        d, (jy, jm, jd) = self.future_day(22)
        with db.db() as c:
            schedule.add_blocked(c, d.isoformat(), 0, "تعطیل")
        r = self.book(a, self.doc_id, "جدید", days=22, hour=11)
        self.assertEqual(r.status_code, 400)
        self.assertIn("بسته", r.text)
        # Existing appointment still listed on day view
        r = a.get(f"/day/{jalali.jstr(d)}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("قبلی", r.text)

    def test_status_transitions_and_overlap(self):
        a = self.client("admin", "adminpass1")
        self.book(a, self.doc_id, "وضعیت", days=23, hour=9)
        with db.db() as c:
            appt_id = c.execute("SELECT id FROM appointments WHERE initials='وضعیت'").fetchone()[0]
            d = c.execute("SELECT day FROM appointments WHERE id=?", (appt_id,)).fetchone()[0]
        r = a.get(f"/day/{jalali.jstr(date.fromisoformat(d))}")
        r = a.post(f"/appointments/{appt_id}/status", data={"csrf": csrf(r), "status": "arrived"})
        self.assertEqual(r.status_code, 303)
        with db.db() as c:
            self.assertEqual(c.execute("SELECT status FROM appointments WHERE id=?", (appt_id,)).fetchone()[0],
                             "arrived")
        # Arrived still blocks overlap
        r = self.book(a, self.doc_id, "تداخل", days=23, hour=9, minute=30)
        self.assertEqual(r.status_code, 400)
        self.assertIn("تداخل", r.text)
        # Completed still blocks
        r = a.get(f"/day/{jalali.jstr(date.fromisoformat(d))}")
        a.post(f"/appointments/{appt_id}/status", data={"csrf": csrf(r), "status": "completed"})
        r = self.book(a, self.doc_id, "تداخل۲", days=23, hour=9)
        self.assertEqual(r.status_code, 400)
        # Cancel frees the slot
        r = a.get(f"/day/{jalali.jstr(date.fromisoformat(d))}")
        a.post(f"/appointments/{appt_id}/cancel", data={"csrf": csrf(r)})
        r = self.book(a, self.doc_id, "آزاد", days=23, hour=9)
        self.assertEqual(r.status_code, 303)

    def test_staff_can_set_own_status_not_others(self):
        a = self.client("admin", "adminpass1")
        self.book(a, self.doc_id, "مال-من", days=24, hour=11)
        with db.db() as c:
            mine = c.execute("SELECT id FROM appointments WHERE initials='مال-من'").fetchone()[0]
            other_doc = db.create_user(c, "doc2", "دکتر ب", "doc2pass1")
        self.book(a, other_doc, "مال-او", days=24, hour=11)
        with db.db() as c:
            theirs = c.execute("SELECT id FROM appointments WHERE initials='مال-او'").fetchone()[0]
        d = self.client("doc", "docpass12")
        r = d.get("/me")
        r = d.post(f"/appointments/{mine}/status", data={"csrf": csrf(r), "status": "no_show"})
        self.assertEqual(r.status_code, 303)
        r = d.get("/me")
        r = d.post(f"/appointments/{theirs}/status", data={"csrf": csrf(r), "status": "arrived"})
        self.assertEqual(r.status_code, 403)

    def test_schedule_admin_page(self):
        a = self.client("admin", "adminpass1")
        r = a.get("/schedule")
        self.assertEqual(r.status_code, 200)
        self.assertIn("ساعت کاری", r.text)
        r = a.post("/schedule", data={
            "csrf": csrf(r), "action": "clinic_hours",
            "start_time": "07:30", "end_time": "20:00"})
        self.assertEqual(r.status_code, 303)
        with db.db() as c:
            start, end = schedule.get_hours(c, 0)
            self.assertEqual((start, end), ("07:30", "20:00"))
        d = self.client("doc", "docpass12")
        self.assertEqual(d.get("/schedule").status_code, 403)


if __name__ == "__main__":
    unittest.main()
