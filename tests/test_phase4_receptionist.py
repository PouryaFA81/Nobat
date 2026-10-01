# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase 4.2: receptionist role — book appointments; no user/admin settings."""
import asyncio
import logging
import os
import re
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

_tmp = tempfile.mkdtemp()
os.environ.update(DB_PATH=os.path.join(_tmp, "p4recv.db"), SECRET_KEY="t" * 40,
                  COOKIE_SECURE="0", STAFF_LABEL="مشاور", TIMEZONE="Asia/Tehran")

from starlette.testclient import TestClient  # noqa: E402

from app import db, jalali, main, notify  # noqa: E402

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("nobat").setLevel(logging.WARNING)


async def fake_send(topic, title, message, tags="calendar"):
    return True


async def idle_loop():
    await asyncio.sleep(3600)


def csrf(resp) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', resp.text).group(1)


class ReceptionistMigrationTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._old = db.DB_PATH
        db.DB_PATH = os.path.join(self.dir, "t.db")

    def tearDown(self):
        db.DB_PATH = self._old

    def test_schema_has_receptionist_and_version(self):
        db.init()
        with db.db() as c:
            self.assertEqual(db.current_migration_version(c), db.SCHEMA_VERSION)
            cols = {r[1] for r in c.execute("PRAGMA table_info(users)")}
            self.assertIn("is_receptionist", cols)
            names = {r["name"] for r in c.execute("SELECT name FROM schema_migrations")}
            self.assertIn("receptionist", names)


class ReceptionistAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._db_dir = tempfile.mkdtemp()
        cls._old_db = db.DB_PATH
        db.DB_PATH = os.path.join(cls._db_dir, "p4recv.db")
        cls.patches = [mock.patch.object(notify, "send", fake_send),
                       mock.patch.object(notify, "reminder_loop", idle_loop)]
        for p in cls.patches:
            p.start()
        db.init()
        with db.db() as c:
            cls.admin_id = db.create_user(c, "admin", "مدیر", "adminpass1",
                                          is_admin=True, is_doctor=False)
            cls.recv_id = db.create_user(c, "recv", "پذیرش", "recvpass1",
                                         is_admin=False, is_doctor=False,
                                         is_receptionist=True)
            cls.doc_id = db.create_user(c, "doc", "دکتر الف", "docpass12",
                                        is_admin=False, is_doctor=True)

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()
        db.DB_PATH = cls._old_db

    def setUp(self):
        main._failures.clear()
        with db.db() as c:
            c.execute("DELETE FROM appointments")

    def _login(self, client, username, password):
        r = client.get("/login")
        return client.post("/login", data={"csrf": csrf(r), "username": username,
                                           "password": password}, follow_redirects=False)

    def test_receptionist_home_goes_to_calendar(self):
        with TestClient(main.app) as client:
            r = self._login(client, "recv", "recvpass1")
            self.assertEqual(r.status_code, 303)
            r2 = client.get("/", follow_redirects=False)
            self.assertEqual(r2.headers.get("location"), "/calendar")

    def test_receptionist_can_book_and_cancel(self):
        day = date.today() + timedelta(days=3)
        jy, jm, jd = jalali.to_jalali(day)
        with TestClient(main.app) as client:
            self._login(client, "recv", "recvpass1")
            r = client.get("/appointments/new")
            self.assertEqual(r.status_code, 200)
            data = {
                "csrf": csrf(r), "doctor_id": str(self.doc_id), "initials": "ر.پ",
                "jy": str(jy), "jm": str(jm), "jd": str(jd),
                "hour": "10", "minute": "0", "duration": "60", "description": "محرمانه",
            }
            r2 = client.post("/appointments/new", data=data, follow_redirects=False)
            self.assertEqual(r2.status_code, 303)
            with db.db() as c:
                appt = c.execute("SELECT * FROM appointments WHERE initials = 'ر.پ'").fetchone()
                self.assertIsNotNone(appt)
                self.assertEqual(appt["created_by"], self.recv_id)
                appt_id = appt["id"]
            r3 = client.post(f"/appointments/{appt_id}/cancel",
                             data={"csrf": csrf(client.get(f"/day/{jalali.jstr(day)}"))},
                             follow_redirects=False)
            self.assertEqual(r3.status_code, 303)
            with db.db() as c:
                st = c.execute("SELECT status FROM appointments WHERE id = ?",
                               (appt_id,)).fetchone()["status"]
            self.assertEqual(st, "cancelled")

    def test_receptionist_forbidden_users_schedule_export_audit(self):
        with TestClient(main.app) as client:
            self._login(client, "recv", "recvpass1")
            for path in ("/users", "/schedule", "/export", "/audit"):
                r = client.get(path)
                self.assertEqual(r.status_code, 403, path)

    def test_receptionist_cannot_soft_delete_via_users(self):
        with TestClient(main.app) as client:
            self._login(client, "recv", "recvpass1")
            r = client.get("/users")
            # never reaches form; 403
            self.assertEqual(r.status_code, 403)
            r2 = client.post(f"/users/{self.doc_id}/delete", data={"csrf": "x"})
            self.assertEqual(r2.status_code, 403)

    def test_staff_cannot_access_calendar(self):
        with TestClient(main.app) as client:
            self._login(client, "doc", "docpass12")
            r = client.get("/calendar")
            self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
