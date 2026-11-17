# url_shortener

FastAPI + SQLite URL shortener with click tracking.

## Run

```
pip install -r requirements.txt
export ADMIN_TOKEN=change-me      # required; the app refuses to start without it
export DB_PATH=./shortener.db     # required; SQLite file (created if missing)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Install on an Ubuntu server

Short version (systemd service as a dedicated user, listening on `127.0.0.1:8301`):

```
sudo apt update && sudo apt install -y python3-venv git
sudo useradd --system --home /opt/link-shortener --shell /usr/sbin/nologin linkshort
sudo git clone <REPO_URL> /opt/link-shortener && cd /opt/link-shortener
sudo python3 -m venv .venv && sudo .venv/bin/pip install -r requirements.txt
sudo install -m 600 -o root -g root deploy/link-shortener.env.example /etc/link-shortener.env
sudo sed -i "s/^ADMIN_TOKEN=.*/ADMIN_TOKEN=$(openssl rand -hex 24)/" /etc/link-shortener.env
sudo cp deploy/link-shortener.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now link-shortener
curl http://127.0.0.1:8301/health   # -> ok
```

Put nginx/Caddy in front for TLS (it must set `X-Forwarded-For`). See
[DEPLOY.md](DEPLOY.md) for updating, rate limiting, the nginx example and backups.

## API

- `GET /health` → `ok`
- `GET /{code}` → 302 to the target; records time, referrer, user-agent family
  and a salted hash of the client IP (salt rotates daily, derived from a random
  secret stored in the DB; the raw IP is never stored). Behind a reverse proxy,
  the hashed IP is the proxy's unless uvicorn is run with `--proxy-headers`/`--forwarded-allow-ips`.
- Admin API, header `Authorization: Bearer $ADMIN_TOKEN`:
  - `POST /api/links` `{"target": "https://...", "code": "optional"}` → 201 (random 6-char code if omitted)
  - `GET /api/links` (includes click counts)
  - `DELETE /api/links/{code}` → 204 (also deletes its clicks)

  - `GET /api/links/{code}/stats[?days=30]` → clicks per day (UTC, zero-filled), top 10 referrers (`(direct)` when absent), browser families

## Admin page

`/admin` (static, no external assets): enter the admin token once (kept in
`sessionStorage`, cleared on sign-out/401), create/delete links, see total clicks,
and per-link stats with a 30-day bar chart. The chart is a small dependency-free
SVG implementation in `app/static/chart.js` (no CDN, no vendored library needed).

Targets must be http/https. Codes: 1–32 of `A-Za-z0-9_-`; `api`, `admin`, `static`, `health` are reserved (case-insensitive).

## Test

```
pytest
```
