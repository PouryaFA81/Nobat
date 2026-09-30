# Security policy

Nobat stores appointment data for clinics and counseling practices, so security reports are taken seriously.

## Reporting a vulnerability

**Please don't open a public issue for security problems.**

Report it privately through GitHub instead:

1. Open the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Describe the problem, how to reproduce it, and what an attacker could do with it.

You'll get a reply as soon as possible. Once a fix is released, you'll be credited in the changelog, unless you prefer not to be.

<div dir="rtl">

**گزارش مشکل امنیتی:** لطفاً مشکلات امنیتی را در issue عمومی ننویسید. از زبانه‌ی **Security** مخزن،
گزینه‌ی **Report a vulnerability** را بزنید و مشکل را به‌صورت خصوصی گزارش دهید.

</div>

## Supported versions

Only the latest release gets security fixes. Update with `git pull && docker compose up -d --build`.

## Advice for people running Nobat

- Always use HTTPS. The login cookie is only sent over HTTPS unless you set `COOKIE_SECURE=0`.
- Use a long random `SECRET_KEY` and keep `.env` private.
- Give staff members strong passwords, and deactivate or delete accounts that are no longer used.
- Back up `data/` regularly and keep the backups somewhere private.
- Keep the server, Docker and Nobat up to date.
