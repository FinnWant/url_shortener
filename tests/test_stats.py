import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

TOKEN = "s3cret"
H = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(tmp_path):
    db = str(tmp_path / "t.db")
    c = TestClient(create_app(db_path=db, admin_token=TOKEN), follow_redirects=False)
    c.db = db
    c.post("/api/links", json={"target": "https://example.com", "code": "abc"}, headers=H)
    return c


def add_click(client, days_ago, ref=None, ua="Firefox"):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    with sqlite3.connect(client.db) as c:
        c.execute("INSERT INTO clicks (code, clicked_at, referrer, ua_family, ip_hash) "
                  "VALUES ('abc', ?, ?, ?, 'h')", (ts, ref, ua))


def test_stats_requires_auth(client):
    assert client.get("/api/links/abc/stats").status_code == 401
    assert client.get("/api/links/abc/stats",
                      headers={"Authorization": "Bearer nope"}).status_code == 401


def test_stats_unknown_link(client):
    assert client.get("/api/links/zzz/stats", headers=H).status_code == 404


def test_stats_empty_is_zero_filled(client):
    s = client.get("/api/links/abc/stats", headers=H).json()
    assert s["clicks"] == 0
    assert len(s["clicks_per_day"]) == 30
    assert all(d["clicks"] == 0 for d in s["clicks_per_day"])
    assert s["top_referrers"] == [] and s["browsers"] == []


def test_stats_per_day_window(client):
    add_click(client, 0); add_click(client, 0); add_click(client, 5)
    add_click(client, 29); add_click(client, 30)  # day 30 is outside the window
    s = client.get("/api/links/abc/stats", headers=H).json()
    days = s["clicks_per_day"]
    assert days[-1]["clicks"] == 2 and days[-6]["clicks"] == 1 and days[0]["clicks"] == 1
    assert sum(d["clicks"] for d in days) == 4
    assert s["clicks"] == 5  # total includes older clicks
    dates = [d["date"] for d in days]
    assert dates == sorted(dates) and dates[-1] == datetime.now(timezone.utc).date().isoformat()


def test_stats_referrers_and_browsers(client):
    for _ in range(3): add_click(client, 0, ref="https://a.test/", ua="Chrome")
    add_click(client, 0, ref="https://b.test/", ua="Firefox")
    add_click(client, 0, ref=None, ua="Chrome")
    add_click(client, 0, ref="", ua="Safari")
    s = client.get("/api/links/abc/stats", headers=H).json()
    assert s["top_referrers"][0] == {"referrer": "https://a.test/", "clicks": 3}
    assert {"referrer": "(direct)", "clicks": 2} in s["top_referrers"]
    assert s["browsers"][0] == {"family": "Chrome", "clicks": 4}
    assert sum(b["clicks"] for b in s["browsers"]) == 6


def test_stats_via_real_redirect(client):
    client.get("/abc", headers={"Referer": "https://r.test/", "User-Agent": "curl/8"})
    s = client.get("/api/links/abc/stats", headers=H).json()
    assert s["clicks_per_day"][-1]["clicks"] == 1
    assert s["top_referrers"] == [{"referrer": "https://r.test/", "clicks": 1}]
    assert s["browsers"] == [{"family": "curl", "clicks": 1}]


def test_stats_days_param_clamped(client):
    assert len(client.get("/api/links/abc/stats?days=7", headers=H).json()["clicks_per_day"]) == 7
    assert len(client.get("/api/links/abc/stats?days=9999", headers=H).json()["clicks_per_day"]) == 365


def test_admin_page_and_static(client):
    r = client.get("/admin")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "http://" not in r.text.replace("http://www.w3.org", "") .replace("https://example.com", "")
    for f in ("admin.js", "chart.js", "admin.css"):
        assert client.get(f"/static/{f}").status_code == 200
    assert "sessionStorage" in client.get("/static/admin.js").text
