# SPDX-License-Identifier: AGPL-3.0-or-later
"""Neumorphism theme tokens + Option A′ header chrome."""
import logging
import os
import re
import tempfile
import unittest
from unittest import mock

_tmp = tempfile.mkdtemp()
os.environ.update(DB_PATH=os.path.join(_tmp, "ui_themes.db"), SECRET_KEY="t" * 40,
                  COOKIE_SECURE="0", STAFF_LABEL="مشاور", TIMEZONE="Asia/Tehran")

from starlette.testclient import TestClient  # noqa: E402

from app import db, main, notify  # noqa: E402
import asyncio

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("nobat").setLevel(logging.WARNING)


async def idle_loop():
    await asyncio.sleep(3600)


class UiThemesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._db_dir = tempfile.mkdtemp()
        cls._old_db = db.DB_PATH
        db.DB_PATH = os.path.join(cls._db_dir, "ui_themes.db")
        cls.patches = [mock.patch.object(notify, "reminder_loop", idle_loop)]
        for p in cls.patches:
            p.start()
        db.init()
        with db.db() as c:
            db.create_user(c, "admin", "مدیر", "adminpass1", is_admin=True, is_doctor=False)
            db.create_user(c, "doc", "دکتر", "docpass12", is_admin=False, is_doctor=True)

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()
        db.DB_PATH = cls._old_db

    def client(self, username="admin", password="adminpass1"):
        c = TestClient(main.app, follow_redirects=False)
        r = c.get("/login")
        token = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
        c.post("/login", data={"csrf": token, "username": username, "password": password})
        return c

    def test_themes_css_file_exists_and_has_palettes(self):
        path = main.HERE / "static" / "themes.css"
        self.assertTrue(path.is_file(), "themes.css must ship in app/static")
        css = path.read_text()
        self.assertIn('[data-theme="yaru-orange"]', css)
        self.assertIn('[data-theme="teal"]', css)
        self.assertIn('[data-mode="dark"]', css)
        self.assertIn(".neu-raised", css)
        self.assertIn(".neu-btn", css)

    def test_themes_css_is_served(self):
        c = TestClient(main.app, follow_redirects=False)
        r = c.get("/static/themes.css")
        self.assertEqual(r.status_code, 200)
        self.assertIn("yaru-orange", r.text)
        self.assertIn("--brand", r.text)

    def test_theme_js_is_served(self):
        c = TestClient(main.app, follow_redirects=False)
        r = c.get("/static/theme.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("nobat-theme", r.text)
        self.assertIn("data-mode", r.text)

    def test_base_layout_links_themes_and_defaults(self):
        c = self.client()
        r = c.get("/calendar")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/static/themes.css", r.text)
        self.assertIn("/static/theme.js", r.text)
        self.assertIn('data-theme="yaru-orange"', r.text)
        self.assertIn("data-mode", r.text)
        self.assertIn("data-theme-mode", r.text)
        self.assertIn('data-theme-set="yaru-orange"', r.text)
        self.assertIn('data-theme-set="teal"', r.text)
        self.assertIn("تیره", r.text)
        self.assertIn("پالت", r.text)
        ti = r.text.find("/static/themes.css")
        si = r.text.find("/static/style.css")
        self.assertGreater(si, ti)
        self.assertGreater(ti, -1)

    def test_header_option_a_prime_chrome(self):
        """Primary header: only calendar/+; palette+admin under Account; mode beside Account."""
        c = self.client()
        r = c.get("/calendar")
        html = r.text
        self.assertIn('class="nav-primary"', html)
        self.assertIn('aria-label="تقویم"', html)
        self.assertIn('aria-label="نوبت جدید"', html)
        self.assertIn('class="mode-switch"', html)
        self.assertIn('aria-label="حساب"', html)
        # No header kebab / three-dot chrome control
        self.assertNotIn("سه نقطه", html)
        # Palette + admin tools live under Account menu groups
        self.assertIn(">ظاهر<", html)
        self.assertIn(">مدیریت<", html)
        self.assertIn(">حساب<", html)
        self.assertIn("همکاران", html)
        self.assertIn("ساعات کاری", html)
        self.assertIn("خروجی CSV", html)
        self.assertIn("گزارش فعالیت", html)
        # Search / my-schedule not as primary header links (in Account instead)
        self.assertIn('href="/search"', html)
        # Admin is not a doctor in this fixture — no برنامه من
        self.assertNotIn("برنامه من", html)
        # No standalone theme-controls chrome block
        self.assertNotIn("theme-controls", html)

    def test_doctor_header_has_me_under_account_not_primary(self):
        c = self.client("doc", "docpass12")
        r = c.get("/me")
        self.assertEqual(r.status_code, 200)
        self.assertIn("برنامه من", r.text)
        self.assertIn('href="/search"', r.text)
        self.assertNotIn('class="nav-primary"', r.text)
        self.assertNotIn('href="/users"', r.text)
        self.assertNotIn("خروجی CSV", r.text)

    def test_day_page_menu_bare_dots(self):
        c = self.client()
        # need a day URL — calendar today works via redirect path; use a fixed jalali-ish day page
        r = c.get("/calendar")
        self.assertEqual(r.status_code, 200)
        # pick first day link
        m = re.search(r'href="/day/(\d{4}-\d{2}-\d{2})', r.text)
        self.assertIsNotNone(m)
        r = c.get(f"/day/{m.group(1)}")
        self.assertEqual(r.status_code, 200)
        self.assertIn('class="page-menu"', r.text)
        self.assertIn(">⋮<", r.text)
        self.assertIn(">چاپ<", r.text)
        self.assertIn(">دانلود ICS<", r.text)
        self.assertNotIn("چاپ برگه روز", r.text)

    def test_me_page_menu_bare_dots(self):
        c = self.client("doc", "docpass12")
        r = c.get("/me")
        self.assertEqual(r.status_code, 200)
        self.assertIn('class="page-menu"', r.text)
        self.assertIn(">⋮<", r.text)
        self.assertIn(">چاپ<", r.text)
        self.assertIn(">دانلود ICS<", r.text)
        self.assertNotIn("دانلود تقویم (ICS)", r.text)

    def test_print_css_still_present(self):
        css = (main.HERE / "static" / "style.css").read_text()
        self.assertIn("@media print", css)
        self.assertIn(".no-print", css)
        self.assertIn(".mode-switch", css)
        self.assertIn(".nav-primary", css)
        self.assertIn(".page-menu", css)
        self.assertIn(".dots", css)

    def test_popover_panels_use_soft_drop_not_neu_outglow(self):
        css = (main.HERE / "static" / "style.css").read_text()
        # Shared panel rule should prefer soft drop + hairline over --shadow-out dual-tone
        self.assertIn(".menu-body, .page-menu-body", css)
        self.assertIn("0 8px 24px", css)
        self.assertIn("border: 1px solid", css)
        # Ensure we are not applying --shadow-out / --shadow-light halo on those panels
        block_start = css.find(".menu-body, .page-menu-body")
        block = css[block_start:block_start + 450]
        self.assertNotIn("--shadow-out", block)
        self.assertNotIn("--shadow-light", block)

    def test_style_no_longer_fights_with_prefers_color_scheme(self):
        css = (main.HERE / "static" / "style.css").read_text()
        self.assertNotIn("prefers-color-scheme", css)


if __name__ == "__main__":
    unittest.main()
