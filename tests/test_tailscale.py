import json
import subprocess

import pytest

from samantha_mirror import tailscale


def fake_run(outputs):
    def run(*args, timeout=15):
        return subprocess.CompletedProcess(args, 0, stdout=outputs.get(" ".join(args), ""), stderr="")
    return run


@pytest.mark.parametrize("out,ok", [
    ("100.101.102.103\n", True),
    ("192.168.1.5\n", False),   # a LAN address must never be bound
    ("8.8.8.8\n", False),
    ("", False),
    ("garbage", False),
])
def test_tailscale_ip_only_accepts_the_tailscale_range(monkeypatch, out, ok):
    monkeypatch.setattr(tailscale, "run", fake_run({"ip -4": out}))
    if ok:
        assert tailscale.tailscale_ip() == out.strip()
    else:
        with pytest.raises(tailscale.BindError):
            tailscale.tailscale_ip()


SERVE = json.dumps({"Web": {
    "pc.tail1234.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8787"}}},
    "pc.tail1234.ts.net:8443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:9999"}}},
}})
ST = {"Self": {"DNSName": "pc.tail1234.ts.net."}, "CertDomains": ["pc.tail1234.ts.net"], "BackendState": "Running"}


def test_https_url_and_serve_map(monkeypatch):
    monkeypatch.setattr(tailscale, "run", fake_run({"serve status --json": SERVE}))
    assert tailscale.serve_map() == {443: "http://127.0.0.1:8787", 8443: "http://127.0.0.1:9999"}
    assert tailscale.https_url(ST, 8787) == "https://pc.tail1234.ts.net/"
    assert tailscale.https_url(ST, 9999) == "https://pc.tail1234.ts.net:8443/"
    assert tailscale.https_url(ST, 1234) is None


def test_enable_https_never_takes_another_apps_port(monkeypatch):
    calls = []

    def run(*args, timeout=15):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(tailscale, "run", run)
    # 443 and 8443 belong to other apps: ours must land on 10000
    monkeypatch.setattr(tailscale, "serve_map", lambda: {443: "http://127.0.0.1:1", 8443: "http://127.0.0.1:2"})
    assert tailscale.enable_https(ST, 5555) == "https://pc.tail1234.ts.net:10000/"
    assert ("serve", "--bg", "--https=10000", "http://127.0.0.1:5555") in calls
