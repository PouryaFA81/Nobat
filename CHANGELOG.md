# Changelog

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
