"""One shared capture thread. All viewers read the same encoded frame.

The thread only runs while at least one viewer is connected. Settings can be
changed while it runs (see FrameSource.configure).

Screen grabbing uses DXGI Desktop Duplication (via dxcam) when available: it is
several times faster than mss's GDI capture and reports whether the screen changed.
mss remains as the fallback.
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

try:  # optional: several times faster than Pillow at resizing and encoding
    import cv2
    import numpy as np
except ImportError:
    cv2 = None

log = logging.getLogger("screen-mirror")

RETRY_DELAY = 1.0   # seconds to wait after a capture error before trying again
IDLE_POLL = 0.002   # seconds between checks while the screen isn't changing
DX_FAIL_LIMIT = 3   # runtime DXGI failures in a row before we stick to mss


def _cursor_pos():
    """Cursor position in physical pixels (we are DPI-aware), or None."""
    try:
        pt = wintypes.POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
            return pt.x, pt.y
    except Exception:
        pass
    return None


# -- grabbers: grab() -> (BGRA buffer, (width, height), changed) --------------------------
class _MssGrabber:
    name = "mss"

    def __init__(self, monitor: int):
        self._sct = mss.MSS()  # mss handles are thread-bound on Windows: create in the capture thread
        if monitor >= len(self._sct.monitors):
            self._sct.close()
            raise RuntimeError(f"Monitor {monitor} does not exist")
        self.region = self._sct.monitors[monitor]
        self._crc = None

    def grab(self):
        shot = self._sct.grab(self.region)
        raw = shot.bgra
        crc = zlib.crc32(raw)
        changed, self._crc = crc != self._crc, crc
        return raw, shot.size, changed

    def close(self):
        self._sct.close()


class _DxGrabber:
    name = "dxgi"

    def __init__(self, monitor: int):
        import dxcam  # optional dependency
        if monitor < 1:
            raise RuntimeError("DXGI capture can't combine monitors")
        with mss.MSS() as sct:
            if monitor >= len(sct.monitors):
                raise RuntimeError(f"Monitor {monitor} does not exist")
            self.region = sct.monitors[monitor]
        self._cam = dxcam.create(output_idx=monitor - 1, output_color="BGRA")
        if (self._cam.width, self._cam.height) != (self.region["width"], self.region["height"]):
            self._cam.release()
            raise RuntimeError("DXGI output doesn't match the selected monitor")
        self._last = None
        # The first grab returns the current picture; wait briefly for it.
        deadline = time.monotonic() + 1.5
        while self._last is None:
            self._last = self._cam.grab()
            if self._last is None:
                if time.monotonic() > deadline:
                    self._cam.release()
                    raise RuntimeError("DXGI produced no frame")
                time.sleep(0.01)
        self._first = True

    def grab(self):
        frame = self._cam.grab()  # None = nothing changed since the last call
        changed = frame is not None or self._first
        self._first = False
        if frame is not None:
            self._last = frame
        h, w = self._last.shape[:2]
        return self._last, (w, h), changed

    def close(self):
        self._cam.release()


class FrameSource:
    def __init__(self, monitor: int, fps: int, quality: int, scale: float, cursor: bool = True,
                 backend: str = "auto"):
        self._cond = threading.Condition()
        self._settings = {"monitor": monitor, "fps": fps, "quality": quality, "scale": scale, "cursor": cursor}
        self._backend = backend  # auto | dxgi | mss
        self._frame = b""
        self._seq = 0      # bumps only when the picture changed
        self._tick = 0     # bumps every capture loop; proves the thread is alive
        self._clients = 0
        self._thread = None
        self._error = ""
        self._size = (0, 0)  # size of the last encoded frame
        self._grabber_name = ""

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
                "capture": self._grabber_name,
            }

    def wait_frame(self, last_seq: int, timeout: float = 5.0):
        """Block until a frame newer than last_seq exists. Returns (seq, jpeg) or None."""
        with self._cond:
            self._cond.wait_for(lambda: self._frame and self._seq != last_seq, timeout)
            if not self._frame or self._seq == last_seq:
                return None
            return self._seq, self._frame

    # -- capture loop --------------------------------------------------------
    def _open_grabber(self, monitor: int):
        if self._backend != "mss" and not self._dx_disabled:
            try:
                return _DxGrabber(monitor)
            except Exception as exc:
                if self._backend == "dxgi":
                    raise
                log.info("DXGI capture unavailable (%s); using mss", exc)
        return _MssGrabber(monitor)

    def _run(self) -> None:
        self._dx_disabled = False
        dx_failures = 0
        grabber = None
        monitor = None
        last_key = None
        frame_id = 0
        last_sent = 0.0
        try:
            while True:
                try:
                    with self._cond:
                        # Decide to stop and clear _thread in one step, so a viewer
                        # arriving right now always starts a fresh thread.
                        if self._clients <= 0:
                            self._thread = None
                            return
                        s = dict(self._settings)
                    if grabber is None or s["monitor"] != monitor:
                        if grabber:
                            grabber.close()
                            grabber = None
                        grabber = self._open_grabber(s["monitor"])
                        monitor, last_key = s["monitor"], None
                        log.info("capture: monitor %s via %s", monitor, grabber.name)
                        with self._cond:
                            self._grabber_name = grabber.name

                    # Hold the fps cap by waiting *before* grabbing, so the picture we send
                    # is as fresh as possible, then poll quickly while nothing changes.
                    wait = last_sent + 1.0 / s["fps"] - time.monotonic()
                    if wait > 0:
                        time.sleep(wait)
                    grabbed_at = time.monotonic()
                    buf, size, changed = grabber.grab()
                    dx_failures = 0
                    frame_id += changed
                    # Skip encoding and sending when nothing on screen changed.
                    pos = _cursor_pos() if s["cursor"] else None
                    key = (frame_id, pos, s["scale"], s["quality"])
                    jpeg = None
                    if key != last_key:
                        last_key = key
                        jpeg, out_size = self._encode(size, buf, s, grabber.region, pos)
                    with self._cond:
                        self._tick += 1
                        self._error = ""
                        if jpeg is not None:
                            self._frame, self._size = jpeg, out_size
                            self._seq += 1
                        self._cond.notify_all()
                    if jpeg is not None:
                        last_sent = grabbed_at  # pace from the grab, so encode time doesn't add to the interval
                    else:
                        time.sleep(IDLE_POLL)
                except Exception as exc:  # e.g. locked screen, UAC prompt, display change
                    log.warning("capture error: %s", exc)
                    if grabber is not None:
                        if grabber.name == "dxgi" and self._backend == "auto":
                            dx_failures += 1
                            if dx_failures >= DX_FAIL_LIMIT:
                                log.warning("DXGI keeps failing; switching to mss")
                                self._dx_disabled = True
                        try:
                            grabber.close()
                        except Exception:
                            pass
                        grabber = None
                    with self._cond:
                        self._error = str(exc) or exc.__class__.__name__
                        self._cond.notify_all()
                        if self._clients <= 0:
                            self._thread = None
                            return
                    time.sleep(RETRY_DELAY)
        finally:
            if grabber is not None:
                try:
                    grabber.close()
                except Exception:
                    pass

    @staticmethod
    def _arrow(x, y, width):
        k = max(0.6, min(1.5, width / 1000)) * 12
        return [(x, y), (x, y + 1.5 * k), (x + 0.4 * k, y + 1.15 * k), (x + 0.75 * k, y + 1.7 * k),
                (x + 1.0 * k, y + 1.55 * k), (x + 0.65 * k, y + 1.0 * k), (x + 1.05 * k, y + 1.0 * k)]

    @classmethod
    def _encode(cls, size, buf, s, region, cursor_pos):
        if cv2 is not None:
            return cls._encode_cv2(size, buf, s, region, cursor_pos)
        return cls._encode_pil(size, buf, s, region, cursor_pos)

    @classmethod
    def _encode_cv2(cls, size, buf, s, region, cursor_pos):
        scale = s["scale"]
        img = np.frombuffer(buf, dtype=np.uint8).reshape(size[1], size[0], 4) if isinstance(buf, (bytes, bytearray)) else buf
        if scale < 1.0:
            target = (max(1, int(size[0] * scale)), max(1, int(size[1] * scale)))
            # AREA keeps text crisp when shrinking a lot; LINEAR is cheaper for mild shrinking.
            img = cv2.resize(img, target, interpolation=cv2.INTER_AREA if scale <= 0.6 else cv2.INTER_LINEAR)
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)  # also gives a writable copy
        h, w = img.shape[:2]
        if cursor_pos:
            x = (cursor_pos[0] - region["left"]) * scale
            y = (cursor_pos[1] - region["top"]) * scale
            if 0 <= x < w and 0 <= y < h:
                pts = np.array(cls._arrow(x, y, w), dtype=np.float32).round().astype(np.int32)
                cv2.fillPoly(img, [pts], (255, 255, 255), cv2.LINE_AA)
                cv2.polylines(img, [pts], True, (0, 0, 0), 1, cv2.LINE_AA)
        ok, out = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, s["quality"]])
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        return out.tobytes(), (w, h)

    @classmethod
    def _encode_pil(cls, size, buf, s, region, cursor_pos):
        img = Image.frombuffer("RGB", size, buf, "raw", "BGRX", 0, 1)
        scale = s["scale"]
        if scale < 1.0:
            target = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
            factor = int(1 / scale)
            if factor >= 2:
                img = img.reduce(factor)  # box filter: fast, and sharp for text
            if img.size != target:
                img = img.resize(target, Image.BILINEAR)
        if cursor_pos:
            x = (cursor_pos[0] - region["left"]) * scale
            y = (cursor_pos[1] - region["top"]) * scale
            if 0 <= x < img.width and 0 <= y < img.height:
                ImageDraw.Draw(img).polygon(cls._arrow(x, y, img.width), fill=(255, 255, 255), outline=(0, 0, 0))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=s["quality"])
        return out.getvalue(), img.size
