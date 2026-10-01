from samantha_mirror.auth import COOKIE, MAX_FAILS
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


def test_lockout_uses_forwarded_client_only_from_the_proxy(cfg):
    """Behind `tailscale serve` every request comes from our own address, so X-Forwarded-For
    keeps one bad device from locking out the others."""
    from samantha_mirror.server import create_app
    c = create_app(cfg, "100.64.0.1").test_client()
    proxy = {"REMOTE_ADDR": "100.64.0.1"}
    for _ in range(MAX_FAILS):
        c.get("/api/state", headers={"X-Forwarded-For": "100.64.0.9"}, environ_overrides=proxy)
    assert c.get("/api/state", headers={"X-Forwarded-For": "100.64.0.9", **BEARER},
                 environ_overrides=proxy).status_code == 429
    assert c.get("/api/state", headers={"X-Forwarded-For": "100.64.0.8", **BEARER},
                 environ_overrides=proxy).status_code == 200
