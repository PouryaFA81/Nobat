# Phase 3 — Clinic UX

## What changed

### 3.1 Print day sheet
- Print CSS (`@media print` in `style.css`): hides nav, footer, action buttons (`.no-print` / `.appt-actions`); clean appointment list for paper.
- **چاپ برگه روز** on day view (`/day/...`) and **چاپ** on staff **برنامه من** (`/me`).

### 3.2 CSV export (admin)
- Persian UI at `/export`; download at `/export.csv`.
- Jalali from/to date selects (Gregorian `from`/`to` ISO also accepted).
- Optional staff filter.
- UTF-8 **BOM** for Excel + Persian headers.
- Default columns: تاریخ، ساعت، همکار (label from `STAFF_LABEL`)، حروف اول، وضعیت، ثبت‌کننده.
- **Notes off by default** (privacy; same rule as ntfy). Optional checkbox for admin-only notes column.

### 3.3 Initials search + created_by
- `/search` — admin searches all appointments; staff only their own schedule.
- Day rows show **ثبت‌کننده** when `created_by` is set (already in schema; LEFT JOIN to `users`).

### 3.4 Wider year picker
- Booking and schedule Jalali year selects use today ± **5** years (`year_choices` / `YEAR_SPAN`).

## How to use

1. **Print:** open a day or «برنامه من», tap چاپ, use the browser print dialog.
2. **CSV:** admin → **خروجی CSV** → pick شمسی range → دانلود CSV.
3. **Search:** **جستجو** in nav → type initials (partial match).

## How to run

```bash
python -m app.manage migrate
python -m unittest discover -s tests -t . -v
```

## Rollback notes

- No new migrations. Print CSS, routes, and templates are additive.
- Removing Phase 3 code leaves existing data unchanged (`created_by` already existed).
