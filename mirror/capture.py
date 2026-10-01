"""One shared capture thread. All viewers read the same encoded frame.

The thread only runs while at least one viewer is connected. Settings can be
changed while it runs (see FrameSource.configure).
"""
import ctypes
import io
import logging
import threading
import time
import zlib
from ctypes import wintypes

import mss
from PIL import Image, ImageDraw

log = logging.getLogger("screen-mirror")

RETRY_DELAY = 1.0  # seconds to wait after a capture error before trying again


def _cursor_pos():
    """Cursor position in physical pixels (we are DPI-aware), or None."""
    try:
        pt = wintypes.POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
            return pt.x, pt.y
    except Exception:
        pass
    return None


class FrameSource:
    def __init__(self, monitor: int, fps: int, quality: int, scale: float, cursor: bool = True):
        self._cond = threading.Condition()
        self._settings = {"monitor": monitor, "fps": fps, "quality": quality, "scale": scale, "cursor": cursor}
        self._frame = b""
        self._seq = 0      # bumps only when the picture changed
        self._tick = 0     # bumps every capture loop; proves the thread is alive
        self._clients = 0
        self._thread = None
        self._error = ""
        self._size = (0, 0)  # size of the last encoded frame

    # -- settings ------------------------------------------------------------
    def settings(self) -> dict:
        with self._cond:
            return dict(self._settings)

    def configure(self, **changes) -> None:
        """Apply already-validated settings; takes effect on the next frame."""
        with self._cond:
            self._settings.update(changes)

    # -- viewer bookkeeping --------------------------------------------------
    def client_count(self) -> int:
        with self._cond:
            return self._clients

    def add_client(self) -> None:
        with self._cond:
            self._clients += 1
            if self._thread is None:
                self._frame = b""  # never show a frame left over from the last session
                self._error = ""
                self._thread = threading.Thread(target=self._run, name="capture", daemon=True)
                self._thread.start()

    def remove_client(self) -> None:
        with self._cond:
            self._clients -= 1

    def state(self) -> dict:
        with self._cond:
            return {
                "seq": self._seq, "tick": self._tick, "viewers": self._clients,
                "error": self._error, "width": self._size[0], "height": self._size[1],
            }

    def wait_frame(self, last_seq: int, timeout: float = 5.0):
        """Block until a frame newer than last_seq exists. Returns (seq, jpeg) or None."""
        with self._cond:
            self._cond.wait_for(lambda: self._frame and self._seq != last_seq, timeout)
            if not self._frame or self._seq == last_seq:
                return None
            return self._seq, self._frame

    # -- capture loop --------------------------------------------------------
    def _run(self) -> None:
        last_key = None
        while True:
            try:
                # mss handles are thread-bound on Windows, so create it here.
                with mss.MSS() as sct:
                    monitor = None
                    region = None
                    while True:
                        started = time.monotonic()
                        with self._cond:
                            # Decide to stop and clear _thread in one step, so a viewer
                            # arriving right now always starts a fresh thread.
                            if self._clients <= 0:
                                self._thread = None
                                return
                            s = dict(self._settings)
                        if s["monitor"] != monitor:
                            if s["monitor"] >= len(sct.monitors):
                                raise RuntimeError(f"Monitor {s['monitor']} does not exist")
                            monitor, region, last_key = s["monitor"], sct.monitors[s["monitor"]], None
                        shot = sct.grab(region)
                        raw = shot.bgra
                        # Skip encoding and sending when nothing on screen changed.
                        pos = _cursor_pos() if s["cursor"] else None
                        key = (zlib.crc32(raw), pos, s["scale"], s["quality"])
                        jpeg = None
                        if key != last_key:
                            last_key = key
                            jpeg, size = self._encode(shot.size, raw, s, region, pos)
                        with self._cond:
                            self._tick += 1
                            self._error = ""
                            if jpeg is not None:
                                self._frame, self._size = jpeg, size
                                self._seq += 1
                            self._cond.notify_all()
                        delay = 1.0 / s["fps"] - (time.monotonic() - started)
                        if delay > 0:
                            time.sleep(delay)
            except Exception as exc:  # e.g. locked screen, UAC prompt, display change
                log.warning("capture error: %s", exc)
                with self._cond:
                    self._error = str(exc) or exc.__class__.__name__
                    self._cond.notify_all()
                    if self._clients <= 0:
                        self._thread = None
                        return
                last_key = None
                time.sleep(RETRY_DELAY)

    @staticmethod
    def _encode(size, raw, s, region, cursor_pos):
        img = Image.frombytes("RGB", size, raw, "raw", "BGRX")
        scale = s["scale"]
        if scale < 1.0:
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.BILINEAR)
        if cursor_pos:
            x = (cursor_pos[0] - region["left"]) * scale
            y = (cursor_pos[1] - region["top"]) * scale
            if 0 <= x < img.width and 0 <= y < img.height:
                k = max(0.6, min(1.5, img.width / 1000)) * 12
                arrow = [(x, y), (x, y + 1.5 * k), (x + 0.4 * k, y + 1.15 * k), (x + 0.75 * k, y + 1.7 * k),
                         (x + 1.0 * k, y + 1.55 * k), (x + 0.65 * k, y + 1.0 * k), (x + 1.05 * k, y + 1.0 * k)]
                d = ImageDraw.Draw(img)
                d.polygon(arrow, fill=(255, 255, 255), outline=(0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=s["quality"])
        return buf.getvalue(), img.size
