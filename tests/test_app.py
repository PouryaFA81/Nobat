# SPDX-License-Identifier: AGPL-3.0-or-later
"""End-to-end tests of the panel through its web interface.

Notifications are captured instead of being sent to a real ntfy server.
"""
import asyncio
import logging
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

_tmp = tempfile.mkdtemp()
os.environ.update(DB_PATH=os.path.join(_tmp, "test.db"), SECRET_KEY="t" * 40,
                  COOKIE_SECURE="0", STAFF_LABEL="مشاور", TIMEZONE="Asia/Tehran")

from starlette.testclient import TestClient  # noqa: E402

from app import db, jalali, main, notify  # noqa: E402

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


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patches = [mock.patch.object(notify, "send", fake_send),
                       mock.patch.object(notify, "reminder_loop", idle_loop)]
        for p in cls.patches:
            p.start()
        db.init()
        with db.db() as c:
            cls.admin_id = db.create_user(c, "admin", "مدیر", "adminpass1", is_admin=True, is_doctor=True)
            cls.doc_id = db.create_user(c, "doc", "دکتر الف", "docpass12")
            cls.other_id = db.create_user(c, "other", "دکتر ب", "otherpass1")

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()

    def setUp(self):
        SENT.clear()
        main._failures.clear()

    # ---------- helpers
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
        return c.post("/appointments/new", data={
            "csrf": csrf(r), "doctor_id": doctor_id, "initials": initials, "jy": jy, "jm": jm, "jd": jd,
            "hour": hour, "minute": minute, "duration": duration, "description": description})

    # ---------- tests
    def test_login_rejects_wrong_password(self):
        c = TestClient(main.app, follow_redirects=False)
        r = c.get("/login")
        r = c.post("/login", data={"csrf": csrf(r), "username": "admin", "password": "wrong-password"})
        self.assertEqual(r.status_code, 401)

    def test_booking_notifies_only_that_staff_member(self):
        a = self.client("admin", "adminpass1")
        r = self.book(a, self.doc_id, "ع.م", description="جلسه اول")
        self.assertEqual(r.status_code, 303)
        self.assertEqual(len(SENT), 1)
        with db.db() as c:
            topic = c.execute("SELECT ntfy_topic FROM users WHERE id = ?", (self.doc_id,)).fetchone()[0]
        self.assertEqual(SENT[0]["topic"], topic)
        self.assertIn("ع.م", SENT[0]["message"])
        self.assertNotIn("جلسه اول", SENT[0]["message"], "descriptions must never be sent in notifications")

    def test_overlapping_appointment_is_refused(self):
        a = self.client("admin", "adminpass1")
        self.book(a, self.doc_id, "الف", days=11, hour=10)
        r = self.book(a, self.doc_id, "ب", days=11, hour=10, minute=30)
        self.assertEqual(r.status_code, 400)
        self.assertIn("تداخل", r.text)
        # A different staff member at the same time is fine
        r = self.book(a, self.other_id, "ج", days=11, hour=10, minute=30)
        self.assertEqual(r.status_code, 303)

    def test_staff_sees_only_own_appointments_and_cannot_edit(self):
        a = self.client("admin", "adminpass1")
        self.book(a, self.doc_id, "مال-دکتر-الف", days=12, description="یادداشت الف")
        self.book(a, self.other_id, "مال-دکتر-ب", days=12, description="یادداشت ب")
        d = self.client("doc", "docpass12")
        r = d.get("/me")
        self.assertIn("مال-دکتر-الف", r.text)
        self.assertIn("یادداشت الف", r.text)
        self.assertNotIn("مال-دکتر-ب", r.text)
        self.assertEqual(d.get("/calendar").status_code, 403)
        self.assertEqual(d.get("/users").status_code, 403)

    def test_move_and_cancel_send_notifications(self):
        a = self.client("admin", "adminpass1")
        self.book(a, self.doc_id, "جابه‌جا", days=13, hour=9)
        with db.db() as c:
            appt_id = c.execute("SELECT id FROM appointments WHERE initials = 'جابه‌جا'").fetchone()[0]
        SENT.clear()
        d, (jy, jm, jd) = self.future_day(14)
        r = a.get(f"/appointments/{appt_id}/edit")
        a.post(f"/appointments/{appt_id}/edit", data={
            "csrf": csrf(r), "doctor_id": self.doc_id, "initials": "جابه‌جا", "jy": jy, "jm": jm, "jd": jd,
            "hour": 11, "minute": 0, "duration": 60, "description": ""})
        self.assertEqual(SENT[-1]["title"], "تغییر زمان نوبت")
        r = a.get(f"/day/{jalali.jstr(d)}")
        a.post(f"/appointments/{appt_id}/cancel", data={"csrf": csrf(r)})
        self.assertEqual(SENT[-1]["title"], "لغو نوبت")

    def test_post_without_csrf_is_rejected(self):
        a = self.client("admin", "adminpass1")
        r = a.post("/users/new", data={"name": "x", "username": "x", "password": "12345678"})
        self.assertEqual(r.status_code, 400)

    def test_delete_user_removes_their_appointments(self):
        a = self.client("admin", "adminpass1")
        with db.db() as c:
            uid = db.create_user(c, "temp", "موقت", "temppass1")
        self.book(a, uid, "موقت-۱", days=15)
        r = a.get(f"/users/{uid}/edit")
        r = a.post(f"/users/{uid}/delete", data={"csrf": csrf(r)})
        self.assertEqual(r.status_code, 303)
        with db.db() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone())
            self.assertIsNone(c.execute("SELECT 1 FROM appointments WHERE doctor_id = ?", (uid,)).fetchone())

    def test_admin_cannot_delete_self(self):
        a = self.client("admin", "adminpass1")
        r = a.get(f"/users/{self.admin_id}/edit")
        a.post(f"/users/{self.admin_id}/delete", data={"csrf": csrf(r)})
        with db.db() as c:
            self.assertIsNotNone(c.execute("SELECT 1 FROM users WHERE id = ?", (self.admin_id,)).fetchone())

    def test_password_reset_logs_out_other_sessions(self):
        d = self.client("other", "otherpass1")
        self.assertEqual(d.get("/me").status_code, 200)
        a = self.client("admin", "adminpass1")
        r = a.get(f"/users/{self.other_id}/edit")
        a.post(f"/users/{self.other_id}/edit", data={
            "csrf": csrf(r), "name": "دکتر ب", "password": "newpass123", "is_doctor": "1", "active": "1"})
        r = d.get("/me")
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/login")
        with db.db() as c:  # restore for other tests
            c.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                      (db.hash_password("otherpass1"), self.other_id))

    def test_evening_reminder_is_sent_once(self):
        a = self.client("admin", "adminpass1")
        self.book(a, self.doc_id, "یادآوری", days=2, hour=8)
        tomorrow_evening = datetime.combine(notify.now_local().date() + timedelta(days=1),
                                            datetime.min.time()).replace(hour=notify.REMINDER_HOUR)
        SENT.clear()
        with mock.patch.object(notify, "now_local", return_value=tomorrow_evening):
            asyncio.run(notify.send_due_reminders())
            asyncio.run(notify.send_due_reminders())
        reminders = [s for s in SENT if "یادآوری" in s["title"] and "یادآوری" in s["message"]]
        self.assertEqual(len(reminders), 1)

    def test_security_headers_and_source_link(self):
        a = self.client("admin", "adminpass1")
        r = a.get("/calendar")
        self.assertIn("content-security-policy", r.headers)
        self.assertEqual(r.headers["x-frame-options"], "DENY")
        self.assertIn(main.SOURCE_URL, r.text, "AGPL: the source code link must be shown")


if __name__ == "__main__":
    unittest.main()
