# Phase 4 — Later features

## What changed

### 4.1 ICS download
- Staff: **دانلود تقویم (ICS)** on `/me` → `/me.ics` (upcoming appointments).
- Coordinators (admin/receptionist): **دانلود ICS** on day view → `/day/{jdate}/ics`.
- Privacy: `SUMMARY` = initials only; `DESCRIPTION` = generic «نوبت». Private notes are never included.

### 4.2 Receptionist role
- Migration `0005`: `users.is_receptionist`.
- New role distinct from admin/doctor: can use calendar and CRUD appointments (book/edit/cancel/status/search).
- Cannot access: همکاران (`/users`), ساعات کاری (`/schedule`), خروجی CSV, گزارش فعالیت (`/audit`).
- Cannot hard-delete users (still CLI `delete-user --confirm YES` only; soft-deactivate is admin UI).

### 4.3 Recurring weekly series
- Migration `0006`: `appointments.series_id`.
- On **نوبت جدید**, optional **تکرار هفتگی** (1–26). Same slot every week under one `series_id`.
- Any overlap or working-hours conflict refuses the **entire** series (nothing inserted).
- Cancel: **فقط این نوبت** vs **کل سری هفتگی**.
- Blocked/holiday days remain soft-warn only (do not hard-block).
- Edit still applies to a single occurrence (series-wide edit deferred).

### 4.4 Waitlist + auto-promote
- Migration `0007`: `waitlist` table (soft queue per staff + day).
- Day view: add/remove waiting clients; optional preferred time; private note (not in ICS/ntfy).
- **Auto-promote (documented):** when an **active** appointment is cancelled (scope=one), the oldest waiting entry for the same `doctor_id` + `day` is booked if preferred time (or the freed slot) fits hours and has no overlap. Series cancel does not auto-promote. Flash message names the promoted initials.

## How to use

1. **ICS:** برنامه من → دانلود تقویم؛ or day sheet → دانلود ICS; import into a calendar app.
2. **Receptionist:** admin → همکاران → tick «پذیرش» (without admin). They land on the calendar.
3. **Series:** نوبت جدید → تکرار هفتگی → N هفته.
4. **Waitlist:** open a day → فهرست انتظار → add; cancel an appointment to auto-promote.

## How to run

```bash
python -m app.manage migrate
python -m unittest discover -s tests -t . -v
```

## Rollback notes

- Migrations `0005`–`0007` are additive (`is_receptionist`, `series_id`, `waitlist`).
- Removing Phase 4 code leaves columns/tables in place; safe to ignore.
