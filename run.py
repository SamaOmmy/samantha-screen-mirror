"""Entry point: python run.py"""
import ctypes
import sys

import mss
from waitress import serve

from mirror import config, netbind
from mirror.server import create_app


def _dpi_aware() -> None:
    # Without this, scaled displays on Windows are captured at the wrong size.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def main() -> int:
    _dpi_aware()
    try:
        cfg = config.load()
        ip = netbind.tailscale_ip()
    except (config.ConfigError, netbind.BindError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    with mss.MSS() as sct:
        monitors = sct.monitors
    if cfg.monitor >= len(monitors):
        print(f"ERROR: SM_MONITOR={cfg.monitor} but only monitors 0-{len(monitors) - 1} exist.", file=sys.stderr)
        return 1
    m = monitors[cfg.monitor]

    app = create_app(cfg)
    print(f"Mirroring monitor {cfg.monitor} ({m['width']}x{m['height']}) "
          f"at {cfg.fps} fps, quality {cfg.jpeg_quality}, scale {cfg.scale}")
    print(f"Listening ONLY on {ip}:{cfg.port}")
    print(f"Open on your phone: http://{ip}:{cfg.port}/?token={cfg.token}")
    print("Press Ctrl+C to stop.")
    # send_bytes=1 so each JPEG frame is flushed immediately instead of buffered.
    serve(app, host=ip, port=cfg.port, threads=cfg.max_clients + 3, send_bytes=1, ident="screen-mirror")
    return 0


if __name__ == "__main__":
    sys.exit(main())
