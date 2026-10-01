"""Entry point: python run.py   (or pythonw run.py to run with no console window)"""
import ctypes
import logging
import logging.handlers
import sys
import time

import mss
from waitress import serve

from mirror import config, netbind
from mirror.server import create_app

TAILSCALE_WAIT = 120  # seconds; at logon Tailscale may still be starting

log = logging.getLogger("screen-mirror")


def _setup_logging() -> None:
    handlers = [logging.handlers.RotatingFileHandler(
        config.ROOT / "screen-mirror.log", maxBytes=500_000, backupCount=1, encoding="utf-8")]
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
            return netbind.tailscale_ip()
        except netbind.BindError as exc:
            if time.monotonic() >= deadline:
                raise
            log.warning("%s Retrying...", exc)
            time.sleep(5)


def main() -> int:
    _setup_logging()
    _dpi_aware()
    try:
        cfg = config.load()
        ip = _wait_for_tailscale()
    except (config.ConfigError, netbind.BindError) as exc:
        log.error("%s", exc)
        return 1

    with mss.MSS() as sct:
        monitors = sct.monitors
    if cfg.monitor >= len(monitors):
        log.error("SM_MONITOR=%s but only monitors 0-%s exist.", cfg.monitor, len(monitors) - 1)
        return 1
    m = monitors[cfg.monitor]

    app = create_app(cfg, ip)
    log.info("Mirroring monitor %s (%sx%s) at %s fps, quality %s, scale %s",
             cfg.monitor, m["width"], m["height"], cfg.fps, cfg.jpeg_quality, cfg.scale)
    listen = f"{ip}:{cfg.port}" + (f" 127.0.0.1:{cfg.port}" if cfg.loopback else "")
    log.info("Listening ONLY on %s", listen.replace(" ", " and "))
    # The token is printed to the console only, never written to the log file.
    if sys.stdout is not None:
        print(f"Open on your phone: http://{ip}:{cfg.port}/?token={cfg.token}")
        print("Press Ctrl+C to stop.")
    try:
        # send_bytes=1 so each JPEG frame is flushed immediately instead of buffered.
        serve(app, listen=listen, threads=cfg.max_clients + 4, send_bytes=1, ident="screen-mirror")
    except OSError as exc:
        log.error("Could not listen on %s (%s). Is screen-mirror already running? "
                  "Close it or change SM_PORT.", listen, exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
