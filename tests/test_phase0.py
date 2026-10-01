# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase 0: migrations, backup/restore safety, soft-delete users."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_tmp = tempfile.mkdtemp()
os.environ.setdefault("DB_PATH", os.path.join(_tmp, "phase0.db"))
os.environ.setdefault("SECRET_KEY", "t" * 40)
os.environ.setdefault("COOKIE_SECURE", "0")

from app import db  # noqa: E402
from app import manage  # noqa: E402


class MigrateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.dir, "t.db")
        self._old = db.DB_PATH
        db.DB_PATH = self.db_path

    def tearDown(self):
        db.DB_PATH = self._old

    def test_init_records_baseline_migration(self):
        db.init()
        with db.db() as c:
            ver = db.current_migration_version(c)
            row = c.execute("SELECT name FROM schema_migrations WHERE version = 1").fetchone()
        self.assertEqual(ver, db.SCHEMA_VERSION)
        self.assertEqual(row["name"], "baseline")
        # Tables from SCHEMA exist
        with db.db() as c:
            tables = {r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        self.assertIn("users", tables)
        self.assertIn("schema_migrations", tables)

    def test_migrate_is_idempotent(self):
        db.init()
        again = db.migrate()
        self.assertEqual(again, [])
        with db.db() as c:
            self.assertEqual(db.current_migration_version(c), db.SCHEMA_VERSION)

    def test_pending_migration_is_applied(self):
        db.init()
        mig_dir = Path(self.dir) / "migrations"
        mig_dir.mkdir()
        probe_ver = db.SCHEMA_VERSION + 1
        script = mig_dir / f"{probe_ver:04d}_phase0_test.sql"
        script.write_text(
            "CREATE TABLE IF NOT EXISTS phase0_probe (id INTEGER PRIMARY KEY);\n",
            encoding="utf-8",
        )
        with mock.patch.object(db, "MIGRATIONS_DIR", mig_dir):
            # Pretend a newer script exists as pending: current SCHEMA already recorded.
            combined = Path(db.__file__).parent / "migrations"

            def files():
                out = []
                for path in sorted(combined.glob("*.sql")):
                    import re
                    m = re.match(r"^(\d+)_(.+)\.sql$", path.name)
                    if m:
                        out.append((int(m.group(1)), m.group(2), path))
                out.append((probe_ver, "phase0_test", script))
                return sorted(out)

            with mock.patch.object(db, "_migration_files", files):
                applied = db.migrate()
        self.assertEqual(applied, [probe_ver])
        with db.db() as c:
            self.assertEqual(db.current_migration_version(c), probe_ver)
            self.assertIsNotNone(c.execute(
                "SELECT 1 FROM sqlite_master WHERE name='phase0_probe'").fetchone())


class BackupRestoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.dir, "live.db")
        self.bdir = Path(self.dir) / "backups"
        self._old_db = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init()
        with db.db() as c:
            db.create_user(c, "admin", "Admin", "adminpass1", is_admin=True)

    def tearDown(self):
        db.DB_PATH = self._old_db

    def test_backup_default_path_and_prune(self):
        with mock.patch.object(manage, "DEFAULT_BACKUP_DIR", self.bdir):
            manage.cmd_backup(argparse_ns(path=None))
            files = list(self.bdir.glob("nobat-*.db"))
            self.assertEqual(len(files), 1)
            # Make an old backup and prune it
            old = self.bdir / "nobat-2000-01-01.db"
            old.write_bytes(files[0].read_bytes())
            os.utime(old, (0, 0))
            manage.cmd_backup_prune(argparse_ns(days=14))
            self.assertFalse(old.exists())
            self.assertTrue(files[0].exists())

    def test_restore_refuses_overwrite_without_force(self):
        bak = Path(self.dir) / "snap.db"
        with mock.patch.object(manage, "DEFAULT_BACKUP_DIR", self.bdir):
            manage.cmd_backup(argparse_ns(path=str(bak)))
        with self.assertRaises(SystemExit) as cm:
            manage.cmd_restore(argparse_ns(path=str(bak), force=False, to=None))
        self.assertEqual(cm.exception.code, 2)
        # Live DB still has the admin user
        with db.db() as c:
            self.assertIsNotNone(c.execute("SELECT 1 FROM users WHERE username='admin'").fetchone())

    def test_restore_to_path_leaves_live_untouched(self):
        bak = Path(self.dir) / "snap.db"
        out = Path(self.dir) / "restored.db"
        manage.cmd_backup(argparse_ns(path=str(bak)))
        # Corrupt "identity" of live by adding a second user, then restore to --to
        with db.db() as c:
            db.create_user(c, "other", "Other", "otherpass1")
        manage.cmd_restore(argparse_ns(path=str(bak), force=False, to=str(out)))
        with db.db() as c:
            n = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        self.assertEqual(n, 2)  # live unchanged
        conn = sqlite3.connect(str(out))
        try:
            n2 = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(n2, 1)

    def test_restore_force_overwrites_live(self):
        bak = Path(self.dir) / "snap.db"
        manage.cmd_backup(argparse_ns(path=str(bak)))
        with db.db() as c:
            db.create_user(c, "extra", "Extra", "extrapass1")
            self.assertEqual(c.execute("SELECT COUNT(*) FROM users").fetchone()[0], 2)
        manage.cmd_restore(argparse_ns(path=str(bak), force=True, to=None))
        with db.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)


class SoftDeleteCliTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.dir, "t.db")
        self._old = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init()
        with db.db() as c:
            db.create_user(c, "doc", "دکتر", "docpass12")

    def tearDown(self):
        db.DB_PATH = self._old

    def test_deactivate_blocks_flag(self):
        manage.cmd_deactivate_user(argparse_ns(username="doc"))
        with db.db() as c:
            row = c.execute("SELECT active FROM users WHERE username='doc'").fetchone()
            self.assertEqual(row["active"], 0)

    def test_delete_user_requires_confirm(self):
        with self.assertRaises(SystemExit):
            manage.cmd_delete_user(argparse_ns(username="doc", confirm="no"))
        with db.db() as c:
            self.assertIsNotNone(c.execute("SELECT 1 FROM users WHERE username='doc'").fetchone())

    def test_delete_user_with_confirm(self):
        manage.cmd_delete_user(argparse_ns(username="doc", confirm="YES"))
        with db.db() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM users WHERE username='doc'").fetchone())


def argparse_ns(**kwargs):
    return type("NS", (), kwargs)()


if __name__ == "__main__":
    unittest.main()
