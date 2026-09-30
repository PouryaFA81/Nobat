<p align="center">
  <img src="app/static/icons/icon-192.png" width="96" alt="Nobat icon">
</p>

<h1 align="center">Nobat · نوبت</h1>

<p align="center">
  A small, private, self-hosted appointment panel for clinics and counseling practices.<br>
  Persian interface · Jalali calendar · phone notifications · no third-party services.
</p>

<p align="center">
  <a href="README.fa.md">فارسی</a> ·
  <a href="docs/INSTALL.md">Install</a> ·
  <a href="CONTRIBUTING.md">Contribute</a> ·
  <a href="#setup-support">Setup support</a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue" alt="License: AGPL-3.0"></a>
  <a href="https://github.com/PouryaFA81/Nobat/actions/workflows/ci.yml"><img src="https://github.com/PouryaFA81/Nobat/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

---

## What it does

Nobat (نوبت, "appointment") is built for a small group, for example a few counselors or doctors, where **one coordinator books all the appointments** by phone or in person.

- **The coordinator** logs in, sees a Jalali month calendar of everyone's appointments, and books, moves or cancels them.
  Each appointment has the client's initials, date, time, length, the staff member, and an optional private note.
- **Each staff member** logs in and sees **only their own** upcoming appointments, including the notes.
- **Phone notifications** reach the staff member when an appointment is booked, moved or cancelled,
  and each evening they get a list of tomorrow's sessions.
- **Installable on phones** like an app (PWA): add it to the home screen from the browser.

<p align="center">
  <img src="docs/screenshots/calendar.png" width="260" alt="Coordinator: month calendar">
  <img src="docs/screenshots/day.png" width="260" alt="Coordinator: appointments of one day">
  <img src="docs/screenshots/my-schedule.png" width="260" alt="Staff member: own schedule">
</p>

## Privacy by design

Nobat is meant for sensitive settings, so it keeps things minimal:

- **Fully self-hosted.** No cloud services, no analytics, no AI. Notifications go through your own [ntfy](https://ntfy.sh) server.
- **Minimal data.** Only client initials, appointment time, and an optional note. No phone numbers or full names are required.
- **Notifications carry no notes.** Only initials and time, because they appear on lock screens.
- **Each staff member sees only their own appointments.**
- **One SQLite file** holds everything, which makes backups and moving servers simple.
- Hardened defaults: hashed passwords (scrypt), CSRF protection, strict Content-Security-Policy, login rate limiting,
  and a service worker that never stores appointment pages on the phone.

## Quick start

You need a Linux server with Docker, a domain name (two subdomains), and a reverse proxy with HTTPS such as Caddy.

```bash
git clone https://github.com/PouryaFA81/Nobat.git nobat
cd nobat
cp .env.example .env        # then edit it
docker compose up -d --build
```

The full step-by-step guide, including notifications, the first account and backups, is in **[docs/INSTALL.md](docs/INSTALL.md)**.

## Configuration

All settings live in `.env`:

| Setting | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | *(required)* | Random secret for login cookies. Generate with `openssl rand -hex 32`. |
| `NTFY_TOKEN` | | Token the panel uses to send notifications. |
| `BASE_URL` | | Public address of the panel, e.g. `https://nobat.example.com`. |
| `NTFY_PUBLIC_URL` | | Public address of the notification server. |
| `TIMEZONE` | `Asia/Tehran` | Time zone for all dates and times. |
| `REMINDER_HOUR` | `20` | Hour when the "sessions tomorrow" reminder is sent. |
| `STAFF_LABEL` | `مشاور` | What the panel calls staff members, e.g. `پزشک` or `درمانگر`. |
| `STAFF_LABEL_PLURAL` | label + `ان` | Plural form, if the default isn't right. |
| `SOURCE_URL` | this repository | Source code link in the footer (see [License](#license)). |
| `COOKIE_SECURE` | `1` | Set `0` only for local testing without HTTPS. |

## Setup support

Don't have a server, or prefer not to set it up yourself? Installation and maintenance can be arranged as a paid service.

👉 **[Open a setup request](https://github.com/PouryaFA81/Nobat/issues/new?template=setup_request.yml)**. Describe what you need; don't post private contact details in public. The maintainer will reply in the issue to arrange a private conversation.

## Contributing

Contributions are welcome: bug reports, ideas, translations, documentation and code.
Please read **[CONTRIBUTING.md](CONTRIBUTING.md)** and our **[Code of Conduct](CODE_OF_CONDUCT.md)**.
For security issues, follow **[SECURITY.md](SECURITY.md)** instead of opening a public issue.

## Tech stack

Python ([Starlette](https://www.starlette.io/)) with server-rendered Jinja templates, SQLite, a few lines of vanilla JavaScript, and [ntfy](https://ntfy.sh) for push notifications, all in Docker Compose.
The Jalali calendar is implemented in pure Python (`app/jalali.py`) with no extra dependency.

## License

Nobat is free software under the **[GNU Affero General Public License v3.0](LICENSE)** (AGPL-3.0-or-later).

You may use, study, change and share it, including commercially. If you run a **modified** version for other people over a network,
you must offer them the source code of your version. The footer link (`SOURCE_URL`) is there for that.
Third-party components and their licenses are listed in [NOTICE.md](NOTICE.md).
