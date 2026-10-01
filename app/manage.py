# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command-line helper, run inside the container:

    docker compose exec nobat python -m app.manage create-admin
    docker compose exec nobat python -m app.manage reset-password <username>
    docker compose exec nobat python -m app.manage migrate
    docker compose exec nobat python -m app.manage backup
    docker compose exec nobat python -m app.manage backup /data/backups/nobat-YYYY-MM-DD.db
    docker compose exec nobat python -m app.manage backup-prune
    docker compose exec nobat python -m app.manage backup-prune --days 14
    docker compose exec nobat python -m app.manage restore /data/backups/nobat-YYYY-MM-DD.db
    docker compose exec nobat python -m app.manage restore /data/backups/nobat-YYYY-MM-DD.db --force
    docker compose exec nobat python -m app.manage deactivate-user <username>
    docker compose exec nobat python -m app.manage delete-user <username> --confirm YES
"""
import argparse
import getpass
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import db

DEFAULT_BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "")) if os.environ.get("BACKUP_DIR") else None


def backup_dir() -> Path:
    """Directory for automatic backups (next to the live DB by default)."""
    if DEFAULT_BACKUP_DIR is not None:
        return DEFAULT_BACKUP_DIR
    parent = Path(db.DB_PATH).resolve().parent
    return parent / "backups"


def ask_password() -> str:
    while True:
        p1 = getpass.getpass("Password (min 8 chars): ")
        p2 = getpass.getpass("Repeat password: ")
        if len(p1) < 8:
            print("Too short.")
        elif p1 != p2:
            print("Passwords do not match.")
        else:
            return p1


def cmd_migrate(_args=None):
    db.init()
    applied = db.migrate()
    with db.db() as c:
        ver = db.current_migration_version(c)
    if applied:
        print(f"Applied migrations: {', '.join(str(v) for v in applied)}. Now at version {ver}.")
    else:
        print(f"Database already at version {ver} (SCHEMA_VERSION={db.SCHEMA_VERSION}).")


def cmd_backup(args):
    db.init()
    if args.path:
        dest = Path(args.path)
    else:
        bdir = backup_dir()
        stamp = datetime.now().strftime("%Y-%m-%d")
        dest = bdir / f"nobat-{stamp}.db"
        # If today's file exists, add a time suffix to avoid silent overwrite.
        if dest.exists():
            stamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
            dest = bdir / f"nobat-{stamp}.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = db.connect()
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    print(f"Backup written to {dest}")


def cmd_backup_prune(args):
    days = args.days
    if days < 1:
        print("Keep days must be at least 1.", file=sys.stderr)
        sys.exit(1)
    bdir = backup_dir()
    if not bdir.is_dir():
        print(f"No backup directory at {bdir}; nothing to prune.")
        return
    cutoff = datetime.now() - timedelta(days=days)
    removed = 0
    kept = 0
    for path in sorted(bdir.glob("nobat-*.db")):
        # Prefer mtime; refuse to delete files that don't look like our backups.
        if not re.match(r"^nobat-.+\.db$", path.name):
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if mtime < cutoff:
            path.unlink()
            print(f"Removed {path}")
            removed += 1
        else:
            kept += 1
    print(f"Prune done: removed {removed}, kept {kept} (retention {days} days) under {bdir}")


def cmd_restore(args):
    src = Path(args.path)
    if not src.is_file():
        print(f"Backup not found: {src}", file=sys.stderr)
        sys.exit(1)
    # Quick sanity: must open as SQLite and have users or schema_migrations.
    try:
        check = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        try:
            tables = {r[0] for r in check.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        finally:
            check.close()
    except sqlite3.Error as e:
        print(f"Not a readable SQLite database: {e}", file=sys.stderr)
        sys.exit(1)
    if "users" not in tables and "appointments" not in tables:
        print("File does not look like a Nobat database (no users/appointments tables).",
              file=sys.stderr)
        sys.exit(1)

    live = Path(db.DB_PATH)
    if args.to:
        dest = Path(args.to)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        print(f"Restored copy written to {dest} (live DB untouched).")
        return

    if dest_is_live_and_exists := live.exists():
        if not args.force:
            print(
                f"Refusing to overwrite live database {live}.\n"
                f"  Use --force to replace it, or --to PATH to restore to another file.",
                file=sys.stderr,
            )
            sys.exit(2)

    live.parent.mkdir(parents=True, exist_ok=True)
    # Copy via sqlite backup API into a temp file then replace, to avoid
    # corrupting a running WAL DB mid-write when possible.
    tmp = live.with_suffix(live.suffix + ".restore-tmp")
    try:
        sconn = sqlite3.connect(str(src))
        try:
            dconn = sqlite3.connect(str(tmp))
            try:
                sconn.backup(dconn)
            finally:
                dconn.close()
        finally:
            sconn.close()
        os.replace(tmp, live)
        # Drop stale WAL/SHM from the previous live file if present.
        for suffix in ("-wal", "-shm"):
            side = Path(str(live) + suffix)
            if side.exists():
                side.unlink()
    finally:
        if tmp.exists():
            tmp.unlink()
    action = "overwrote" if dest_is_live_and_exists else "wrote"
    print(f"Restore {action} live database at {live}")


def cmd_deactivate_user(args):
    db.init()
    username = args.username.strip().lower()
    with db.db() as c:
        row = c.execute("SELECT id, name, active FROM users WHERE username = ?", (username,)).fetchone()
        if not row:
            print("No such user.", file=sys.stderr)
            sys.exit(1)
        if not row["active"]:
            print(f"User '{username}' is already deactivated.")
            return
        c.execute("UPDATE users SET active = 0 WHERE id = ?", (row["id"],))
    print(f"User '{username}' ({row['name']}) deactivated. Appointments retained; login blocked.")


def cmd_delete_user(args):
    """Permanently delete a user and their appointments. Requires --confirm YES."""
    if args.confirm != "YES":
        print(
            "Hard delete permanently removes the user and their appointments.\n"
            "Prefer: python -m app.manage deactivate-user USERNAME\n"
            "To proceed, re-run with: --confirm YES",
            file=sys.stderr,
        )
        sys.exit(1)
    db.init()
    username = args.username.strip().lower()
    with db.db() as c:
        row = c.execute("SELECT id, name FROM users WHERE username = ?", (username,)).fetchone()
        if not row:
            print("No such user.", file=sys.stderr)
            sys.exit(1)
        uid = row["id"]
        n_appts = c.execute("SELECT COUNT(*) FROM appointments WHERE doctor_id = ?", (uid,)).fetchone()[0]
        c.execute("DELETE FROM appointments WHERE doctor_id = ?", (uid,))
        c.execute("UPDATE appointments SET created_by = NULL WHERE created_by = ?", (uid,))
        c.execute("DELETE FROM users WHERE id = ?", (uid,))
    print(f"Permanently deleted '{username}' ({row['name']}) and {n_appts} appointment(s).")


def cmd_create_admin(_args=None):
    db.init()
    username = input("Username (English letters/numbers): ").strip().lower()
    name = input("Display name (can be Persian): ").strip()
    is_doctor = input("Does this person also receive appointments (counselor, doctor...)? [Y/n]: ").strip().lower() != "n"
    password = ask_password()
    with db.db() as c:
        db.create_user(c, username, name or username, password, is_admin=True, is_doctor=is_doctor)
    print(f"Admin '{username}' created.")


def cmd_reset_password(args):
    db.init()
    password = ask_password()
    with db.db() as c:
        n = c.execute("UPDATE users SET password_hash = ?, active = 1 WHERE username = ?",
                      (db.hash_password(password), args.username)).rowcount
    print("Password reset." if n else "No such user.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m app.manage",
        description="Nobat admin CLI (run inside the container).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("migrate", help="Apply pending database migrations")
    sp.set_defaults(func=cmd_migrate)

    sp = sub.add_parser("backup", help="Copy the live database (default: data/backups/nobat-YYYY-MM-DD.db)")
    sp.add_argument("path", nargs="?", default=None, help="Optional destination path")
    sp.set_defaults(func=cmd_backup)

    sp = sub.add_parser("backup-prune", help="Delete backups older than N days (default 14)")
    sp.add_argument("--days", type=int, default=14, help="Retention in days (default 14)")
    sp.set_defaults(func=cmd_backup_prune)

    sp = sub.add_parser("restore", help="Restore a backup (refuses to overwrite live DB without --force)")
    sp.add_argument("path", help="Path to a backup .db file")
    sp.add_argument("--force", action="store_true", help="Overwrite the live database")
    sp.add_argument("--to", dest="to", default=None, help="Restore to this path instead of the live DB")
    sp.set_defaults(func=cmd_restore)

    sp = sub.add_parser("deactivate-user", help="Soft-delete: block login, keep appointments")
    sp.add_argument("username")
    sp.set_defaults(func=cmd_deactivate_user)

    sp = sub.add_parser("delete-user", help="Hard-delete user and appointments (requires --confirm YES)")
    sp.add_argument("username")
    sp.add_argument("--confirm", default="", help="Must be exactly YES to proceed")
    sp.set_defaults(func=cmd_delete_user)

    sp = sub.add_parser("create-admin", help="Create the first admin account")
    sp.set_defaults(func=cmd_create_admin)

    sp = sub.add_parser("reset-password", help="Reset a user's password and re-activate them")
    sp.add_argument("username")
    sp.set_defaults(func=cmd_reset_password)

    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Backward-compatible: old "backup /path" without argparse subcommand quirks.
    parser = build_parser()
    if not argv:
        parser.print_help()
        sys.exit(1)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
