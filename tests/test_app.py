import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app, ua_family

TOKEN = "s3cret"
H = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(tmp_path):
    db = str(tmp_path / "t.db")
    app = create_app(db_path=db, admin_token=TOKEN)
    c = TestClient(app, follow_redirects=False)
    c.db = db
    c.app_ = app
    return c


def mk(client, **body):
    return client.post("/api/links", json=body, headers=H)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.text == "ok"


def test_redirect_and_click_recording(client):
    mk(client, target="https://example.com/x", code="abc")
    r = client.get("/abc", headers={"Referer": "https://ref.test/",
                                    "User-Agent": "Mozilla/5.0 Firefox/120.0"})
    assert r.status_code == 302
    assert r.headers["location"] == "https://example.com/x"
    rows = sqlite3.connect(client.db).execute(
        "SELECT code, clicked_at, referrer, ua_family, ip_hash FROM clicks").fetchall()
    assert len(rows) == 1
    code, at, ref, fam, h = rows[0]
    assert (code, ref, fam) == ("abc", "https://ref.test/", "Firefox")
    assert at and len(h) == 64
    assert "testclient" not in h
    assert client.get("/api/links", headers=H).json()[0]["clicks"] == 1


def test_raw_ip_never_stored(client):
    mk(client, target="https://example.com", code="abc")
    client.get("/abc")
    dump = "\n".join(sqlite3.connect(client.db).iterdump())
    assert "testclient" not in dump


def test_ip_hash_rotates_daily(client):
    f = client.app_.state.ip_hash
    d1 = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    d1b = datetime(2026, 1, 1, 23, tzinfo=timezone.utc)
    d2 = datetime(2026, 1, 2, 1, tzinfo=timezone.utc)
    assert f("1.2.3.4", d1) == f("1.2.3.4", d1b)
    assert f("1.2.3.4", d1) != f("1.2.3.4", d2)
    assert f("1.2.3.4", d1) != f("1.2.3.5", d1)


def test_unknown_code_404_and_no_click(client):
    assert client.get("/nope").status_code == 404
    assert sqlite3.connect(client.db).execute("SELECT COUNT(*) FROM clicks").fetchone()[0] == 0


def test_ua_family():
    assert ua_family("Mozilla/5.0 Chrome/1 Safari/5 Edg/1") == "Edge"
    assert ua_family("Mozilla/5.0 Chrome/1 Safari/5") == "Chrome"
    assert ua_family("curl/8") == "curl"
    assert ua_family(None) == "Unknown"


def test_random_code(client):
    r = mk(client, target="http://example.com")
    assert r.status_code == 201
    code = r.json()["code"]
    assert len(code) == 6 and code.isalnum()
    assert client.get(f"/{code}").status_code == 302


def test_duplicate_code(client):
    assert mk(client, target="https://a.com", code="dup").status_code == 201
    assert mk(client, target="https://b.com", code="dup").status_code == 409


def test_list_and_delete(client):
    mk(client, target="https://a.com", code="one")
    mk(client, target="https://b.com", code="two")
    assert {l["code"] for l in client.get("/api/links", headers=H).json()} == {"one", "two"}
    assert client.delete("/api/links/one", headers=H).status_code == 204
    assert client.delete("/api/links/one", headers=H).status_code == 404
    assert client.get("/one").status_code == 404


@pytest.mark.parametrize("method,path", [
    ("get", "/api/links"), ("post", "/api/links"), ("delete", "/api/links/x")])
def test_auth_failures(client, method, path):
    kw = {"json": {"target": "https://a.com"}} if method == "post" else {}
    assert getattr(client, method)(path, **kw).status_code == 401
    r = getattr(client, method)(path, headers={"Authorization": "Bearer wrong"}, **kw)
    assert r.status_code == 401
    r = getattr(client, method)(path, headers={"Authorization": f"Basic {TOKEN}"}, **kw)
    assert r.status_code == 401


@pytest.mark.parametrize("target", [
    "javascript:alert(1)", "ftp://example.com/x", "file:///etc/passwd",
    "example.com", "//example.com", "https://", "data:text/html,hi", "",
    "https://exa mple.com"])
def test_invalid_targets(client, target):
    assert mk(client, target=target).status_code == 422


@pytest.mark.parametrize("code", ["api", "admin", "static", "health", "API", "Admin"])
def test_reserved_codes(client, code):
    assert mk(client, target="https://a.com", code=code).status_code == 422


@pytest.mark.parametrize("code", ["", "a/b", "has space", "x" * 33, "é"])
def test_invalid_codes(client, code):
    assert mk(client, target="https://a.com", code=code).status_code == 422


def test_reserved_paths_not_redirects(client):
    assert client.get("/api").status_code == 404
    assert client.get("/static").status_code == 404


def test_refuses_to_start_without_token(tmp_path, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        create_app(db_path=str(tmp_path / "x.db"))
    monkeypatch.setenv("ADMIN_TOKEN", "")
    with pytest.raises(RuntimeError):
        create_app(db_path=str(tmp_path / "x.db"))
