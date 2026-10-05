"""Helper programs must never flash a console window (the server has no window of its own)."""
import subprocess
import sys

import pytest

from samantha_mirror import autostart, proc, tailscale

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows console windows")


def test_hidden_flags_ask_for_no_window():
    kw = proc.hidden()
    assert kw["creationflags"] & subprocess.CREATE_NO_WINDOW
    assert kw["startupinfo"].wShowWindow == subprocess.SW_HIDE


def _capture(monkeypatch):
    seen = []

    def fake_run(cmd, **kw):
        seen.append(kw)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return seen


def test_tailscale_calls_are_hidden(monkeypatch):
    seen = _capture(monkeypatch)
    monkeypatch.setattr(tailscale, "find_cli", lambda: "tailscale.exe")
    tailscale.run("ip", "-4")
    assert seen[0]["creationflags"] & subprocess.CREATE_NO_WINDOW


def test_powershell_calls_are_hidden(monkeypatch):
    seen = _capture(monkeypatch)
    autostart.status()
    assert seen[0]["creationflags"] & subprocess.CREATE_NO_WINDOW


def test_no_bare_subprocess_run_in_the_package():
    """Guard: every helper launch has to go through proc.run (wizard's visible winget install is the one exception)."""
    import pathlib
    import re

    root = pathlib.Path(proc.__file__).parent
    for path in root.glob("*.py"):
        if path.name in ("proc.py", "wizard.py"):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            assert not re.search(r"subprocess\.(run|Popen|call|check_output)\(", line) or "proc.hidden()" in line \
                or "startupinfo" in line, f"{path.name}: {line.strip()}"
