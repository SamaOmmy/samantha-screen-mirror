"""One shared capture thread. All viewers read the same encoded frame.

The thread only runs while at least one viewer is connected.
"""
import io
import threading
import time

import mss
from PIL import Image


class FrameSource:
    def __init__(self, monitor: int, fps: int, quality: int, scale: float):
        self.monitor = monitor
        self.interval = 1.0 / fps
        self.quality = quality
        self.scale = scale

        self._cond = threading.Condition()
        self._frame = b""
        self._seq = 0
        self._clients = 0
        self._thread = None

    # -- viewer bookkeeping -------------------------------------------------
    def client_count(self) -> int:
        with self._cond:
            return self._clients

    def add_client(self) -> None:
        with self._cond:
            self._clients += 1
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="capture", daemon=True)
                self._thread.start()

    def remove_client(self) -> None:
        with self._cond:
            self._clients -= 1

    @property
    def seq(self) -> int:
        with self._cond:
            return self._seq

    def wait_frame(self, last_seq: int, timeout: float = 5.0):
        """Block until a frame newer than last_seq exists. Returns (seq, jpeg) or None."""
        with self._cond:
            self._cond.wait_for(lambda: self._seq != last_seq, timeout)
            if self._seq == last_seq:
                return None
            return self._seq, self._frame

    # -- capture loop -------------------------------------------------------
    def _run(self) -> None:
        try:
            # mss handles are thread-bound on Windows, so create it here.
            with mss.MSS() as sct:
                if self.monitor >= len(sct.monitors):
                    raise RuntimeError(f"Monitor {self.monitor} does not exist")
                region = sct.monitors[self.monitor]
                while True:
                    started = time.monotonic()
                    with self._cond:
                        if self._clients <= 0:
                            return
                    jpeg = self._encode(sct.grab(region))
                    with self._cond:
                        self._frame = jpeg
                        self._seq += 1
                        self._cond.notify_all()
                    delay = self.interval - (time.monotonic() - started)
                    if delay > 0:
                        time.sleep(delay)
        finally:
            with self._cond:
                self._thread = None
                self._cond.notify_all()

    def _encode(self, shot) -> bytes:
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        if self.scale < 1.0:
            size = (max(1, int(img.width * self.scale)), max(1, int(img.height * self.scale)))
            img = img.resize(size, Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=self.quality)
        return buf.getvalue()
