# Phase 1 — Booking correctness

## What changed

### 1.1 Working hours + blocked days
- Tables `working_hours` and `blocked_days` (migration **0002**).
- Clinic-wide default hours (`doctor_id = 0`), default **06:00–24:00** (same bookable starts as before: 06…23).
- Optional per-staff override; if unset, the clinic default applies.
- Blocked/holiday days refuse **new** bookings (clinic-wide or per staff). Existing appointments on those days still show in day/me views.
- Validation in `_parse_appt_form` (booking and edit paths).
- Admin UI: **ساعات کاری** (`/schedule`) — Persian, simple forms.

### 1.2 Appointment statuses
- Statuses: `active` | `arrived` | `no_show` | `completed` | `cancelled` (migration **0003** documents values; column stays TEXT).
- Day view (admin) and me view (staff, own appointments) can set status via POST `/appointments/{id}/status`.
- Cancel path unchanged (`/appointments/{id}/cancel` + notification).
- Overlap: only **`cancelled`** frees the slot; `active` / `arrived` / `no_show` / `completed` (and unknown values) still block rebooking.

## How to configure hours

1. Open **ساعات کاری** in the admin nav (or `/schedule`).
2. Set clinic start/end as `HH:MM` (use `24:00` for end-of-day).
3. Optionally pick a staff member and set a personal window, or check «استفاده از پیش‌فرض کلینیک».
4. Add blocked days with Jalali date, optional staff filter, and optional reason.

Until you change anything, behaviour matches the historical 6–23 hour picker.

## How to run

```bash
python -m app.manage migrate
python -m unittest discover -s tests -t . -v
```

## Rollback notes

- **0002 / 0003** are additive (`CREATE IF NOT EXISTS`, documentation `SELECT 1`). Rolling back app code leaves the new tables harmless; old code ignores them.
- To clear overrides: delete rows from `working_hours` where `doctor_id != 0`, and/or clear `blocked_days`.
- Status values other than `active`/`cancelled` display as tags; older builds that only understand those two still load rows (unknown statuses may look odd but data is intact).
