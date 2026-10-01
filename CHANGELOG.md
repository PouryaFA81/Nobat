# Changelog

## [Unreleased]

### Added
- Working hours (clinic default + per-staff override) and blocked/holiday days with admin UI (`/schedule`); migration `0002`.
- Appointment statuses: arrived, no-show, completed (plus active/cancelled); status buttons on day and me views; migration `0003`.
- Database migration runner (`schema_migrations`, `python -m app.manage migrate`) with baseline `0001`.
- `backup` default path under `data/backups/`, plus `backup-prune` (default 14 days) and safe `restore` (`--force` / `--to`).
- Soft-delete (deactivate) as the default user removal path; hard delete only via `delete-user --confirm YES`.

### Changed
- Booking validation enforces working hours and blocked days; overlap treats only cancelled as free.
- User edit UI no longer offers permanent delete; appointments are retained when a colleague is deactivated.

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-09-30

First public release.

### Added
- Coordinator panel: Jalali month calendar, day view, and booking, moving, cancelling and restoring appointments.
- Overlap check: a staff member can't be booked twice at the same time.
- Private note per appointment, visible only to the coordinator and that staff member.
- Staff view: each staff member sees only their own upcoming and past appointments.
- Push notifications through a self-hosted ntfy server: booked, moved, cancelled, and an evening list of tomorrow's sessions.
- Staff management: add, edit, deactivate and delete colleagues, and reset passwords.
- Installable on phones (PWA), with a Persian interface, the Vazirmatn font and dark mode.
- Settings for time zone, reminder hour and the word used for staff members.
- Command-line tools: create admin, reset password, backup.
- Security: scrypt password hashing, CSRF protection, strict Content-Security-Policy, login rate limiting,
  and logout of other sessions after a password change.

[1.0.0]: https://github.com/PouryaFA81/Nobat/releases/tag/v1.0.0
