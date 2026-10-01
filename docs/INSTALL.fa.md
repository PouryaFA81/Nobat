<div dir="rtl">

# راهنمای نصب

[English](INSTALL.md)

مراحل را به ترتیب انجام دهید. همه‌ی دستورها روی سرور اجرا می‌شوند.

**پیش‌نیازها:**
- یک سرور لینوکسی با Docker و Docker Compose
- دو نام دامنه که به سرور اشاره کنند، مثلاً `nobat.example.com` (پنل) و `ntfy.example.com` (اعلان‌ها)
- یک پراکسی معکوس با HTTPS، مثل [Caddy](https://caddyserver.com). برنامه‌ی گوشی (PWA) فقط با HTTPS کار می‌کند.

در این راهنما، به جای `nobat.example.com` و `ntfy.example.com` آدرس‌های خودتان را بگذارید.

---

### ۱. دریافت کد

</div>

```bash
cd /srv
git clone https://github.com/PouryaFA81/Nobat.git nobat
cd nobat
```

<div dir="rtl">

(هر پوشه‌ای مناسب است؛ `/srv/nobat` فقط یک نمونه است.)

### ۲. بررسی اینکه هر دو آدرس به سرور اشاره می‌کنند

</div>

```bash
dig +short nobat.example.com
dig +short ntfy.example.com
```

<div dir="rtl">

هر دو باید IP عمومی سرور شما را نشان دهند.

### ۳. ساخت فایل تنظیمات

</div>

```bash
cp .env.example .env
openssl rand -hex 32
```

<div dir="rtl">

فایل `.env` را باز کنید و:
- رشته‌ی تصادفی را جلوی `SECRET_KEY=` بگذارید
- `BASE_URL` و `NTFY_PUBLIC_URL` را روی دو آدرس خودتان تنظیم کنید
- `SOURCE_URL` را روی آدرس مخزنی بگذارید که از آن نصب کرده‌اید

فعلاً `NTFY_TOKEN` را خالی بگذارید.

سپس فایل `ntfy/server.yml` را باز کنید و `base-url` را روی آدرس اعلان‌ها بگذارید (همان مقدار `NTFY_PUBLIC_URL`).

### ۴. ساخت پوشه‌های داده

پنل داخل کانتینر با شناسه‌ی کاربری ۱۰۰۰ اجرا می‌شود، پس باید مالک پوشه‌ی داده‌اش باشد:

</div>

```bash
mkdir -p data ntfy/data ntfy/cache
sudo chown 1000:1000 data
```

<div dir="rtl">

### ۵. فقط اگر پراکسی معکوس شما داخل Docker اجرا می‌شود

اگر پراکسی مستقیماً روی سرور نصب است، این مرحله را رد کنید.

</div>

```bash
cp docker-compose.override.example.yml docker-compose.override.yml
```

<div dir="rtl">

فایل `docker-compose.override.yml` را باز کنید و سه توضیح بالای آن را انجام دهید.

### ۶. اجرا

</div>

```bash
docker compose up -d --build
docker compose logs --tail 20
```

<div dir="rtl">

باید `Nobat 1.0.0 started` و `Listening on :80` (از ntfy) را ببینید.

### ۷. اجازه‌ی ارسال اعلان به پنل

این چهار دستور را یکی‌یکی اجرا کنید:

</div>

```bash
docker compose exec -e NTFY_PASSWORD=$(openssl rand -hex 16) ntfy ntfy user add nobatapp
docker compose exec ntfy ntfy access nobatapp 'nb_*' write-only
docker compose exec ntfy ntfy access everyone 'nb_*' read-only
docker compose exec ntfy ntfy token add nobatapp
```

<div dir="rtl">

کار این دستورها: فقط پنل می‌تواند اعلان بفرستد. هر گوشی فقط وقتی می‌تواند اعلان‌ها را بخواند که نام طولانی و تصادفی موضوع (topic) را بداند، و هر همکار موضوع مخصوص خودش را دارد.

دستور آخر توکنی چاپ می‌کند که با `tk_` شروع می‌شود. آن را در `.env` جلوی `NTFY_TOKEN=` بگذارید و اعمال کنید:

</div>

```bash
docker compose up -d
```

<div dir="rtl">

### ۸. افزودن دو آدرس به پراکسی معکوس

برای Caddy که روی خود سرور نصب است، این را به Caddyfile اضافه کنید:

</div>

```
nobat.example.com {
    reverse_proxy 127.0.0.1:8000
}

ntfy.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

<div dir="rtl">

اگر Caddy داخل Docker است (مرحله‌ی ۵)، به جای آن‌ها از `nobat:8000` و `nobat-ntfy:80` استفاده کنید.

Caddy را دوباره بارگذاری کنید و بررسی کنید:

</div>

```bash
curl -s https://nobat.example.com/health
```

<div dir="rtl">

باید `ok` چاپ شود.

### ۹. ساخت حساب هماهنگ‌کننده

</div>

```bash
docker compose exec nobat python -m app.manage create-admin
```

<div dir="rtl">

به پرسش‌ها پاسخ دهید. وقتی پرسید آیا این شخص خودش هم نوبت می‌گیرد، اگر هماهنگ‌کننده خودش هم مراجع می‌بیند **Y** را بزنید.

آدرس `https://nobat.example.com` را باز کنید و وارد شوید.

### ۱۰. افزودن همکاران

در پنل به **همکاران ← + همکار جدید** بروید. نام کاربری و رمز اولیه را به هر همکار بدهید.

هر همکار بعد از ورود، از منو گزینه‌ی **تنظیم اعلان‌ها** را باز می‌کند. آنجا مراحل دقیق برنامه‌ی ntfy روی گوشی،
موضوع اختصاصی خودش و دکمه‌ی ارسال اعلان آزمایشی را می‌بیند.

### ۱۱. پشتیبان‌گیری روزانه

crontab را باز کنید:

</div>

```bash
crontab -e
```

<div dir="rtl">

این خط‌ها را اضافه کنید (اگر پوشه‌ی دیگری استفاده کرده‌اید، `/srv/nobat` را عوض کنید):

</div>

```
0 3 * * * cd /srv/nobat && docker compose exec -T nobat python -m app.manage backup >> /srv/nobat/backup.log 2>&1
30 3 * * * cd /srv/nobat && docker compose exec -T nobat python -m app.manage backup-prune --days 14 >> /srv/nobat/backup.log 2>&1
```

<div dir="rtl">

دستور `backup` بدون مسیر، فایل را در `data/backups/nobat-YYYY-MM-DD.db` می‌نویسد.
`backup-prune` پشتیبان‌های قدیمی‌تر از ۱۴ روز را پاک می‌کند.
با `ls -la data/backups/` و `cat backup.log` بررسی کنید. بهتر است هر از گاهی پشتیبان‌ها را روی دستگاه دیگری هم کپی کنید.

بعد از به‌روزرسانی Nobat یک‌بار مهاجرت پایگاه‌داده را اجرا کنید:

</div>

```bash
docker compose exec nobat python -m app.manage migrate
```

<div dir="rtl">

(نصب تازه هم هنگام راه‌اندازی به‌صورت خودکار مهاجرت را اعمال می‌کند.)

---

## دستورهای روزمره

| کار | دستور |
|---|---|
| دیدن لاگ‌ها | `docker compose logs -f nobat` |
| اعمال مهاجرت پایگاه‌داده | `docker compose exec nobat python -m app.manage migrate` |
| بازنشانی رمز فراموش‌شده | `docker compose exec nobat python -m app.manage reset-password USERNAME` |
| پشتیبان‌گیری فوری | `docker compose exec nobat python -m app.manage backup` |
| پاکسازی پشتیبان‌های قدیمی | `docker compose exec nobat python -m app.manage backup-prune --days 14` |
| بازیابی پشتیبان در فایل دیگر | `docker compose exec nobat python -m app.manage restore /data/backups/FILE.db --to /data/restored.db` |
| بازیابی روی پایگاه زنده | `docker compose exec nobat python -m app.manage restore /data/backups/FILE.db --force` |
| غیرفعال کردن کاربر | `docker compose exec nobat python -m app.manage deactivate-user USERNAME` |
| حذف همیشگی کاربر | `docker compose exec nobat python -m app.manage delete-user USERNAME --confirm YES` |
| به‌روزرسانی به نسخه‌ی جدید | `git pull && docker compose up -d --build && docker compose exec nobat python -m app.manage migrate` |

## انتقال به سرور دیگر

۱. روی سرور قبلی: `docker compose down`  
۲. کل پوشه (شامل `data/` و `ntfy/`) را به سرور جدید کپی کنید.  
۳. روی سرور جدید، مراحل ۵ (در صورت نیاز)، ۶ و ۸ را تکرار کنید.  
۴. هر دو آدرس را در DNS به IP سرور جدید اشاره دهید.

گوشی‌ها بدون هیچ تغییری کار می‌کنند، چون آدرس‌ها همان است.

## رفع اشکال

**اعلانی نمی‌آید و در لاگ `500 Unable to connect` یا خطای پراکسی دیده می‌شود.**
ممکن است سرور شما تنظیم `HTTP_PROXY` را به کانتینرها بدهد. از نسخه‌ی ۱.۰.۰، پنل برای سرور اعلان خودش پراکسی را نادیده می‌گیرد.
اگر باز هم این خطا را دیدید، با `docker compose exec nobat env | grep -i proxy` بررسی کنید.

**اعلانی نمی‌آید و در لاگ `403` دیده می‌شود.**
توکن داخل `.env` خالی یا اشتباه است. دستور آخر مرحله‌ی ۷ را دوباره اجرا کنید و سپس `docker compose up -d`.

**پنل پیام «SECRET_KEY must be set» می‌دهد.**
مقدار `SECRET_KEY` در `.env` خالی یا کوتاه‌تر از ۳۲ نویسه است (مرحله‌ی ۳).

**اعلان‌ها روی آیفون دیر می‌رسند.**
iOS اتصال دائمی به سرورهای ntfy شخصی را نگه نمی‌دارد. توضیح پایین فایل `ntfy/server.yml` را ببینید.

**تغییرات ظاهری روی گوشی دیده نمی‌شود.**
ممکن است گوشی فایل‌های قدیمی را نگه داشته باشد. برنامه را کامل ببندید و دوباره باز کنید.

</div>
