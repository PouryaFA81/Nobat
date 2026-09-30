# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command-line helper, run inside the container:

    docker compose exec nobat python -m app.manage create-admin
    docker compose exec nobat python -m app.manage reset-password <username>
    docker compose exec nobat python -m app.manage backup /data/backups/nobat-YYYY-MM-DD.db
"""
import getpass
import sys

from . import db


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


def main():
    db.init()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "create-admin":
        username = input("Username (English letters/numbers): ").strip().lower()
        name = input("Display name (can be Persian): ").strip()
        is_doctor = input("Does this person also receive appointments (counselor, doctor...)? [Y/n]: ").strip().lower() != "n"
        password = ask_password()
        with db.db() as c:
            db.create_user(c, username, name or username, password, is_admin=True, is_doctor=is_doctor)
        print(f"Admin '{username}' created.")
    elif cmd == "reset-password" and len(sys.argv) == 3:
        password = ask_password()
        with db.db() as c:
            n = c.execute("UPDATE users SET password_hash = ?, active = 1 WHERE username = ?",
                          (db.hash_password(password), sys.argv[2])).rowcount
        print("Password reset." if n else "No such user.")
    elif cmd == "backup" and len(sys.argv) == 3:
        # Safe copy of the live database (works while the panel is running).
        import os
        import sqlite3
        os.makedirs(os.path.dirname(sys.argv[2]) or ".", exist_ok=True)
        src = db.connect()
        dst = sqlite3.connect(sys.argv[2])
        src.backup(dst)
        dst.close()
        src.close()
        print(f"Backup written to {sys.argv[2]}")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
