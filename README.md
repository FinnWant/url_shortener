# url_shortener

FastAPI + SQLite URL shortener with click tracking.

## Run

```
pip install -r requirements.txt
export ADMIN_TOKEN=change-me      # required; the app refuses to start without it
export DB_PATH=./shortener.db     # required; SQLite file (created if missing)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

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

Targets must be http/https. Codes: 1–32 of `A-Za-z0-9_-`; `api`, `admin`, `static`, `health` are reserved (case-insensitive).

## Test

```
pytest
```
