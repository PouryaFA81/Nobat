# Contributing to Nobat

Thank you for helping! Every kind of contribution is welcome: bug reports, ideas, fixes, translations and documentation.
You can write in **English or Persian**.

<div dir="rtl">

**خلاصه‌ی فارسی:** از هر نوع مشارکتی استقبال می‌کنیم و می‌توانید فارسی یا انگلیسی بنویسید.
برای گزارش خطا یا پیشنهاد، یک [issue](../../issues/new/choose) باز کنید. برای تغییر کد، یک fork بسازید،
تغییرتان را در یک شاخه‌ی جدید انجام دهید، تست‌ها را اجرا کنید و یک pull request بفرستید.
هیچ‌وقت اطلاعات واقعی مراجعان را در issue، اسکرین‌شات یا داده‌ی آزمایشی قرار ندهید.

</div>

## Ground rules

- Be kind. This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
- **Never post real client data**, not in issues, screenshots, logs or test data. Use made-up initials.
- Report security problems privately, as described in [SECURITY.md](SECURITY.md).
- Keep it small. Nobat is deliberately simple and has few dependencies. For a larger feature, please open an issue
  to discuss it before writing code, so your time isn't wasted.

## Ways to help

- **Report a bug:** [open a bug report](../../issues/new?template=bug_report.yml).
- **Suggest a feature:** [open a feature request](../../issues/new?template=feature_request.yml).
- **Pick up work:** issues labeled `good first issue` or `help wanted` are good starting points.
- **Improve the docs:** typos, unclear steps, and better Persian or English wording all count.

## Development setup

You need Python 3.12 or newer. Docker isn't required for development.

```bash
git clone https://github.com/<your-username>/Nobat.git nobat
cd nobat
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a local account and start the panel:

```bash
export DB_PATH=./dev.db SECRET_KEY=$(openssl rand -hex 32) COOKIE_SECURE=0
python -m app.manage create-admin
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. Notifications fail quietly without an ntfy server, which is fine for most work.

## Running the tests

```bash
python -m unittest discover -s tests -t . -v
```

The tests use only the Python standard library, so there's nothing extra to install. Please add a test for any bug you fix or feature you add.

## Project layout

| Path | What's there |
|---|---|
| `app/main.py` | Routes, permissions, forms |
| `app/db.py` | SQLite schema, users, password hashing |
| `app/jalali.py` | Jalali calendar conversion and Persian formatting |
| `app/notify.py` | ntfy notifications and the evening reminder |
| `app/manage.py` | Command-line tools (create admin, reset password, backup) |
| `app/templates/` | HTML pages (Jinja2) |
| `app/static/` | CSS, the small JS file, service worker, icons, font |
| `tests/` | Automated tests |
| `docs/` | Installation guides and screenshots |

## Code style

- Python: follow PEP 8, keep functions short, and prefer the standard library over new dependencies.
- No inline `<script>` or `style=""` in templates, because the Content-Security-Policy blocks them. Put code in `app/static/`.
- Interface text is Persian. Where a staff member is named, use the `STAFF` / `STAFF_PL` template variables instead of a fixed word.
- If you change `style.css` or `app.js`, bump the `?v=` number in `base.html` and `sw.js` so phones load the new file.

## Sending a pull request

1. Fork the repository and create a branch: `git checkout -b fix-short-description`
2. Make your change, with tests.
3. Run the tests.
4. Push and open a pull request. The template will ask for a short description and a checklist.

The CI builds the Docker image and runs the tests on every pull request.

## License of contributions

Nobat is licensed under the AGPL-3.0-or-later. By submitting a contribution, you agree that it's licensed under the same terms.
