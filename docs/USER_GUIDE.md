# Nobat user guide

[فارسی](USER_GUIDE.fa.md)

This guide is for **everyday use** of Nobat — booking, viewing, and phone alerts.  
It assumes someone already set up the panel and gave you the website address and a login.  
For installing the server, see [INSTALL.md](INSTALL.md).

Menu names below match what you see on screen (the interface is in Persian).

---

## What Nobat is

Nobat is a private calendar for a small clinic or counseling practice.

- One person (or a few) **books appointments** for clients.
- Each colleague sees **only their own** schedule.
- Optional **phone notifications** when something is booked, moved, or cancelled.

You never need a client’s full name or phone number. The panel works with **initials** (for example `ع.م`) plus date, time, and an optional private note.

---

## Who does what

| Role | Typical person | What they can do |
|---|---|---|
| **مدیر نوبت‌دهی** (scheduling admin) | Practice manager | Everything: calendar, book/edit/cancel, colleagues, working hours, CSV export, activity log |
| **پذیرش** (reception) | Front desk | Calendar, book/edit/cancel, search — not user management or admin settings |
| **همکار / مشاور** (staff who take sessions) | Counselor or doctor | **برنامه من** (My schedule), phone alerts, search — not everyone else’s calendar |

Your login may combine roles (for example admin who also takes clients).

---

## Sign in, password, sign out

1. Open the Nobat address in your browser (phone or computer).
2. Enter the **username** and **password** you were given.
3. To change your password later: open your name in the top menu → **تغییر رمز**.
4. To sign out: your name → **خروج**.

If you forget your password, ask the person who runs the server — they can reset it for you.

---

## Look and feel (optional)

In the top bar:

- **تیره / روشن** — switch dark and light mode.
- **پالت** — choose a color theme (for example نارنجی یارو or سبزآبی).

Your choice is remembered in this browser.

---

## For reception / admins: the calendar

Open **تقویم**.

- You see a **Jalali (Persian) month**.
- An orange number on a day = how many **active** appointments that day has.
- Tap a day to open the **day list**.
- Use the arrows to change month, or **امروز** to jump to today.
- Optional filter: pick one colleague to see only their days.

<!-- screenshot: docs/screenshots/calendar.png -->

### Open a day

On the day page you can:

- See every appointment (time, initials, colleague, notes).
- Tap **+ نوبت جدید در این روز** to book.
- **چاپ برگه روز** — print the day’s sheet.
- **دانلود ICS** — download that day for another calendar app.
- Manage the **wait list** at the bottom (see below).

<!-- screenshot: docs/screenshots/day.png -->

---

## Book an appointment

Two ways:

- Top menu → **+ نوبت**, or  
- From a day → **+ نوبت جدید در این روز**

Then fill in:

1. **Colleague** (مشاور / پزشک — whatever your practice calls them).
2. **Client initials** (not the full name).
3. **Date** (day / month / year).
4. **Time** and **length** (minutes).
5. Optional **weekly repeat** (same time each week; if any week conflicts, none are saved).
6. Optional **note** — only you and that colleague see it inside Nobat. It is **never** sent in a phone notification.

Tap **ذخیره** (Save).

---

## Edit, move, or cancel

On the day list, open **ویرایش / جابه‌جایی** on an appointment.

- Change colleague, initials, date, time, length, or note, then save.
- **لغو** cancels the appointment. The colleague is notified.
- If it is part of a **weekly series**, you can cancel **only this one** or the **whole series**.

### Status buttons (day of the session)

You (or the colleague on **برنامه من**) can mark:

- Arrived  
- No-show  
- Completed  
- Or back to active  

Cancelled appointments can be reactivated with **فعال‌سازی دوباره** if needed.

---

## Wait list

If a day or colleague is full, add the client to **فهرست انتظار این روز** on that day’s page.

Enter colleague, initials, optional preferred time, length, and note.

If an active appointment is cancelled and a free slot matches, the next person on the wait list for that colleague and day can be promoted automatically.

---

## Search

Open **جستجو** to find appointments by initials or other details your practice uses — handy when a client calls back.

---

## For staff: My schedule

Open **برنامه من**.

- See your **upcoming** sessions (initials, time, notes).
- Switch to **نوبت‌های گذشته** for the last 30 days.
- **چاپ** to print, or **دانلود تقویم (ICS)** to add upcoming sessions to your phone calendar.
- Mark arrived / no-show / completed from this list.

You do **not** see other colleagues’ appointments.

<!-- screenshot: docs/screenshots/my-schedule.png -->

---

## Phone notifications

Anyone who **takes appointments** should set this up once.

1. Open your name in the top menu → **تنظیم اعلان‌ها**.
2. Install the **ntfy** app (Android or iPhone).
3. Follow the steps on that page: paste your personal **Topic**, turn on **Use another server**, paste the server address, then **Subscribe**.
4. Tap **ارسال اعلان آزمایشی** to test.

You get alerts when:

- A session is booked for you  
- A session is moved or cancelled  
- The evening before, a list of tomorrow’s sessions  

Notifications show **initials and time only** — never the private note.  
Do not share your Topic with anyone else.

If your account does not take appointments, Nobat will not send you alerts.

---

## Put Nobat on your phone home screen

Treat it like an app:

- **Android (Chrome):** menu ⋮ → Add to Home screen / Install app  
- **iPhone (Safari):** Share → Add to Home Screen  

---

## For admins only (short)

### Colleagues — **همکاران**

- **+ همکار جدید** — display name, username, password.  
- Tick whether they **take appointments**, are **reception**, and/or **scheduling admin**.  
- To stop someone logging in: edit them, untick **حساب فعال است**, save. Their past appointments stay.

### Working hours — **ساعات کاری**

- Clinic open hours, optional hours per colleague, and closed days (holiday / leave).  
- Closed days **warn** you; they do not hard-block booking.

### CSV export — **خروجی CSV**

Download appointment data for records or spreadsheets.

### Activity log — **گزارش فعالیت**

See who changed what (useful if two people book at the desk).

---

## Quick tips

- Prefer **initials**, not full names, in the panel.  
- Put sensitive detail in the **note** field, not in anything a lock screen might show.  
- If the phone looks “stuck” on an old design after an update, fully close Nobat and open it again.  
- Need the server installed or repaired? That is a separate job — see [INSTALL.md](INSTALL.md) or ask your maintainer.

---

*Questions about a button you see on screen? Tell your coordinator which page you are on and what you wanted to do — most tasks are book, move, cancel, or check My schedule.*
