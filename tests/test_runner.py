import errno
import threading
import time

import pytest

from samantha_mirror import runner


class DummyServer:
    def __init__(self):
        self.closed = False

    def run(self):
        return

    def close(self):
        self.closed = True


@pytest.fixture
def fast(monkeypatch, cfg):
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    monkeypatch.setattr(runner, "_wait_for_tailscale", lambda: "100.64.0.1")
    monkeypatch.setattr(runner, "create_app", lambda cfg: object())
    return cfg


def test_address_not_ready_is_recognised():
    assert runner.address_not_ready(OSError(errno.EADDRNOTAVAIL, "not valid in its context"))
    assert not runner.address_not_ready(OSError(errno.EADDRINUSE, "in use"))


def test_keeps_retrying_while_the_address_is_not_ready(fast, monkeypatch):
    """The boot-time bug: Tailscale knows its address before Windows has attached it (WinError 10049)."""
    calls = []

    def create(app, **kw):
        calls.append(kw["listen"])
        if len(calls) < 4:
            raise OSError(errno.EADDRNOTAVAIL, "The requested address is not valid in its context")
        return DummyServer()

    monkeypatch.setattr(runner, "create_server", create)
    assert runner.serve_forever(fast) == 0
    assert len(calls) == 4


def test_gives_up_when_the_address_never_becomes_usable(fast, monkeypatch):
    monkeypatch.setattr(runner, "BIND_RETRY_SECONDS", -1)
    monkeypatch.setattr(runner, "create_server",
                        lambda app, **kw: (_ for _ in ()).throw(OSError(errno.EADDRNOTAVAIL, "nope")))
    assert runner.serve_forever(fast) == 1


def test_other_bind_errors_are_not_retried(fast, monkeypatch):
    calls = []

    def create(app, **kw):
        calls.append(1)
        raise OSError(errno.EADDRINUSE, "port already in use")

    monkeypatch.setattr(runner, "create_server", create)
    assert runner.serve_forever(fast) == 1
    assert len(calls) == 1


def test_watchdog_rebuilds_a_listener_that_stops_answering(monkeypatch):
    monkeypatch.setattr(runner, "WATCHDOG_INTERVAL", 0.01)
    monkeypatch.setattr(runner, "WATCHDOG_FAILS", 2)
    server, stop, tripped = DummyServer(), threading.Event(), threading.Event()
    # Nothing listens on this port, so every self-check fails.
    runner._watchdog("127.0.0.1", 9, server, stop, tripped)
    assert tripped.is_set() and server.closed


def test_closing_a_real_waitress_server_stops_run(cfg):
    """The watchdog relies on server.close() making server.run() return."""
    from waitress import create_server

    server = create_server(lambda environ, start: (start("200 OK", []), [b"ok"])[1], listen="127.0.0.1:0")
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(0.3)
    server.close()
    thread.join(timeout=10)
    assert not thread.is_alive()
