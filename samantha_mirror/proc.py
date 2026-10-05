"""Run helper programs (tailscale, powershell, git) without ever flashing a console window.

The server runs with no window of its own. On Windows, a windowless program that starts a console
program makes Windows open a brand-new terminal for it, so every call would flash a terminal on
screen. Always start helpers through here.
"""
import subprocess
import sys


def hidden() -> dict:
    """Keyword arguments for subprocess.run / Popen that keep the child's window from appearing."""
    if sys.platform != "win32":
        return {}
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": info}


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **{**hidden(), **kwargs})


def start_detached(cmd: list[str]) -> subprocess.Popen:
    """Start a program that keeps running after this one exits, with no window."""
    kw = hidden()
    kw["creationflags"] |= subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(cmd, close_fds=True, **kw)
