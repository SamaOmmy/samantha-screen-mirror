"""Start the server: bind to the Tailscale address, log, and serve.

It is meant to run unattended from logon to logoff, so it keeps itself working:
  - at boot Tailscale can know its address before Windows has attached it to the network
    adapter (WinError 10049): keep retrying instead of giving up;
  - if the listener ever stops answering (Tailscale restarted or updated, adapter reset),
    a watchdog tears it down and builds a fresh one.
"""
import ctypes
import errno
import logging
import logging.handlers
import socket
import sys
import threading
import time

import mss
from waitress import create_server

from . import config, tailscale, updater
from .server import create_app

TAILSCALE_WAIT = 120       # seconds; at logon Tailscale may still be starting
BIND_RETRY_SECONDS = 600   # how long to keep retrying while the address is not usable yet
WATCHDOG_INTERVAL = 20     # seconds between self-checks
WATCHDOG_FAILS = 3         # consecutive failed self-checks before the listener is rebuilt

# `tailscale serve` (HTTPS) connects from this machine. Trust only it for X-Forwarded-*, so the real
# client address and https scheme reach the app, and nobody else can fake them.
PROXY_TRUST = {
    "trusted_proxy": "127.0.0.1",
    "trusted_proxy_count": 1,
    "trusted_proxy_headers": {"x-forwarded-for", "x-forwarded-proto"},
}

log = logging.getLogger("samantha-mirror")


def _setup_logging() -> None:
    handlers = [logging.handlers.RotatingFileHandler(
        config.log_path(), maxBytes=500_000, backupCount=1, encoding="utf-8")]
    if sys.stderr is not None:  # None under pythonw
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", handlers=handlers)
    logging.getLogger("waitress").setLevel(logging.WARNING)


def _dpi_aware() -> None:
    # Without this, scaled displays on Windows are captured at the wrong size.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def _wait_for_tailscale() -> str:
    deadline = time.monotonic() + TAILSCALE_WAIT
    while True:
        try:
            return tailscale.tailscale_ip()
        except tailscale.BindError as exc:
            if time.monotonic() >= deadline:
                raise
            log.warning("%s Retrying...", exc)
            time.sleep(5)


def address_not_ready(exc: OSError) -> bool:
    """True for 'that address is not (yet) assigned to this machine': worth waiting for."""
    return getattr(exc, "winerror", None) == 10049 or exc.errno == errno.EADDRNOTAVAIL


def _watchdog(ip: str, port: int, server, stop: threading.Event, tripped: threading.Event) -> None:
    fails = 0
    while not stop.wait(WATCHDOG_INTERVAL):
        try:
            socket.create_connection((ip, port), timeout=3).close()
            fails = 0
        except OSError as exc:
            fails += 1
            log.warning("self-check %s/%s failed: %s", fails, WATCHDOG_FAILS, exc)
            if fails >= WATCHDOG_FAILS:
                log.warning("listener is not answering; rebuilding it")
                tripped.set()
                server.close()  # makes server.run() return
                return


def serve_forever(cfg: config.Config) -> int:
    deadline = time.monotonic() + BIND_RETRY_SECONDS
    announced = False
    while True:
        try:
            ip = _wait_for_tailscale()  # re-read each round: the address can change
        except tailscale.BindError as exc:
            log.error("%s", exc)
            return 1
        listen = f"{ip}:{cfg.port}" + (f" 127.0.0.1:{cfg.port}" if cfg.loopback else "")
        try:
            # send_bytes=1 so each JPEG frame is flushed immediately instead of buffered.
            server = create_server(create_app(cfg), listen=listen, threads=cfg.max_clients + 4,
                                   send_bytes=1, ident="samantha-mirror", **PROXY_TRUST)
        except OSError as exc:
            if address_not_ready(exc) and time.monotonic() < deadline:
                log.warning("Address %s is not usable yet (%s). Retrying...", ip, exc)
                time.sleep(5)
                continue
            log.error("Could not listen on %s (%s). Is it already running? Close it or change SM_PORT.",
                      listen, exc)
            return 1

        log.info("Listening ONLY on %s", listen.replace(" ", " and "))
        # The token is printed to the console only, never written to the log file.
        if sys.stdout is not None and not announced:
            print(f"Open on your phone: http://{ip}:{cfg.port}/?token={cfg.token}")
            print("(Run `samantha-mirror link` for a QR code and the HTTPS address.)  Press Ctrl+C to stop.")
        announced = True

        stop, tripped = threading.Event(), threading.Event()
        threading.Thread(target=_watchdog, args=(ip, cfg.port, server, stop, tripped),
                         name="watchdog", daemon=True).start()
        try:
            server.run()
        except KeyboardInterrupt:
            return 0
        finally:
            stop.set()
            server.close()
        if not tripped.is_set():
            return 0
        deadline = time.monotonic() + BIND_RETRY_SECONDS  # fresh patience for the rebuild
        time.sleep(2)


def run_server() -> int:
    _setup_logging()
    _dpi_aware()
    try:
        cfg = config.load()
    except config.ConfigError as exc:
        log.error("%s", exc)
        return 1

    with mss.MSS() as sct:
        monitors = sct.monitors
    if cfg.monitor >= len(monitors):
        log.error("SM_MONITOR=%s but only monitors 0-%s exist.", cfg.monitor, len(monitors) - 1)
        return 1
    m = monitors[cfg.monitor]
    log.info("Mirroring monitor %s (%sx%s) at %s fps, quality %s, scale %s",
             cfg.monitor, m["width"], m["height"], cfg.fps, cfg.jpeg_quality, cfg.scale)
    if cfg.update_check:
        updater.start_background_check()
    return serve_forever(cfg)
