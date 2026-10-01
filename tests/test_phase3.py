# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase 3: print CSS, CSV export, initials search, created_by on day rows."""
import asyncio
import logging
import os
import re
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

_tmp = tempfile.mkdtemp()
os.environ.update(DB_PATH=os.path.join(_tmp, "phase3.db"), SECRET_KEY="t" * 40,
                  COOKIE_SECURE="0", STAFF_LABEL="مشاور", TIMEZONE="Asia/Tehran")

from starlette.testclient import TestClient  # noqa: E402

from app import db, export_csv, jalali, main, notify  # noqa: E402

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


class Phase3ExportHelpers(unittest.TestCase):
    def test_csv_utf8_bom_and_no_notes_by_default(self):
        rows = [{
            "day": "2026-10-01", "start_time": "09:30", "staff_name": "دکتر الف",
            "initials": "س.م", "status": "arrived", "created_by_name": "مدیر",
            "description": "یادداشت محرمانه",
        }]
        raw = export_csv.build_csv(rows, staff_header="مشاور", include_notes=False)
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        text = raw.decode("utf-8-sig")
        self.assertIn("س.م", text)
        self.assertIn("حاضر", text)
        self.assertIn("مدیر", text)
        self.assertNotIn("محرمانه", text)
        self.assertNotIn("یادداشت", text.split("\n")[0])  # header has no notes col

    def test_csv_optional_notes_column(self):
        rows = [{
            "day": "2026-10-01", "start_time": "09:30", "staff_name": "دکتر الف",
            "initials": "س.م", "status": "active", "created_by_name": "مدیر",
            "description": "یادداشت محرمانه",
        }]
        text = export_csv.build_csv(rows, include_notes=True).decode("utf-8-sig")
        self.assertIn("یادداشت", text.split("\n")[0])
        self.assertIn("محرمانه", text)

    def test_year_choices_wider_than_plus_minus_one(self):
        years = main.year_choices(date(2026, 10, 1))
        ty = jalali.to_jalali(date(2026, 10, 1))[0]
        self.assertEqual(years[0], ty - main.YEAR_SPAN)
        self.assertEqual(years[-1], ty + main.YEAR_SPAN)
        self.assertGreaterEqual(len(years), 11)


class Phase3PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._db_dir = tempfile.mkdtemp()
        cls._old_db = db.DB_PATH
        db.DB_PATH = os.path.join(cls._db_dir, "phase3.db")
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

    def test_print_css_and_button_on_day_and_me(self):
        css = (main.HERE / "static" / "style.css").read_text()
        self.assertIn("@media print", css)
        self.assertIn(".no-print", css)
        a = self.client("admin", "adminpass1")
        d = self.book(a, self.doc_id, "چاپ")
        r = a.get(f"/day/{jalali.jstr(d)}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("data-print", r.text)
        self.assertIn(">چاپ<", r.text)
        self.assertIn("page-menu", r.text)
        self.assertIn("⋮", r.text)
        self.assertIn("no-print", r.text)
        doc = self.client("doc", "docpass12")
        r = doc.get("/me")
        self.assertEqual(r.status_code, 200)
        self.assertIn("data-print", r.text)

    def test_day_shows_created_by(self):
        a = self.client("admin", "adminpass1")
        d = self.book(a, self.doc_id, "ثبتک")
        r = a.get(f"/day/{jalali.jstr(d)}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("ثبت‌کننده", r.text)
        self.assertIn("مدیر", r.text)

    def test_export_admin_only_and_csv_content(self):
        a = self.client("admin", "adminpass1")
        d = self.book(a, self.doc_id, "خروجی", description="یادداشت سری")
        jy, jm, jd = jalali.to_jalali(d)
        r = a.get("/export")
        self.assertEqual(r.status_code, 200)
        self.assertIn("خروجی CSV", r.text)
        r = a.get("/export.csv", params={
            "from_jy": jy, "from_jm": jm, "from_jd": jd,
            "to_jy": jy, "to_jm": jm, "to_jd": jd,
        })
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.headers.get("content-type", ""))
        body = r.content
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))
        text = body.decode("utf-8-sig")
        self.assertIn("خروجی", text)
        self.assertIn("دکتر الف", text)
        self.assertIn("مدیر", text)
        self.assertNotIn("سری", text)
        # optional notes
        r = a.get("/export.csv", params={
            "from_jy": jy, "from_jm": jm, "from_jd": jd,
            "to_jy": jy, "to_jm": jm, "to_jd": jd, "notes": "1",
        })
        self.assertIn("سری", r.content.decode("utf-8-sig"))
        doc = self.client("doc", "docpass12")
        self.assertEqual(doc.get("/export").status_code, 403)
        self.assertEqual(doc.get("/export.csv").status_code, 403)

    def test_search_admin_all_staff_own(self):
        a = self.client("admin", "adminpass1")
        self.book(a, self.doc_id, "جستجوی‌الف")
        self.book(a, self.admin_id, "جستجوی‌ب", hour=17)
        r = a.get("/search", params={"q": "جستجوی"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("جستجوی‌الف", r.text)
        self.assertIn("جستجوی‌ب", r.text)
        self.assertIn("ثبت‌کننده", r.text)
        doc = self.client("doc", "docpass12")
        r = doc.get("/search", params={"q": "جستجوی"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("جستجوی‌الف", r.text)
        self.assertNotIn("جستجوی‌ب", r.text)

    def test_appt_form_year_span(self):
        a = self.client("admin", "adminpass1")
        r = a.get("/appointments/new")
        self.assertEqual(r.status_code, 200)
        ty = jalali.to_jalali(notify.now_local().date())[0]
        self.assertIn(f'value="{ty - main.YEAR_SPAN}"', r.text)
        self.assertIn(f'value="{ty + main.YEAR_SPAN}"', r.text)


if __name__ == "__main__":
    unittest.main()
