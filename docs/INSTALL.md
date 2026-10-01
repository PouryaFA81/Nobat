# Installation guide

[فارسی](INSTALL.fa.md)

Do the steps in order. Run every command on your server.

**You need:**
- A Linux server with Docker and Docker Compose
- Two DNS names pointing at the server, for example `nobat.example.com` (panel) and `ntfy.example.com` (notifications)
- A reverse proxy that provides HTTPS, such as [Caddy](https://caddyserver.com). A PWA only works over HTTPS.

Throughout this guide, replace `nobat.example.com` and `ntfy.example.com` with your own names.

---

### 1. Get the code

```bash
cd /srv
git clone https://github.com/PouryaFA81/Nobat.git nobat
cd nobat
```

(Any folder works. `/srv/nobat` is just an example.)

### 2. Check both names point to the server

```bash
dig +short nobat.example.com
dig +short ntfy.example.com
```

Both should print your server's public IP.

### 3. Create the settings file

```bash
cp .env.example .env
openssl rand -hex 32
```

Open `.env` and:
- paste the random string after `SECRET_KEY=`
- set `BASE_URL` and `NTFY_PUBLIC_URL` to your two addresses
- set `SOURCE_URL` to the repository you installed from

Leave `NTFY_TOKEN` empty for now.

Then open `ntfy/server.yml` and set `base-url` to your notification address (the same value as `NTFY_PUBLIC_URL`).

### 4. Create the data folders

The panel runs as user ID 1000 inside its container, so it needs to own its data folder:

```bash
mkdir -p data ntfy/data ntfy/cache
sudo chown 1000:1000 data
```

### 5. Only if your reverse proxy runs in Docker

Skip this step if your reverse proxy runs directly on the server.

```bash
cp docker-compose.override.example.yml docker-compose.override.yml
```

Open `docker-compose.override.yml` and follow the three comments at the top.

### 6. Start it

```bash
docker compose up -d --build
docker compose logs --tail 20
```

You should see `Nobat 1.0.0 started` and ntfy's `Listening on :80`.

### 7. Allow the panel to send notifications

Run these four commands one by one:

```bash
docker compose exec -e NTFY_PASSWORD=$(openssl rand -hex 16) ntfy ntfy user add nobatapp
docker compose exec ntfy ntfy access nobatapp 'nb_*' write-only
docker compose exec ntfy ntfy access everyone 'nb_*' read-only
docker compose exec ntfy ntfy token add nobatapp
```

What they do: only the panel can send notifications. A phone can read a topic only if it knows the topic's long random name, and each staff member gets their own.

The last command prints a token starting with `tk_`. Paste it into `.env` after `NTFY_TOKEN=`, then apply it:

```bash
docker compose up -d
```

### 8. Add the two addresses to your reverse proxy

For Caddy running on the server, add to your Caddyfile:

```
nobat.example.com {
    reverse_proxy 127.0.0.1:8000
}

ntfy.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

If Caddy runs in Docker (step 5), use `nobat:8000` and `nobat-ntfy:80` instead.

Reload Caddy, then check:

```bash
curl -s https://nobat.example.com/health
```

It should print `ok`.

### 9. Create the coordinator's account

```bash
docker compose exec nobat python -m app.manage create-admin
```

Answer the questions. When asked whether this person also receives appointments, answer **Y** if the coordinator sees clients too.

Open `https://nobat.example.com` and log in.

### 10. Add staff members

In the panel, go to **همکاران → + همکار جدید**. Give each person their username and starting password.

After logging in, each person opens **تنظیم اعلان‌ها** from the menu. It shows the exact steps for the ntfy phone app,
their personal topic, and a button to send a test notification.

### 11. Set up a daily backup

Open your crontab:

```bash
crontab -e
```

Add these lines (change `/srv/nobat` if you used another folder):

```
0 3 * * * cd /srv/nobat && docker compose exec -T nobat python -m app.manage backup >> /srv/nobat/backup.log 2>&1
30 3 * * * cd /srv/nobat && docker compose exec -T nobat python -m app.manage backup-prune --days 14 >> /srv/nobat/backup.log 2>&1
```

`backup` with no path writes to `data/backups/nobat-YYYY-MM-DD.db` inside the container (`/data/backups/`…).
`backup-prune` deletes backups older than 14 days (change `--days` if you want).
Check with `ls -la data/backups/` and `cat backup.log`. Copy backups off the server now and then.

After upgrading Nobat, apply database migrations once:

```bash
docker compose exec nobat python -m app.manage migrate
```

(Fresh installs also run migrations automatically on startup / `init`.)

---

## Everyday commands

| What | Command |
|---|---|
| See logs | `docker compose logs -f nobat` |
| Apply DB migrations | `docker compose exec nobat python -m app.manage migrate` |
| Reset a forgotten password | `docker compose exec nobat python -m app.manage reset-password USERNAME` |
| Make a backup now | `docker compose exec nobat python -m app.manage backup` |
| Prune old backups | `docker compose exec nobat python -m app.manage backup-prune --days 14` |
| Restore a backup to a file | `docker compose exec nobat python -m app.manage restore /data/backups/FILE.db --to /data/restored.db` |
| Restore over the live DB | `docker compose exec nobat python -m app.manage restore /data/backups/FILE.db --force` |
| Deactivate a user | `docker compose exec nobat python -m app.manage deactivate-user USERNAME` |
| Hard-delete a user | `docker compose exec nobat python -m app.manage delete-user USERNAME --confirm YES` |
| Update to a new version | `git pull && docker compose up -d --build && docker compose exec nobat python -m app.manage migrate` |

## Moving to another server

1. On the old server: `docker compose down`
2. Copy the whole folder (it includes `data/` and `ntfy/`) to the new server.
3. On the new server, repeat steps 5 (if needed), 6 and 8.
4. Point both DNS names to the new server's IP.

Phones keep working without changes, because the addresses stay the same.

## Troubleshooting

**No notifications, and the log shows `500 Unable to connect` or a proxy error.**
Your server may pass an `HTTP_PROXY` setting into containers. The panel ignores proxy settings for its own
notification server since version 1.0.0. If you still see this, check with `docker compose exec nobat env | grep -i proxy`.

**No notifications, and the log shows `403`.**
The token in `.env` is missing or wrong. Repeat the last command of step 7 and run `docker compose up -d`.

**The panel says "SECRET_KEY must be set".**
`SECRET_KEY` in `.env` is empty or shorter than 32 characters (step 3).

**Notifications arrive late on iPhone.**
iOS doesn't keep a live connection to self-hosted ntfy servers. See the comment at the bottom of `ntfy/server.yml`.

**Changes to the design don't show up on a phone.**
The phone may have cached old style files. Close the app completely and open it again.
