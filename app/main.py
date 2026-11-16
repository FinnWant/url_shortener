import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

RESERVED_CODES = {"api", "admin", "static", "health"}
CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
    code TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clicks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    clicked_at TEXT NOT NULL,
    referrer TEXT,
    ua_family TEXT NOT NULL,
    ip_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS clicks_code ON clicks(code);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def ua_family(ua: str | None) -> str:
    """Coarse user-agent family (order matters: Edge/Opera contain 'Chrome')."""
    if not ua:
        return "Unknown"
    u = ua.lower()
    for needle, name in [
        ("bot", "Bot"), ("spider", "Bot"), ("crawler", "Bot"),
        ("curl", "curl"), ("python-requests", "Python"), ("python-httpx", "Python"),
        ("edg/", "Edge"), ("edge/", "Edge"), ("opr/", "Opera"), ("opera", "Opera"),
        ("firefox", "Firefox"), ("fxios", "Firefox"),
        ("chrome", "Chrome"), ("crios", "Chrome"),
        ("safari", "Safari"),
    ]:
        if needle in u:
            return name
    return "Other"


def validate_target(url: str) -> str:
    url = url.strip()
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        raise ValueError("invalid URL")
    if parts.scheme.lower() not in ("http", "https"):
        raise ValueError("target must be an http or https URL")
    if not host:
        raise ValueError("target must include a host")
    if len(url) > 2048 or any(c in url for c in "\r\n\x00") or any(c.isspace() for c in url):
        raise ValueError("invalid URL")
    return url


def validate_code(code: str) -> str:
    if not CODE_RE.match(code):
        raise ValueError("code must be 1-32 chars of letters, digits, '-' or '_'")
    if code.lower() in RESERVED_CODES:
        raise ValueError(f"'{code}' is a reserved code")
    return code


class LinkIn(BaseModel):
    target: str
    code: str | None = None


def create_app(db_path: str | None = None, admin_token: str | None = None) -> FastAPI:
    db_path = db_path or os.environ.get("DB_PATH")
    admin_token = admin_token or os.environ.get("ADMIN_TOKEN")
    if not admin_token:
        raise RuntimeError("ADMIN_TOKEN environment variable is required")
    if not db_path:
        raise RuntimeError("DB_PATH environment variable is required")

    def connect() -> sqlite3.Connection:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    with closing(connect()) as c, c:
        c.executescript(SCHEMA)
        # Persistent random secret; the daily salt is derived from it, so
        # IP hashes can't be reversed by brute force without the DB secret.
        c.execute("INSERT OR IGNORE INTO meta VALUES ('salt_secret', ?)",
                  (secrets.token_hex(32),))
        secret = c.execute("SELECT value FROM meta WHERE key='salt_secret'").fetchone()[0]

    def ip_hash(ip: str, now: datetime) -> str:
        day = now.strftime("%Y-%m-%d")
        salt = hmac.new(secret.encode(), day.encode(), hashlib.sha256).digest()
        return hmac.new(salt, ip.encode(), hashlib.sha256).hexdigest()

    bearer = HTTPBearer(auto_error=False)

    def require_admin(cred: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if cred is None or not hmac.compare_digest(
            cred.credentials.encode(), admin_token.encode()
        ):
            raise HTTPException(401, "invalid or missing token",
                                headers={"WWW-Authenticate": "Bearer"})

    app = FastAPI(title="URL Shortener")
    api = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])

    def row(r):
        return {"code": r["code"], "target": r["target"], "created_at": r["created_at"],
                "clicks": r["clicks"]}

    q = ("SELECT l.*, (SELECT COUNT(*) FROM clicks c WHERE c.code=l.code) AS clicks "
         "FROM links l")

    @api.post("/links", status_code=201)
    def create_link(body: LinkIn):
        try:
            target = validate_target(body.target)
            code = validate_code(body.code) if body.code is not None else None
        except ValueError as e:
            raise HTTPException(422, str(e))
        now = datetime.now(timezone.utc).isoformat()
        with closing(connect()) as c, c:
            if code is not None:
                try:
                    c.execute("INSERT INTO links VALUES (?,?,?)", (code, target, now))
                except sqlite3.IntegrityError:
                    raise HTTPException(409, "code already exists")
            else:
                for _ in range(20):
                    code = "".join(secrets.choice(ALPHABET) for _ in range(6))
                    if code.lower() in RESERVED_CODES:
                        continue
                    try:
                        c.execute("INSERT INTO links VALUES (?,?,?)", (code, target, now))
                        break
                    except sqlite3.IntegrityError:
                        continue
                else:
                    raise HTTPException(500, "could not generate a unique code")
        return {"code": code, "target": target, "created_at": now, "clicks": 0}

    @api.get("/links")
    def list_links():
        with closing(connect()) as c:
            return [row(r) for r in c.execute(q + " ORDER BY created_at, code")]

    @api.delete("/links/{code}", status_code=204)
    def delete_link(code: str):
        with closing(connect()) as c, c:
            cur = c.execute("DELETE FROM links WHERE code=?", (code,))
            if cur.rowcount == 0:
                raise HTTPException(404, "link not found")
            c.execute("DELETE FROM clicks WHERE code=?", (code,))

    app.include_router(api)

    @app.get("/health", response_class=PlainTextResponse)
    def health():
        return "ok"

    @app.get("/{code}")
    def follow(code: str, request: Request):
        if code.lower() in RESERVED_CODES:
            raise HTTPException(404, "not found")
        now = datetime.now(timezone.utc)
        with closing(connect()) as c, c:
            r = c.execute("SELECT target FROM links WHERE code=?", (code,)).fetchone()
            if r is None:
                raise HTTPException(404, "not found")
            ip = request.client.host if request.client else "unknown"
            c.execute(
                "INSERT INTO clicks (code, clicked_at, referrer, ua_family, ip_hash) "
                "VALUES (?,?,?,?,?)",
                (code, now.isoformat(), request.headers.get("referer"),
                 ua_family(request.headers.get("user-agent")), ip_hash(ip, now)),
            )
        return RedirectResponse(r["target"], status_code=302)

    app.state.ip_hash = ip_hash
    app.state.connect = connect
    return app


# Module-level app for uvicorn; fails fast if ADMIN_TOKEN/DB_PATH are missing.
app = create_app()
