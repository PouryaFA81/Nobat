# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase 2: audit log and reminder durability (catch-up / idempotency)."""
import asyncio
import logging
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

_tmp = tempfile.mkdtemp()
os.environ.update(DB_PATH=os.path.join(_tmp, "phase2.db"), SECRET_KEY="t" * 40,
                  COOKIE_SECURE="0", STAFF_LABEL="مشاور", TIMEZONE="Asia/Tehran")

from starlette.testclient import TestClient  # noqa: E402

from app import audit, db, jalali, main, notify  # noqa: E402

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("nobat").setLevel(logging.WARNING)

SENT: list[dict] = []


async def fake_send(topic, title, message, tags="calendar"):
    SENT.append({"topic": topic, "title": title, "message": message, "tags": tags})
    return True


async def idle_loop():
    await asyncio.sleep(3600)


def csrf(resp) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', resp.text).group(1)


class Phase2AuditHelpers(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._old = db.DB_PATH
        db.DB_PATH = os.path.join(self.dir, "a.db")
        db.init()

    def tearDown(self):
        db.DB_PATH = self._old

    def test_migration_creates_audit_log(self):
        with db.db() as c:
            self.assertEqual(db.current_migration_version(c), db.SCHEMA_VERSION)
            tables = {r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        self.assertIn("audit_log", tables)
        self.assertEqual(db.SCHEMA_VERSION, 4)

    def test_record_fail_safe_does_not_raise(self):
        with db.db() as c:
            uid = db.create_user(c, "a", "A", "password12", is_admin=True)

        class Boom:
            def execute(self, *a, **k):
                raise RuntimeError("disk full")

            def commit(self):
                pass

        # Separate-connection path: patch db.db context to raise on insert
        with mock.patch.object(db, "db") as mdb:
            class Ctx:
                def __enter__(self):
                    return Boom()

                def __exit__(self, *a):
                    return False

            mdb.return_value = Ctx()
            audit.record({"id": uid, "username": "a"}, audit.BOOK, appointment_id=1)
        # Still alive; no exception

    def test_record_on_shared_connection(self):
        with db.db() as c:
            uid = db.create_user(c, "b", "B", "password12", is_admin=True)
            c.execute(
                "INSERT INTO appointments (doctor_id, initials, day, start_time, duration_min) "
                "VALUES (?, 'XX', '2099-01-01', '10:00', 60)", (uid,))
            appt_id = c.execute("SELECT id FROM appointments").fetchone()[0]
            audit.record({"id": uid, "username": "b"}, audit.BOOK,
                         appointment_id=appt_id, conn=c, detail={"day": "2099-01-01"})
            row = c.execute("SELECT action, appointment_id FROM audit_log").fetchone()
            self.assertEqual(row["action"], audit.BOOK)
            self.assertEqual(row["appointment_id"], appt_id)

    def test_audit_failure_does_not_rollback_booking(self):
        """If audit_log is missing mid-flight, booking row must remain."""
        with db.db() as c:
            uid = db.create_user(c, "c", "C", "password12", is_admin=True)
            c.execute("ALTER TABLE audit_log RENAME TO audit_log_hidden")
            c.execute(
                "INSERT INTO appointments (doctor_id, initials, day, start_time, duration_min) "
                "VALUES (?, 'YY', '2099-02-01', '11:00', 60)", (uid,))
            appt_id = c.execute("SELECT id FROM appointments WHERE initials='YY'").fetchone()[0]
            audit.record({"id": uid, "username": "c"}, audit.BOOK,
                         appointment_id=appt_id, conn=c, detail={"x": 1})
            still = c.execute("SELECT id FROM appointments WHERE id = ?", (appt_id,)).fetchone()
            self.assertIsNotNone(still)
            c.execute("ALTER TABLE audit_log_hidden RENAME TO audit_log")


class Phase2PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._db_dir = tempfile.mkdtemp()
        cls._old_db = db.DB_PATH
        db.DB_PATH = os.path.join(cls._db_dir, "phase2.db")
        cls.patches = [mock.patch.object(notify, "send", fake_send),
                       mock.patch.object(notify, "reminder_loop", idle_loop)]
        for p in cls.patches:
            p.start()
        db.init()
        with db.db() as c:
            cls.admin_id = db.create_user(c, "admin", "مدیر", "adminpass1",
                                          is_admin=True, is_doctor=True)
            cls.doc_id = db.create_user(c, "doc", "دکتر الف", "docpass12")
            assert db.current_migration_version(c) == db.SCHEMA_VERSION

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
            c.execute("DELETE FROM audit_log")
            c.execute("DELETE FROM blocked_days")

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

    def book(self, c, doctor_id, initials, days=10, hour=16, minute=0, duration=60, description=""):
        d, (jy, jm, jd) = self.future_day(days)
        r = c.get(f"/appointments/new?day={jalali.jstr(d)}")
        r = c.post("/appointments/new", data={
            "csrf": csrf(r), "doctor_id": doctor_id, "initials": initials,
            "jy": jy, "jm": jm, "jd": jd, "hour": hour, "minute": minute,
            "duration": duration, "description": description,
        })
        self.assertEqual(r.status_code, 303, r.text[:300])
        return d

    def test_book_writes_audit_without_notes(self):
        a = self.client("admin", "adminpass1")
        self.book(a, self.doc_id, "آ ب", description="یادداشت محرمانه")
        with db.db() as c:
            rows = c.execute("SELECT * FROM audit_log WHERE action = ?", (audit.BOOK,)).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["actor_username"], "admin")
        self.assertNotIn("محرمانه", rows[0]["detail"] or "")
        self.assertIn("آ ب", rows[0]["detail"])

    def test_cancel_and_status_audited(self):
        a = self.client("admin", "adminpass1")
        self.book(a, self.doc_id, "س ت")
        with db.db() as c:
            appt_id = c.execute("SELECT id FROM appointments").fetchone()[0]
        r = a.get(f"/day/{jalali.jstr(self.future_day()[0])}")
        # status change
        r = a.post(f"/appointments/{appt_id}/status",
                   data={"csrf": csrf(r), "status": "arrived"})
        self.assertEqual(r.status_code, 303)
        r = a.get(f"/day/{jalali.jstr(self.future_day()[0])}")
        r = a.post(f"/appointments/{appt_id}/cancel", data={"csrf": csrf(r)})
        self.assertEqual(r.status_code, 303)
        with db.db() as c:
            actions = [x["action"] for x in c.execute(
                "SELECT action FROM audit_log ORDER BY id").fetchall()]
        self.assertIn(audit.BOOK, actions)
        self.assertIn(audit.STATUS_CHANGE, actions)
        self.assertIn(audit.CANCEL, actions)

    def test_audit_ui_admin_only(self):
        a = self.client("admin", "adminpass1")
        self.book(a, self.doc_id, "ادیت")
        r = a.get("/audit")
        self.assertEqual(r.status_code, 200)
        self.assertIn("گزارش فعالیت", r.text)
        self.assertIn("ثبت نوبت", r.text)
        d = self.client("doc", "docpass12")
        r = d.get("/audit")
        self.assertEqual(r.status_code, 403)

    def test_deactivate_audited(self):
        a = self.client("admin", "adminpass1")
        with db.db() as c:
            uid = db.create_user(c, "tempuser", "موقت", "temppass1")
        r = a.get(f"/users/{uid}/edit")
        r = a.post(f"/users/{uid}/delete", data={"csrf": csrf(r)})
        self.assertEqual(r.status_code, 303)
        with db.db() as c:
            row = c.execute(
                "SELECT * FROM audit_log WHERE action = ?", (audit.USER_DEACTIVATE,)
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn("tempuser", row["detail"])



if __name__ == "__main__":
    unittest.main()
