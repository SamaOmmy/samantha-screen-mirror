"""The capture loop must hit the requested frame rate on a screen that changes every frame."""
import time

import pytest

from samantha_mirror import capture


class FakeGrabber:
    name = "fake"
    region = {"left": 0, "top": 0, "width": 4, "height": 4}

    def grab(self):
        return b"\0" * 64, (4, 4), True  # always a new picture

    def close(self):
        pass


@pytest.mark.parametrize("fps", [30, 60])
def test_delivers_the_requested_rate(monkeypatch, fps):
    monkeypatch.setattr(capture.FrameSource, "_open_grabber", lambda self, monitor: FakeGrabber())
    monkeypatch.setattr(capture.FrameSource, "_encode", staticmethod(lambda *a: (b"jpeg", (4, 4))))
    src = capture.FrameSource(1, fps, 70, 0.75, cursor=False)
    src.add_client()
    time.sleep(0.5)
    first, t0 = src.state()["seq"], time.perf_counter()
    time.sleep(2.0)
    rate = (src.state()["seq"] - first) / (time.perf_counter() - t0)
    src.remove_client()
    time.sleep(0.2)
    assert fps * 0.85 <= rate <= fps * 1.1, f"asked for {fps} fps, got {rate:.1f}"
