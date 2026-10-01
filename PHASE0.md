# Phase 0 — Safety net

## What changed

### 0.1 Migrations
- New `schema_migrations` table and `app.db.migrate()`.
- Numbered SQL scripts live in `app/migrations/` (starting with `0001_baseline.sql`, a no-op that records the baseline matching `SCHEMA` / `SCHEMA_VERSION` in `app/db.py`).
- `db.init()` still bootstraps fresh databases with `CREATE IF NOT EXISTS`, then applies pending migrations.
- CLI: `python -m app.manage migrate`

### 0.2 Backup / prune / restore
- `backup` — optional path; default writes `…/backups/nobat-YYYY-MM-DD.db` next to the live DB (`/data/backups/` in Docker).
- `backup-prune --days 14` — deletes `nobat-*.db` backups older than N days (default 14).
- `restore PATH` — refuses to overwrite the live DB unless `--force`; use `--to PATH` to restore to another file without touching live data.

### 0.3 Soft-delete users
- Prefer deactivation (`users.active = 0`). Deactivated users cannot log in; appointments are kept.
- UI: hard-delete button removed; use the «حساب فعال است» checkbox (or POST `/users/{id}/delete`, which now deactivates).
- Hard delete only via CLI: `python -m app.manage delete-user USERNAME --confirm YES`
- Soft delete via CLI: `python -m app.manage deactivate-user USERNAME`

## How to run

```bash
# Inside the container (or with DB_PATH set locally)
python -m app.manage migrate
python -m app.manage backup
python -m app.manage backup-prune --days 14
python -m app.manage restore /data/backups/nobat-YYYY-MM-DD.db --to /data/restored.db
python -m app.manage restore /data/backups/nobat-YYYY-MM-DD.db --force   # overwrites live DB
python -m app.manage deactivate-user alice
python -m app.manage delete-user alice --confirm YES
```

Tests:

```bash
python -m unittest discover -s tests -t . -v
```

## Rollback notes

- **Migrations:** `0001_baseline` only inserts a row into `schema_migrations`. Rolling back Phase 0 code leaves that table/row harmlessly. No destructive DDL.
- **Backups:** prune only removes files under the backups directory matching `nobat-*.db`; it never touches the live DB.
- **Restore:** without `--force`, live data is never overwritten.
- **Soft-delete:** re-activate a user in the UI (check «حساب فعال است») or `UPDATE users SET active = 1 WHERE username = …`. Hard delete is irreversible except from a backup.
