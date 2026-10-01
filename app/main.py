"""Nobat — a small, private, self-hosted appointment panel.

Copyright (C) 2026 Nobat contributors
SPDX-License-Identifier: AGPL-3.0-or-later

One coordinator (admin) books appointments for the staff (counselors,
doctors, ...). Each staff member logs in to see only their own schedule and
gets ntfy notifications: on booking, on change/cancel, and the evening before.
"""
import asyncio
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from . import __version__, audit, db, export_csv, jalali, notify, schedule
from .jalali import fa

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("nobat")

HERE = Path(__file__).parent
SECRET_KEY = os.environ.get("SECRET_KEY", "")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") == "1"
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
NTFY_PUBLIC_URL = os.environ.get("NTFY_PUBLIC_URL", "").rstrip("/")
# What the panel calls the people who receive appointments (e.g. مشاور, پزشک, درمانگر).
STAFF_LABEL = os.environ.get("STAFF_LABEL", "مشاور").strip() or "مشاور"
STAFF_LABEL_PLURAL = os.environ.get("STAFF_LABEL_PLURAL", "").strip() or STAFF_LABEL + "ان"
# AGPL-3.0 section 13: users of the panel must be able to get its source code.
# If you run a modified version, point this at your modified source.
SOURCE_URL = os.environ.get("SOURCE_URL", "https://github.com/PouryaFA81/Nobat").strip()

if len(SECRET_KEY) < 32:
    raise SystemExit("SECRET_KEY must be set (at least 32 characters). See README.")

templates = Jinja2Templates(directory=str(HERE / "templates"))
templates.env.filters["fa"] = fa
templates.env.filters["long_date"] = lambda s: jalali.long_date(date.fromisoformat(s))
templates.env.filters["jstr"] = lambda s: jalali.jstr(date.fromisoformat(s))
templates.env.filters["status_label"] = schedule.status_label
templates.env.filters["action_label"] = audit.action_label
templates.env.globals.update(MONTHS=jalali.MONTHS, STAFF=STAFF_LABEL, STAFF_PL=STAFF_LABEL_PLURAL,
                             SOURCE_URL=SOURCE_URL, VERSION=__version__,
                             STATUS_LABELS=schedule.STATUS_LABELS,
                             SLOT_BLOCKING=sorted(schedule.SLOT_BLOCKING))

DURATIONS = [15, 30, 45, 60, 75, 90, 120]
HOURS = list(range(6, 24))
MINUTES = list(range(0, 60, 5))
YEAR_SPAN = 5  # Jalali year select: today ± YEAR_SPAN


def year_choices(center: date | None = None) -> list[int]:
    """Wider year picker for booking / schedule forms (±YEAR_SPAN around today)."""
    d = center or today()
    ty = jalali.to_jalali(d)[0]
    return list(range(ty - YEAR_SPAN, ty + YEAR_SPAN + 1))



# ---------------------------------------------------------------- helpers
def today() -> date:
    return notify.now_local().date()


def current_user(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return None
    with db.db() as c:
        u = c.execute("SELECT * FROM users WHERE id = ? AND active = 1", (uid,)).fetchone()
    # Changing or resetting a password logs out every other session of that user.
    if not u or request.session.get("pv") != u["password_hash"][-12:]:
        request.session.clear()
        return None
    return u


def csrf_token(request: Request) -> str:
    tok = request.session.get("csrf")
    if not tok:
        tok = secrets.token_urlsafe(24)
        request.session["csrf"] = tok
    return tok


async def form_checked(request: Request):
    form = await request.form()
    if not secrets.compare_digest(str(form.get("csrf", "")), request.session.get("csrf", "-")):
        raise PermissionError("csrf")
    return form


def render(request: Request, name: str, user=None, status_code=200, **ctx):
    ctx.update(user=user, csrf=csrf_token(request), today=today().isoformat(),
               flash=request.session.pop("flash", None))
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def redirect(url: str, flash: str | None = None, request: Request | None = None):
    if flash and request is not None:
        request.session["flash"] = flash
    return RedirectResponse(url, status_code=303)


def login_required(admin=False):
    def deco(fn):
        async def wrapper(request: Request):
            user = current_user(request)
            if not user:
                return RedirectResponse("/login", status_code=303)
            if admin and not user["is_admin"]:
                return PlainTextResponse("دسترسی ندارید", status_code=403)
            try:
                return await fn(request, user)
            except PermissionError:
                return PlainTextResponse("فرم منقضی شده است. صفحه را دوباره باز کنید.", status_code=400)
        return wrapper
    return deco


def doctors(c, include_inactive=False):
    q = "SELECT * FROM users WHERE is_doctor = 1" + ("" if include_inactive else " AND active = 1")
    return c.execute(q + " ORDER BY name").fetchall()


def appt_with_topic(c, appt_id):
    row = c.execute(
        "SELECT a.*, u.ntfy_topic, u.name AS doctor_name FROM appointments a "
        "JOIN users u ON u.id = a.doctor_id WHERE a.id = ?", (appt_id,)).fetchone()
    return dict(row) if row else None


def to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def reminder_flag(day: date) -> int:
    """If the evening reminder for this day has already gone out, don't send
    another one; the booking notification itself is enough."""
    now = notify.now_local()
    if day <= now.date():
        return 1
    if day == now.date() + timedelta(days=1) and now.hour >= notify.REMINDER_HOUR:
        return 1
    return 0


# ---------------------------------------------------------------- login
_failures: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


async def login(request: Request):
    if request.method == "GET":
        if current_user(request):
            return redirect("/")
        return render(request, "login.html")
    ip = _client_ip(request)
    recent = [t for t in _failures.get(ip, []) if t > time.time() - 900]
    _failures[ip] = recent
    if len(recent) >= 5:
        return render(request, "login.html", error="تلاش‌های ناموفق زیاد بود. ۱۵ دقیقه بعد دوباره امتحان کنید.",
                      status_code=429)
    try:
        form = await form_checked(request)
    except PermissionError:
        return render(request, "login.html", error="صفحه منقضی شده بود. دوباره وارد شوید.")
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    with db.db() as c:
        u = c.execute("SELECT * FROM users WHERE username = ? AND active = 1", (username,)).fetchone()
    if not u or not db.check_password(password, u["password_hash"]):
        recent.append(time.time())
        return render(request, "login.html", error="نام کاربری یا رمز عبور اشتباه است.", status_code=401)
    _failures.pop(ip, None)
    request.session.clear()
    request.session.update(uid=u["id"], pv=u["password_hash"][-12:], csrf=secrets.token_urlsafe(24))
    return redirect("/")


async def logout(request: Request):
    try:
        await form_checked(request)
    except PermissionError:
        pass
    request.session.clear()
    return redirect("/login")


async def home(request: Request):
    user = current_user(request)
    if not user:
        return redirect("/login")
    return redirect("/calendar" if user["is_admin"] else "/me")


# ---------------------------------------------------------------- staff member view
@login_required()
async def my_schedule(request: Request, user):
    past = request.query_params.get("past") == "1"
    t = today()
    with db.db() as c:
        if past:
            rows = c.execute(
                "SELECT * FROM appointments WHERE doctor_id = ? AND day >= ? AND day < ? "
                "ORDER BY day DESC, start_time", (user["id"], (t - timedelta(days=30)).isoformat(), t.isoformat())).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM appointments WHERE doctor_id = ? AND day >= ? "
                "ORDER BY day, start_time", (user["id"], t.isoformat())).fetchall()
    groups: list[tuple[str, list]] = []
    for r in rows:
        if not groups or groups[-1][0] != r["day"]:
            groups.append((r["day"], []))
        groups[-1][1].append(r)
    tomorrow = (t + timedelta(days=1)).isoformat()
    return render(request, "me.html", user, groups=groups, past=past, tomorrow=tomorrow)


# ---------------------------------------------------------------- coordinator: calendar
@login_required(admin=True)
async def calendar(request: Request, user):
    t = today()
    ty, tm, _ = jalali.to_jalali(t)
    try:
        jy, jm = (int(x) for x in jalali.en_digits(request.query_params.get("m", "")).split("-"))
        assert 1 <= jm <= 12 and 1300 < jy < 1500
    except Exception:
        jy, jm = ty, tm
    doctor_id = request.query_params.get("doctor", "")
    first = jalali.to_gregorian(jy, jm, 1)
    n = jalali.month_length(jy, jm)
    last = first + timedelta(days=n - 1)
    q = ("SELECT day, COUNT(*) AS n FROM appointments WHERE status != 'cancelled' AND day BETWEEN ? AND ?")
    args = [first.isoformat(), last.isoformat()]
    if doctor_id.isdigit():
        q += " AND doctor_id = ?"
        args.append(int(doctor_id))
    with db.db() as c:
        counts = {r["day"]: r["n"] for r in c.execute(q + " GROUP BY day", args)}
        docs = doctors(c)
    lead = (first.weekday() + 2) % 7  # Saturday-first week
    cells = [None] * lead
    for i in range(n):
        d = first + timedelta(days=i)
        cells.append({"jd": i + 1, "iso": d.isoformat(), "j": jalali.jstr(d),
                      "count": counts.get(d.isoformat(), 0), "today": d == t,
                      "friday": d.weekday() == 4})
    while len(cells) % 7:
        cells.append(None)
    prev_m = f"{jy - 1}-12" if jm == 1 else f"{jy}-{jm - 1:02d}"
    next_m = f"{jy + 1}-01" if jm == 12 else f"{jy}-{jm + 1:02d}"
    return render(request, "calendar.html", user, jy=jy, jm=jm, cells=cells,
                  weeks=[cells[i:i + 7] for i in range(0, len(cells), 7)],
                  header=jalali.WEEK_HEADER, prev_m=prev_m, next_m=next_m,
                  this_m=f"{ty}-{tm:02d}", docs=docs, doctor_id=doctor_id)


@login_required(admin=True)
async def day_view(request: Request, user):
    try:
        d = jalali.parse_jstr(request.path_params["jdate"])
    except Exception:
        return redirect("/calendar")
    doctor_id = request.query_params.get("doctor", "")
    q = ("SELECT a.*, u.name AS doctor_name, cu.name AS created_by_name "
         "FROM appointments a JOIN users u ON u.id = a.doctor_id "
         "LEFT JOIN users cu ON cu.id = a.created_by "
         "WHERE a.day = ?")
    args: list = [d.isoformat()]
    if doctor_id.isdigit():
        q += " AND a.doctor_id = ?"
        args.append(int(doctor_id))
    with db.db() as c:
        rows = c.execute(q + " ORDER BY a.status, a.start_time", args).fetchall()
        docs = doctors(c)
    return render(request, "day.html", user, d=d.isoformat(), j=jalali.jstr(d), rows=rows,
                  prev=jalali.jstr(d - timedelta(days=1)), next=jalali.jstr(d + timedelta(days=1)),
                  docs=docs, doctor_id=doctor_id)


# ---------------------------------------------------------------- coordinator: appointment form
def _parse_appt_form(form, c, exclude_id=None):
    """Returns (values, error)."""
    v = {k: jalali.en_digits(str(form.get(k, ""))).strip()
         for k in ("doctor_id", "initials", "jy", "jm", "jd", "hour", "minute", "duration", "description")}
    v["description"] = str(form.get("description", "")).strip()[:1000]
    v["initials"] = str(form.get("initials", "")).strip()[:30]
    if not v["initials"]:
        return v, "حروف اول نام مراجع را وارد کنید."
    try:
        doctor_id = int(v["doctor_id"])
        jy, jm, jd = int(v["jy"]), int(v["jm"]), int(v["jd"])
        hour, minute, duration = int(v["hour"]), int(v["minute"]), int(v["duration"])
    except ValueError:
        return v, "همه‌ی فیلدها را کامل کنید."
    doc = c.execute("SELECT * FROM users WHERE id = ? AND is_doctor = 1 AND active = 1", (doctor_id,)).fetchone()
    if not doc:
        return v, f"{STAFF_LABEL} را انتخاب کنید."
    if not jalali.valid(jy, jm, jd):
        return v, f"{jalali.MONTHS[jm - 1] if 1 <= jm <= 12 else 'این ماه'} {fa(jy)} روز {fa(jd)} ندارد."
    if not (0 <= hour < 24 and 0 <= minute < 60 and 5 <= duration <= 480):
        return v, "ساعت یا مدت جلسه نامعتبر است."
    day = jalali.to_gregorian(jy, jm, jd)
    start = f"{hour:02d}:{minute:02d}"
    day_iso = day.isoformat()

    # Blocked/holiday days are informational only — clinics may still book.
    blocked, reason = schedule.is_blocked(c, day_iso, doctor_id)
    if blocked:
        extra = f" ({reason})" if reason else ""
        v["_blocked_warning"] = (
            f"توجه: این روز به‌عنوان روز بسته/تعطیل علامت خورده است{extra}."
        )

    open_t, close_t = schedule.get_hours(c, doctor_id)
    hours_err = schedule.validate_within_hours(start, duration, open_t, close_t)
    if hours_err:
        return v, hours_err

    s, e = to_min(start), to_min(start) + duration
    # Cancelled frees the slot; every other status (incl. unknown) still occupies it.
    others = c.execute(
        "SELECT id, initials, start_time, duration_min, status FROM appointments "
        "WHERE doctor_id = ? AND day = ? AND status != 'cancelled' AND id != ?",
        (doctor_id, day_iso, exclude_id or 0)).fetchall()
    for o in others:
        os_, oe = to_min(o["start_time"]), to_min(o["start_time"]) + o["duration_min"]
        if s < oe and os_ < e:
            return v, (f"تداخل: {doc['name']} در این زمان نوبت دیگری دارد "
                       f"({o['initials']}، ساعت {fa(o['start_time'])}).")
    v.update(doctor_id=doctor_id, day=day_iso, start_time=start, duration=duration, _day=day)
    return v, None


def _form_ctx(c, v, title, action, appt=None):
    t = today()
    ty = jalali.to_jalali(t)[0]
    return dict(v=v, title=title, action=action, appt=appt, docs=doctors(c),
                years=year_choices(t), hours=HOURS, minutes=MINUTES, durations=DURATIONS)


@login_required(admin=True)
async def appt_new(request: Request, user):
    with db.db() as c:
        if request.method == "GET":
            try:
                d = jalali.parse_jstr(request.query_params.get("day", ""))
            except Exception:
                d = today()
            jy, jm, jd = jalali.to_jalali(d)
            v = dict(doctor_id=request.query_params.get("doctor", ""), initials="", jy=jy, jm=jm, jd=jd,
                     hour=16, minute=0, duration=60, description="")
            return render(request, "appt_form.html", user, **_form_ctx(c, v, "نوبت جدید", "/appointments/new"))
        form = await form_checked(request)
        v, err = _parse_appt_form(form, c)
        if err:
            return render(request, "appt_form.html", user, error=err, status_code=400,
                          **_form_ctx(c, v, "نوبت جدید", "/appointments/new"))
        cur = c.execute(
            "INSERT INTO appointments (doctor_id, initials, day, start_time, duration_min, description, "
            "reminder_sent, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (v["doctor_id"], v["initials"], v["day"], v["start_time"], v["duration"], v["description"],
             reminder_flag(v["_day"]), user["id"]))
        appt_id = cur.lastrowid
        audit.record(user, audit.BOOK, appointment_id=appt_id, conn=c,
                     detail={"day": v["day"], "start": v["start_time"], "doctor_id": v["doctor_id"],
                             "initials": v["initials"]})
        c.commit()
        appt = appt_with_topic(c, appt_id)
    flash = f"نوبت ثبت شد و به {STAFF_LABEL} اطلاع داده شد."
    if v.get("_blocked_warning"):
        flash = f"{flash} {v['_blocked_warning']}"
    request.session["flash"] = flash
    return RedirectResponse(f"/day/{jalali.jstr(v['_day'])}", status_code=303,
                            background=BackgroundTask(notify.appointment_event, "new", appt))


@login_required(admin=True)
async def appt_edit(request: Request, user):
    appt_id = request.path_params["id"]
    with db.db() as c:
        old = appt_with_topic(c, appt_id)
        if not old:
            return redirect("/calendar")
        action = f"/appointments/{appt_id}/edit"
        if request.method == "GET":
            jy, jm, jd = jalali.to_jalali(date.fromisoformat(old["day"]))
            h, m = old["start_time"].split(":")
            v = dict(doctor_id=old["doctor_id"], initials=old["initials"], jy=jy, jm=jm, jd=jd,
                     hour=int(h), minute=int(m), duration=old["duration_min"], description=old["description"])
            return render(request, "appt_form.html", user, **_form_ctx(c, v, "ویرایش نوبت", action, old))
        form = await form_checked(request)
        v, err = _parse_appt_form(form, c, exclude_id=old["id"])
        if err:
            return render(request, "appt_form.html", user, error=err, status_code=400,
                          **_form_ctx(c, v, "ویرایش نوبت", action, old))
        moved = (v["day"], v["start_time"]) != (old["day"], old["start_time"])
        reassigned = v["doctor_id"] != old["doctor_id"]
        reminder = reminder_flag(v["_day"]) if (moved or reassigned) else old["reminder_sent"]
        c.execute(
            "UPDATE appointments SET doctor_id = ?, initials = ?, day = ?, start_time = ?, duration_min = ?, "
            "description = ?, status = 'active', reminder_sent = ?, updated_at = datetime('now') WHERE id = ?",
            (v["doctor_id"], v["initials"], v["day"], v["start_time"], v["duration"], v["description"],
             reminder, old["id"]))
        if old["status"] == "cancelled":
            audit.record(user, audit.RESTORE, appointment_id=old["id"], conn=c,
                         detail={"day": v["day"], "start": v["start_time"], "doctor_id": v["doctor_id"]})
        if reassigned:
            audit.record(user, audit.REASSIGN, appointment_id=old["id"], conn=c,
                         detail={"from_doctor": old["doctor_id"], "to_doctor": v["doctor_id"],
                                 "day": v["day"], "start": v["start_time"]})
        elif moved:
            audit.record(user, audit.MOVE, appointment_id=old["id"], conn=c,
                         detail={"from": f"{old['day']} {old['start_time']}",
                                 "to": f"{v['day']} {v['start_time']}"})
        c.commit()
        new = appt_with_topic(c, old["id"])

    async def notify_changes():
        if old["status"] == "cancelled" or reassigned:
            if reassigned and old["status"] != "cancelled":
                await notify.appointment_event("reassigned_away", new, old)
            await notify.appointment_event("new", new)
        elif moved:
            await notify.appointment_event("moved", new, old)

    flash = "تغییرات ذخیره شد." + (f" به {STAFF_LABEL} اطلاع داده شد." if (moved or reassigned) else "")
    if v.get("_blocked_warning"):
        flash = f"{flash} {v['_blocked_warning']}"
    request.session["flash"] = flash
    return RedirectResponse(f"/day/{jalali.jstr(v['_day'])}", status_code=303,
                            background=BackgroundTask(notify_changes))


@login_required(admin=True)
async def appt_cancel(request: Request, user):
    await form_checked(request)
    with db.db() as c:
        appt = appt_with_topic(c, request.path_params["id"])
        if not appt or appt["status"] == "cancelled":
            return redirect("/calendar")
        c.execute("UPDATE appointments SET status = 'cancelled', updated_at = datetime('now') WHERE id = ?",
                  (appt["id"],))
        audit.record(user, audit.CANCEL, appointment_id=appt["id"], conn=c,
                     detail={"day": appt["day"], "start": appt["start_time"], "doctor_id": appt["doctor_id"]})
    request.session["flash"] = f"نوبت لغو شد و به {STAFF_LABEL} اطلاع داده شد."
    return RedirectResponse(f"/day/{jalali.jstr(date.fromisoformat(appt['day']))}", status_code=303,
                            background=BackgroundTask(notify.appointment_event, "cancelled", appt))


# ---------------------------------------------------------------- status updates
@login_required()
async def appt_set_status(request: Request, user):
    """Set appointment status (admin any; staff only own, non-cancel). Cancel stays on /cancel."""
    form = await form_checked(request)
    new_status = str(form.get("status", "")).strip()
    if new_status not in schedule.STATUSES or new_status == "cancelled":
        return PlainTextResponse("وضعیت نامعتبر است.", status_code=400)
    appt_id = request.path_params["id"]
    with db.db() as c:
        appt = c.execute("SELECT * FROM appointments WHERE id = ?", (appt_id,)).fetchone()
        if not appt:
            return redirect("/calendar" if user["is_admin"] else "/me")
        if not user["is_admin"] and appt["doctor_id"] != user["id"]:
            return PlainTextResponse("دسترسی ندارید", status_code=403)
        if appt["status"] == "cancelled" and not user["is_admin"]:
            return PlainTextResponse("نوبت لغو شده را نمی‌توانید تغییر دهید.", status_code=400)
        c.execute(
            "UPDATE appointments SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (new_status, appt_id))
        audit.record(user, audit.STATUS_CHANGE, appointment_id=appt_id, conn=c,
                     detail={"from": appt["status"], "to": new_status})
    label = schedule.status_label(new_status)
    request.session["flash"] = f"وضعیت نوبت: {label}"
    if user["is_admin"]:
        return redirect(f"/day/{jalali.jstr(date.fromisoformat(appt['day']))}", request=request)
    past = request.query_params.get("past") == "1"
    return redirect("/me?past=1" if past else "/me", request=request)


# ---------------------------------------------------------------- working hours & blocked days
@login_required(admin=True)
async def schedule_settings(request: Request, user):
    with db.db() as c:
        schedule.ensure_clinic_hours(c)
        if request.method == "POST":
            form = await form_checked(request)
            action = str(form.get("action", "")).strip()
            err = None
            if action == "clinic_hours":
                start = jalali.en_digits(str(form.get("start_time", ""))).strip()
                end = jalali.en_digits(str(form.get("end_time", ""))).strip()
                if schedule.parse_hhmm(start) is None or schedule.parse_hhmm(end) is None:
                    err = "ساعت را به صورت HH:MM وارد کنید (مثلاً ۰۸:۰۰)."
                elif schedule.parse_hhmm(start) >= schedule.parse_hhmm(end):
                    err = "ساعت پایان باید بعد از ساعت شروع باشد."
                else:
                    schedule.set_hours(c, schedule.CLINIC, start, end)
                    audit.record(user, audit.SCHEDULE_HOURS, conn=c,
                                 detail={"scope": "clinic", "start": start, "end": end})
                    request.session["flash"] = "ساعت کاری کلینیک ذخیره شد."
            elif action == "staff_hours":
                try:
                    doctor_id = int(form.get("doctor_id", "0"))
                except ValueError:
                    doctor_id = 0
                doc = c.execute(
                    "SELECT id FROM users WHERE id = ? AND is_doctor = 1", (doctor_id,)
                ).fetchone()
                if not doc:
                    err = f"{STAFF_LABEL} را انتخاب کنید."
                elif form.get("use_default") == "1":
                    schedule.clear_staff_hours(c, doctor_id)
                    audit.record(user, audit.SCHEDULE_HOURS, conn=c,
                                 detail={"scope": "staff", "doctor_id": doctor_id, "cleared": True})
                    request.session["flash"] = "بازهٔ اختصاصی برداشته شد؛ از پیش‌فرض کلینیک استفاده می‌شود."
                else:
                    start = jalali.en_digits(str(form.get("start_time", ""))).strip()
                    end = jalali.en_digits(str(form.get("end_time", ""))).strip()
                    if schedule.parse_hhmm(start) is None or schedule.parse_hhmm(end) is None:
                        err = "ساعت را به صورت HH:MM وارد کنید."
                    elif schedule.parse_hhmm(start) >= schedule.parse_hhmm(end):
                        err = "ساعت پایان باید بعد از ساعت شروع باشد."
                    else:
                        schedule.set_hours(c, doctor_id, start, end)
                        audit.record(user, audit.SCHEDULE_HOURS, conn=c,
                                     detail={"scope": "staff", "doctor_id": doctor_id,
                                             "start": start, "end": end})
                        request.session["flash"] = "ساعت کاری همکار ذخیره شد."
            elif action == "add_blocked":
                try:
                    jy, jm, jd = (int(jalali.en_digits(str(form.get(k, "")))) for k in ("jy", "jm", "jd"))
                    doctor_id = int(form.get("doctor_id") or "0")
                except ValueError:
                    err = "تاریخ را کامل کنید."
                    jy = jm = jd = doctor_id = 0
                reason = str(form.get("reason", "")).strip()[:200]
                if not err and not jalali.valid(jy, jm, jd):
                    err = "تاریخ نامعتبر است."
                elif not err and doctor_id != 0:
                    doc = c.execute(
                        "SELECT id FROM users WHERE id = ? AND is_doctor = 1", (doctor_id,)
                    ).fetchone()
                    if not doc:
                        err = f"{STAFF_LABEL} نامعتبر است."
                if not err:
                    day = jalali.to_gregorian(jy, jm, jd).isoformat()
                    schedule.add_blocked(c, day, doctor_id, reason)
                    audit.record(user, audit.SCHEDULE_BLOCK, conn=c,
                                 detail={"op": "add", "day": day, "doctor_id": doctor_id})
                    request.session["flash"] = "روز بسته ثبت شد. نوبت‌دهی در این روز همچنان ممکن است؛ هنگام ثبت هشدار نشان داده می‌شود."
            elif action == "remove_blocked":
                try:
                    bid = int(form.get("blocked_id", "0"))
                except ValueError:
                    bid = 0
                schedule.remove_blocked(c, bid)
                audit.record(user, audit.SCHEDULE_BLOCK, conn=c,
                             detail={"op": "remove", "blocked_id": bid})
                request.session["flash"] = "روز بسته حذف شد."
            else:
                err = "درخواست نامعتبر است."
            if err:
                clinic = schedule.get_hours(c, schedule.CLINIC)
                docs = doctors(c)
                staff_hours = {
                    r["doctor_id"]: (r["start_time"], r["end_time"])
                    for r in c.execute(
                        "SELECT doctor_id, start_time, end_time FROM working_hours WHERE doctor_id != 0"
                    )
                }
                blocked = schedule.list_blocked(c)
                t = today()
                ty = jalali.to_jalali(t)[0]
                return render(request, "schedule.html", user, error=err, status_code=400,
                              clinic_start=clinic[0], clinic_end=clinic[1],
                              docs=docs, staff_hours=staff_hours, blocked=blocked,
                              years=year_choices(t), jy=ty, jm=jalali.to_jalali(t)[1], jd=1)
            return redirect("/schedule", request=request)

        clinic = schedule.get_hours(c, schedule.CLINIC)
        docs = doctors(c)
        staff_hours = {
            r["doctor_id"]: (r["start_time"], r["end_time"])
            for r in c.execute(
                "SELECT doctor_id, start_time, end_time FROM working_hours WHERE doctor_id != 0"
            )
        }
        blocked = schedule.list_blocked(c)
        t = today()
        ty, tm, _ = jalali.to_jalali(t)
    return render(request, "schedule.html", user,
                  clinic_start=clinic[0], clinic_end=clinic[1],
                  docs=docs, staff_hours=staff_hours, blocked=blocked,
                  years=year_choices(t), jy=ty, jm=tm, jd=1)


# ---------------------------------------------------------------- coordinator: users
@login_required(admin=True)
async def users_list(request: Request, user):
    with db.db() as c:
        rows = c.execute("SELECT * FROM users ORDER BY active DESC, name").fetchall()
    return render(request, "users.html", user, rows=rows)


def _user_form_values(form):
    return dict(name=str(form.get("name", "")).strip()[:80],
                username=jalali.en_digits(str(form.get("username", ""))).strip().lower()[:40],
                password=str(form.get("password", "")),
                is_admin=form.get("is_admin") == "1", is_doctor=form.get("is_doctor") == "1",
                active=form.get("active") == "1")


@login_required(admin=True)
async def user_new(request: Request, user):
    if request.method == "GET":
        return render(request, "user_form.html", user, u=None,
                      v=dict(name="", username="", is_admin=False, is_doctor=True, active=True))
    v = _user_form_values(await form_checked(request))
    err = None
    if not v["name"] or not v["username"]:
        err = "نام و نام کاربری را وارد کنید."
    elif not v["username"].replace(".", "").replace("_", "").isalnum() or not v["username"].isascii():
        err = "نام کاربری فقط با حروف انگلیسی و عدد باشد."
    elif len(v["password"]) < 8:
        err = "رمز عبور حداقل ۸ کاراکتر باشد."
    if not err:
        with db.db() as c:
            if c.execute("SELECT 1 FROM users WHERE username = ?", (v["username"],)).fetchone():
                err = "این نام کاربری قبلاً استفاده شده است."
            else:
                uid = db.create_user(c, v["username"], v["name"], v["password"], v["is_admin"], v["is_doctor"])
    if err:
        return render(request, "user_form.html", user, u=None, v=v, error=err, status_code=400)
    return redirect(f"/users/{uid}/edit", "کاربر ساخته شد. اطلاعات ورود و اعلان را به او بدهید.", request)


@login_required(admin=True)
async def user_edit(request: Request, user):
    uid = int(request.path_params["id"])
    with db.db() as c:
        u = c.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if not u:
            return redirect("/users")
        if request.method == "GET":
            return render(request, "user_form.html", user, u=u, v=dict(u), ntfy_public=NTFY_PUBLIC_URL)
        v = _user_form_values(await form_checked(request))
        err = None
        if not v["name"]:
            err = "نام را وارد کنید."
        elif v["password"] and len(v["password"]) < 8:
            err = "رمز عبور حداقل ۸ کاراکتر باشد."
        elif uid == user["id"] and (not v["is_admin"] or not v["active"]):
            err = "نمی‌توانید دسترسی مدیر یا فعال بودن حساب خودتان را بردارید."
        if err:
            return render(request, "user_form.html", user, u=u, v=v, error=err,
                          ntfy_public=NTFY_PUBLIC_URL, status_code=400)
        was_active = bool(u["active"])
        c.execute("UPDATE users SET name = ?, is_admin = ?, is_doctor = ?, active = ? WHERE id = ?",
                  (v["name"], int(v["is_admin"]), int(v["is_doctor"]), int(v["active"]), uid))
        if v["password"]:
            c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (db.hash_password(v["password"]), uid))
        if was_active and not v["active"]:
            audit.record(user, audit.USER_DEACTIVATE, conn=c,
                         detail={"target_user_id": uid, "username": u["username"]})
        elif (not was_active) and v["active"]:
            audit.record(user, audit.USER_ACTIVATE, conn=c,
                         detail={"target_user_id": uid, "username": u["username"]})
    return redirect(f"/users/{uid}/edit", "ذخیره شد.", request)


@login_required(admin=True)
async def user_delete(request: Request, user):
    """Soft-delete: deactivate the colleague. Appointments are kept.
    Permanent removal is only available via: python -m app.manage delete-user."""
    await form_checked(request)
    uid = int(request.path_params["id"])
    if uid == user["id"]:
        return redirect(f"/users/{uid}/edit", "نمی‌توانید حساب خودتان را غیرفعال کنید.", request)
    with db.db() as c:
        u = c.execute("SELECT name, active FROM users WHERE id = ?", (uid,)).fetchone()
        if not u:
            return redirect("/users")
        if not u["active"]:
            return redirect("/users", f"{u['name']} از قبل غیرفعال است.", request)
        c.execute("UPDATE users SET active = 0 WHERE id = ?", (uid,))
        uname = c.execute("SELECT username FROM users WHERE id = ?", (uid,)).fetchone()
        audit.record(user, audit.USER_DEACTIVATE, conn=c,
                     detail={"target_user_id": uid,
                             "username": uname["username"] if uname else ""})
    return redirect("/users", f"{u['name']} غیرفعال شد. نوبت‌ها نگه داشته شدند.", request)


# ---------------------------------------------------------------- own account
@login_required()
async def change_password(request: Request, user):
    if request.method == "GET":
        return render(request, "password.html", user)
    form = await form_checked(request)
    old, new, new2 = (str(form.get(k, "")) for k in ("old", "new", "new2"))
    err = None
    if not db.check_password(old, user["password_hash"]):
        err = "رمز فعلی اشتباه است."
    elif len(new) < 8:
        err = "رمز جدید حداقل ۸ کاراکتر باشد."
    elif new != new2:
        err = "تکرار رمز جدید یکسان نیست."
    if err:
        return render(request, "password.html", user, error=err, status_code=400)
    h = db.hash_password(new)
    with db.db() as c:
        c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (h, user["id"]))
    request.session["pv"] = h[-12:]
    return redirect("/", "رمز عبور تغییر کرد.", request)


@login_required()
async def notif_help(request: Request, user):
    return render(request, "notif_help.html", user, topic=user["ntfy_topic"], ntfy_public=NTFY_PUBLIC_URL)


@login_required()
async def notif_test(request: Request, user):
    await form_checked(request)
    ok = await notify.send(user["ntfy_topic"], "آزمایش اعلان", "اعلان‌های پنل نوبت روی این گوشی کار می‌کند.", "white_check_mark")
    return redirect("/notifications", "اعلان آزمایشی فرستاده شد." if ok else "ارسال اعلان ناموفق بود. به مدیر پنل خبر دهید.", request)



# ---------------------------------------------------------------- CSV export (admin)
@login_required(admin=True)
async def export_form(request: Request, user):
    """Persian UI: Jalali date range → CSV download. Notes excluded by default."""
    t = today()
    ty, tm, td = jalali.to_jalali(t)
    # Default range: start of current Jalali month → today
    start = jalali.to_gregorian(ty, tm, 1)
    with db.db() as c:
        docs = doctors(c)
    include_notes = request.query_params.get("notes") == "1"
    return render(
        request, "export.html", user,
        docs=docs, years=year_choices(t),
        from_jy=ty, from_jm=tm, from_jd=1,
        to_jy=ty, to_jm=tm, to_jd=td,
        doctor_id=request.query_params.get("doctor", ""),
        include_notes=include_notes,
    )


@login_required(admin=True)
async def export_csv_download(request: Request, user):
    """Download appointments CSV for a Jalali (or Gregorian) inclusive range."""
    qp = request.query_params
    err = None
    day_from = day_to = None
    # Prefer Jalali parts; fall back to Gregorian YYYY-MM-DD if provided.
    g_from = jalali.en_digits(qp.get("from", "")).strip()
    g_to = jalali.en_digits(qp.get("to", "")).strip()
    try:
        if g_from and g_to and len(g_from) == 10 and len(g_to) == 10 and g_from[4] == "-":
            day_from = date.fromisoformat(g_from)
            day_to = date.fromisoformat(g_to)
        else:
            fy, fm, fd = (int(jalali.en_digits(str(qp.get(k, "")))) for k in ("from_jy", "from_jm", "from_jd"))
            ty_, tm_, td_ = (int(jalali.en_digits(str(qp.get(k, "")))) for k in ("to_jy", "to_jm", "to_jd"))
            if not (jalali.valid(fy, fm, fd) and jalali.valid(ty_, tm_, td_)):
                err = "بازهٔ تاریخ نامعتبر است."
            else:
                day_from = jalali.to_gregorian(fy, fm, fd)
                day_to = jalali.to_gregorian(ty_, tm_, td_)
    except Exception:
        err = "بازهٔ تاریخ را کامل کنید."
    if not err and day_from and day_to and day_from > day_to:
        err = "تاریخ شروع نباید بعد از تاریخ پایان باشد."
    doctor_id = None
    doc_q = qp.get("doctor", "").strip()
    if doc_q.isdigit():
        doctor_id = int(doc_q)
    include_notes = qp.get("notes") == "1"
    if err:
        t = today()
        ty, tm, td = jalali.to_jalali(t)
        with db.db() as c:
            docs = doctors(c)
        return render(
            request, "export.html", user, error=err, status_code=400,
            docs=docs, years=year_choices(t),
            from_jy=qp.get("from_jy", ty), from_jm=qp.get("from_jm", tm), from_jd=qp.get("from_jd", 1),
            to_jy=qp.get("to_jy", ty), to_jm=qp.get("to_jm", tm), to_jd=qp.get("to_jd", td),
            doctor_id=doc_q, include_notes=include_notes,
        )
    with db.db() as c:
        rows = export_csv.fetch_rows(
            c, day_from.isoformat(), day_to.isoformat(), doctor_id=doctor_id)
        body = export_csv.build_csv(rows, staff_header=STAFF_LABEL, include_notes=include_notes)
    fname = f"nobat-{jalali.jstr(day_from)}_{jalali.jstr(day_to)}.csv"
    return Response(
        body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "Cache-Control": "no-store",
        },
    )


# ---------------------------------------------------------------- initials search
@login_required()
async def search_appointments(request: Request, user):
    """Search by client initials. Admin: all; staff: own schedule only."""
    q = str(request.query_params.get("q", "")).strip()[:30]
    rows = []
    if len(q) >= 1:
        like = f"%{q}%"
        with db.db() as c:
            if user["is_admin"]:
                rows = c.execute(
                    "SELECT a.*, u.name AS doctor_name, cu.name AS created_by_name "
                    "FROM appointments a JOIN users u ON u.id = a.doctor_id "
                    "LEFT JOIN users cu ON cu.id = a.created_by "
                    "WHERE a.initials LIKE ? "
                    "ORDER BY a.day DESC, a.start_time LIMIT 200",
                    (like,),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT a.*, u.name AS doctor_name, cu.name AS created_by_name "
                    "FROM appointments a JOIN users u ON u.id = a.doctor_id "
                    "LEFT JOIN users cu ON cu.id = a.created_by "
                    "WHERE a.doctor_id = ? AND a.initials LIKE ? "
                    "ORDER BY a.day DESC, a.start_time LIMIT 200",
                    (user["id"], like),
                ).fetchall()
    return render(request, "search.html", user, q=q, rows=rows)


# ---------------------------------------------------------------- audit log (admin)
@login_required(admin=True)
async def audit_log_view(request: Request, user):
    """Admin-only append-only log. Filter by Gregorian day and/or actor."""
    day_q = jalali.en_digits(request.query_params.get("day", "")).strip()
    actor_q = jalali.en_digits(request.query_params.get("actor", "")).strip()
    day_filter = day_q if day_q and len(day_q) == 10 else None
    actor_id = None
    if actor_q:
        try:
            actor_id = int(actor_q)
        except ValueError:
            actor_id = None
    with db.db() as c:
        rows = audit.list_entries(c, day=day_filter, actor_user_id=actor_id, limit=200)
        actors = c.execute(
            "SELECT DISTINCT actor_user_id AS id, actor_username AS username "
            "FROM audit_log WHERE actor_user_id IS NOT NULL "
            "ORDER BY actor_username"
        ).fetchall()
        # Also list current admins so the filter is usable before any events.
        admins = c.execute(
            "SELECT id, username, name FROM users WHERE is_admin = 1 ORDER BY name"
        ).fetchall()
    return render(request, "audit.html", user, rows=rows, actors=actors, admins=admins,
                  day=day_filter or "", actor=str(actor_id or ""))


# ---------------------------------------------------------------- PWA files & health
async def service_worker(request: Request):
    return FileResponse(HERE / "static" / "sw.js", media_type="text/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


async def manifest(request: Request):
    return FileResponse(HERE / "static" / "manifest.webmanifest", media_type="application/manifest+json")


async def health(request: Request):
    return PlainTextResponse("ok")


# ---------------------------------------------------------------- app
class SecurityHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                h = message.setdefault("headers", [])
                h += [(b"x-frame-options", b"DENY"), (b"x-content-type-options", b"nosniff"),
                      (b"referrer-policy", b"no-referrer"),
                      (b"content-security-policy",
                       b"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                       b"frame-ancestors 'none'; form-action 'self'; base-uri 'none'")]
                if not scope["path"].startswith("/static"):
                    h.append((b"cache-control", b"no-store"))
            await send(message)
        return await self.app(scope, receive, send_wrapper)


@asynccontextmanager
async def lifespan(app):
    db.init()
    task = asyncio.create_task(notify.reminder_loop())
    log.info("Nobat %s started. Time zone %s, reminders at %s:00.", __version__, notify.TIMEZONE.key, notify.REMINDER_HOUR)
    yield
    task.cancel()


routes = [
    Route("/", home),
    Route("/login", login, methods=["GET", "POST"]),
    Route("/logout", logout, methods=["POST"]),
    Route("/me", my_schedule),
    Route("/calendar", calendar),
    Route("/day/{jdate}", day_view),
    Route("/appointments/new", appt_new, methods=["GET", "POST"]),
    Route("/appointments/{id:int}/edit", appt_edit, methods=["GET", "POST"]),
    Route("/appointments/{id:int}/cancel", appt_cancel, methods=["POST"]),
    Route("/appointments/{id:int}/status", appt_set_status, methods=["POST"]),
    Route("/schedule", schedule_settings, methods=["GET", "POST"]),
    Route("/audit", audit_log_view),
    Route("/export", export_form),
    Route("/export.csv", export_csv_download),
    Route("/search", search_appointments),
    Route("/users", users_list),
    Route("/users/new", user_new, methods=["GET", "POST"]),
    Route("/users/{id:int}/edit", user_edit, methods=["GET", "POST"]),
    Route("/users/{id:int}/delete", user_delete, methods=["POST"]),
    Route("/password", change_password, methods=["GET", "POST"]),
    Route("/notifications", notif_help),
    Route("/notifications/test", notif_test, methods=["POST"]),
    Route("/sw.js", service_worker),
    Route("/manifest.webmanifest", manifest),
    Route("/health", health),
    Mount("/static", StaticFiles(directory=str(HERE / "static")), name="static"),
]

app = Starlette(
    routes=routes,
    lifespan=lifespan,
    middleware=[
        Middleware(SecurityHeaders),
        Middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="nobat",
                   max_age=60 * 60 * 24 * 30, same_site="lax", https_only=COOKIE_SECURE),
    ],
)
