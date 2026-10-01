# SPDX-License-Identifier: AGPL-3.0-or-later
"""Neumorphism theme tokens: themes.css served and linked from base layout."""
import logging
import os
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

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()
        db.DB_PATH = cls._old_db

    def client(self):
        c = TestClient(main.app, follow_redirects=False)
        r = c.get("/login")
        import re
        token = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
        c.post("/login", data={"csrf": token, "username": "admin", "password": "adminpass1"})
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
        # themes.css before style.css
        ti = r.text.find("/static/themes.css")
        si = r.text.find("/static/style.css")
        self.assertGreater(si, ti)
        self.assertGreater(ti, -1)

    def test_print_css_still_present(self):
        css = (main.HERE / "static" / "style.css").read_text()
        self.assertIn("@media print", css)
        self.assertIn(".no-print", css)
        self.assertIn("theme-controls", css)

    def test_style_no_longer_fights_with_prefers_color_scheme(self):
        css = (main.HERE / "static" / "style.css").read_text()
        self.assertNotIn("prefers-color-scheme", css)


if __name__ == "__main__":
    unittest.main()
