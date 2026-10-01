import http.client
import json
import threading
import time

from waitress import create_server

from samantha_mirror import runner
from samantha_mirror.auth import COOKIE, MAX_FAILS
from samantha_mirror.server import create_app
from tests.conftest import TOKEN

BEARER = {"Authorization": f"Bearer {TOKEN}"}


def test_app_files_are_public_but_api_is_not(client):
    assert client.get("/").status_code in (200, 500)  # 500 only if the web app is not built
    assert client.get("/api/state").status_code == 401
    assert client.get("/stream").status_code == 401
    assert client.post("/api/settings", json={"fps": 10}).status_code == 401
    assert client.get("/api/screenshot").status_code == 401


def test_token_link_sets_cookie_and_redirects(client):
    resp = client.get(f"/?token={TOKEN}")
    assert resp.status_code == 302 and resp.headers["Location"] == "/"
    assert COOKIE in resp.headers["Set-Cookie"] and "HttpOnly" in resp.headers["Set-Cookie"]
    assert client.get("/api/state").status_code == 200  # cookie now works


def test_login_and_logout(client):
    assert client.post("/api/login", json={"token": "nope"}).status_code == 401
    assert client.post("/api/login", json={"token": TOKEN}).status_code == 200
    assert client.get("/api/state").status_code == 200
    client.post("/api/logout")
    assert client.get("/api/state").status_code == 401


def test_stale_cookie_does_not_block_a_fresh_link(client):
    client.set_cookie(COOKIE, "old-token-value", domain="localhost")
    assert client.get(f"/?token={TOKEN}").status_code == 302


def test_state_reports_version_and_settings(client):
    data = client.get("/api/state", headers=BEARER).get_json()
    assert data["settings"]["fps"] == 30 and data["version"]
    assert data["viewers"] == 0


def test_settings_validation(client):
    ok = client.post("/api/settings", json={"fps": 20, "scale": 0.5, "cursor": False}, headers=BEARER)
    assert ok.status_code == 200 and ok.get_json()["fps"] == 20
    for bad in ({"fps": 999}, {"fps": "fast"}, {"scale": 0}, {"cursor": "yes"}, {"monitor": -1}, {"nope": 1}, [1]):
        assert client.post("/api/settings", json=bad, headers=BEARER).status_code == 400, bad


def test_lockout_blocks_even_the_right_token(client):
    for _ in range(MAX_FAILS):
        client.get("/api/state")
    assert client.get("/api/state", headers=BEARER).status_code == 429


def _serve(cfg, **trust):
    """A real waitress server on a free port, set up the way runner.py does it."""
    server = create_server(create_app(cfg), listen="127.0.0.1:0", **trust)
    threading.Thread(target=server.run, daemon=True).start()
    time.sleep(0.2)
    return server


def _get(port, path, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path, headers=headers or {})
    resp = conn.getresponse()
    resp.read()
    conn.close()
    return resp.status


def test_behind_the_https_proxy_each_device_is_locked_out_separately(cfg):
    """Regression: waitress drops X-Forwarded-For unless the proxy is trusted, which made every
    HTTPS client look like 127.0.0.1, so one phone's bad tries locked out all phones."""
    server = _serve(cfg, **runner.PROXY_TRUST)
    port = server.effective_port
    try:
        for _ in range(MAX_FAILS):
            _get(port, "/api/state", {"X-Forwarded-For": "100.64.0.9"})
        assert _get(port, "/api/state", {"X-Forwarded-For": "100.64.0.9", **BEARER}) == 429
        assert _get(port, "/api/state", {"X-Forwarded-For": "100.64.0.8", **BEARER}) == 200
    finally:
        server.close()


def test_forwarded_headers_are_ignored_from_an_untrusted_source(cfg):
    """Someone who is not the local proxy cannot pick their own client address."""
    server = _serve(cfg, trusted_proxy="10.9.9.9", trusted_proxy_count=1,
                    trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto"})
    port = server.effective_port
    try:
        for i in range(MAX_FAILS):
            _get(port, "/api/state", {"X-Forwarded-For": f"100.64.0.{i}"})  # tries to look like many devices
        assert _get(port, "/api/state", {"X-Forwarded-For": "100.64.0.200", **BEARER}) == 429
    finally:
        server.close()


def test_cookie_is_secure_only_over_https(cfg):
    server = _serve(cfg, **runner.PROXY_TRUST)
    port = server.effective_port
    try:
        def login(headers):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("POST", "/api/login", body=json.dumps({"token": TOKEN}),
                         headers={"Content-Type": "application/json", **headers})
            resp = conn.getresponse()
            resp.read()
            cookie = resp.getheader("Set-Cookie", "")
            conn.close()
            return cookie

        assert "Secure" in login({"X-Forwarded-Proto": "https", "X-Forwarded-For": "100.64.0.5"})
        assert "Secure" not in login({"X-Forwarded-For": "100.64.0.5"})
    finally:
        server.close()
