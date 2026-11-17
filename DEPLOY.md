# Deploying on Ubuntu

The app runs under systemd as user `linkshort`, listening on `127.0.0.1:8301`.
Put a reverse proxy (nginx/Caddy) in front for TLS.

## Install

```bash
sudo apt update && sudo apt install -y python3-venv git

# dedicated system user, no login
sudo useradd --system --home /opt/link-shortener --shell /usr/sbin/nologin linkshort

# code (replace the URL with your repo)
sudo git clone <REPO_URL> /opt/link-shortener
cd /opt/link-shortener
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt

# config: DB_PATH and ADMIN_TOKEN (readable only by root; systemd reads it)
sudo install -m 600 -o root -g root deploy/link-shortener.env.example /etc/link-shortener.env
sudo sed -i "s/^ADMIN_TOKEN=.*/ADMIN_TOKEN=$(openssl rand -hex 24)/" /etc/link-shortener.env

# service (StateDirectory creates /var/lib/link-shortener owned by linkshort)
sudo cp deploy/link-shortener.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now link-shortener
```

Check: `curl http://127.0.0.1:8301/health` → `ok`; logs: `journalctl -u link-shortener -f`.
The admin page is at `/admin`; use the token from `/etc/link-shortener.env`.

## Update

```bash
cd /opt/link-shortener
sudo git pull --ff-only
sudo .venv/bin/pip install -r requirements.txt
sudo systemctl restart link-shortener
```

If `deploy/link-shortener.service` changed, re-copy it and run `sudo systemctl daemon-reload` first.

## Rate limiting

Redirects (`/<code>`) are limited per hashed client IP: `RATE_LIMIT` requests
per `RATE_WINDOW` seconds (default 60 per 60 s), then HTTP 429 with `Retry-After`.
State is in memory, per process (resets on restart). Uvicorn runs with
`--proxy-headers` trusting only 127.0.0.1, so your proxy **must** set
`X-Forwarded-For`, otherwise all clients share the proxy's IP. nginx example:

```nginx
location / {
    proxy_pass http://127.0.0.1:8301;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header Host $host;
}
```

## Backup

The data is a single SQLite file: `sudo sqlite3 /var/lib/link-shortener/links.db ".backup /tmp/links.bak"`.
