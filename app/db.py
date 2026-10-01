# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite storage. The whole database is one file: /data/nobat.db"""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", "/data/nobat.db")

# Bump when adding a numbered script under app/migrations/.
# Migration 0001 baseline; 0002 working hours; 0003 status docs; 0004 audit log;
# 0005 receptionist; 0006 recurring series; (later Phase 4 scripts bump further).
SCHEMA_VERSION = 6

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    is_doctor     INTEGER NOT NULL DEFAULT 1,
    is_receptionist INTEGER NOT NULL DEFAULT 0,
    active        INTEGER NOT NULL DEFAULT 1,
    ntfy_topic    TEXT NOT NULL UNIQUE,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS appointments (
    id            INTEGER PRIMARY KEY,
    doctor_id     INTEGER NOT NULL REFERENCES users(id),
    initials      TEXT NOT NULL,
    day           TEXT NOT NULL,          -- Gregorian YYYY-MM-DD, local time (TIMEZONE setting)
    start_time    TEXT NOT NULL,          -- HH:MM, local time (TIMEZONE setting)
    duration_min  INTEGER NOT NULL DEFAULT 60,
    description   TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'active',   -- active|arrived|no_show|completed|cancelled
    reminder_sent INTEGER NOT NULL DEFAULT 0,
    created_by    INTEGER REFERENCES users(id),
    series_id     TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS working_hours (
    doctor_id  INTEGER NOT NULL PRIMARY KEY,
    start_time TEXT NOT NULL DEFAULT '06:00',
    end_time   TEXT NOT NULL DEFAULT '24:00'
);
CREATE TABLE IF NOT EXISTS blocked_days (
    id         INTEGER PRIMARY KEY,
    day        TEXT NOT NULL,
    doctor_id  INTEGER NOT NULL DEFAULT 0,
    reason     TEXT NOT NULL DEFAULT '',
    UNIQUE (day, doctor_id)
);
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY,
    actor_user_id   INTEGER,
    actor_username  TEXT NOT NULL DEFAULT '',
    action          TEXT NOT NULL,
    appointment_id  INTEGER,
    detail          TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_appt_day ON appointments(day);
CREATE INDEX IF NOT EXISTS idx_appt_doctor ON appointments(doctor_id, day);
CREATE INDEX IF NOT EXISTS idx_appt_series ON appointments(series_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action, created_at);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()



def _table_columns(c: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in c.execute(f"PRAGMA table_info({table})")}


def _ensure_columns(c: sqlite3.Connection) -> None:
    """Idempotent ADD COLUMN / CREATE for Phase 4+ fields (safe on fresh + upgrade)."""
    tables = {r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "users" in tables:
        cols = _table_columns(c, "users")
        if "is_receptionist" not in cols:
            c.execute(
                "ALTER TABLE users ADD COLUMN is_receptionist INTEGER NOT NULL DEFAULT 0"
            )
    if "appointments" in tables:
        acols = _table_columns(c, "appointments")
        if "series_id" not in acols:
            c.execute("ALTER TABLE appointments ADD COLUMN series_id TEXT")
        c.execute("CREATE INDEX IF NOT EXISTS idx_appt_series ON appointments(series_id)")


def _migration_files() -> list[tuple[int, str, Path]]:
    """Return (version, name, path) for each *.sql script, sorted by version."""
    found: list[tuple[int, str, Path]] = []
    if not MIGRATIONS_DIR.is_dir():
        return found
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = re.match(r"^(\d+)_(.+)\.sql$", path.name)
        if not m:
            continue
        found.append((int(m.group(1)), m.group(2), path))
    return found


def current_migration_version(c: sqlite3.Connection) -> int:
    row = c.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()
    return int(row[0])


def migrate(c: sqlite3.Connection | None = None) -> list[int]:
    """Apply pending numbered SQL scripts. Returns list of newly applied versions.

    Safe to call repeatedly. Fresh installs get the full SCHEMA via init(), then
    migrate() records baseline (and any later) scripts. Upgrades apply only
    scripts newer than the highest recorded version.
    """
    own = c is None
    if own:
        conn = connect()
    else:
        conn = c
    applied: list[int] = []
    try:
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, "
            "name TEXT NOT NULL, "
            "applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        _ensure_columns(conn)
        have = current_migration_version(conn)
        for version, name, path in _migration_files():
            if version <= have:
                continue
            sql = path.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                (version, name),
            )
            applied.append(version)
        _ensure_columns(conn)
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()
    return applied


def init():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with db() as c:
        c.executescript(SCHEMA)
        migrate(c)


# ---------- passwords (scrypt, standard library only) ----------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, h_hex = stored.split("$")
        h = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
        return hmac.compare_digest(h.hex(), h_hex)
    except Exception:
        return False


def new_topic() -> str:
    # Long random name: nobody can guess it, so nobody else can subscribe.
    return "nb_" + secrets.token_urlsafe(18).replace("-", "x").replace("_", "y")


def create_user(c, username, name, password, is_admin=False, is_doctor=True,
                is_receptionist=False) -> int:
    cur = c.execute(
        "INSERT INTO users (username, name, password_hash, is_admin, is_doctor, "
        "is_receptionist, ntfy_topic) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (username.strip(), name.strip(), hash_password(password),
         int(is_admin), int(is_doctor), int(is_receptionist), new_topic()),
    )
    return cur.lastrowid
