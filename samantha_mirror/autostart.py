"""Start the server hidden at every Windows logon, via Task Scheduler (no admin needed).

The task has to run as you, in your desktop session: that is the screen being captured.
"""
import subprocess
import sys
from pathlib import Path

TASK = "SamanthaScreenMirror"
LEGACY_TASKS = ("screen-mirror",)  # names used by earlier versions


def _ps(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=60)


def _command() -> tuple[str, str]:
    """(program, arguments) that start the server with no console window."""
    exe = Path(sys.executable)
    if getattr(sys, "frozen", False):  # packaged .exe: a windowless twin sits next to us
        service = exe.with_name("samantha-mirror-service.exe")
        return str(service if service.exists() else exe), "run"
    pythonw = exe.with_name("pythonw.exe")
    return str(pythonw if pythonw.exists() else exe), "-m samantha_mirror run"


def status() -> str:
    """'running', 'ready' (installed, not running) or 'missing'."""
    out = _ps(f"(Get-ScheduledTask -TaskName '{TASK}' -ErrorAction SilentlyContinue).State")
    state = out.stdout.strip().lower()
    return state if state in ("running", "ready") else ("ready" if state else "missing")


def install(start_now: bool = True) -> None:
    remove_legacy()
    program, arguments = _command()
    script = f"""
$a = New-ScheduledTaskAction -Execute '{program}' -Argument '{arguments}'
$t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
       -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName '{TASK}' -Action $a -Trigger $t -Settings $s -Force `
  -Description 'Mirror this PC screen to your phone over Tailscale' | Out-Null
"""
    if start_now:
        script += f"Start-ScheduledTask -TaskName '{TASK}'\n"
    out = _ps(script)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout).strip() or "could not register the task")


def remove() -> None:
    _ps(f"Stop-ScheduledTask -TaskName '{TASK}' -ErrorAction SilentlyContinue; "
        f"Unregister-ScheduledTask -TaskName '{TASK}' -Confirm:$false -ErrorAction SilentlyContinue")
    remove_legacy()


def remove_legacy() -> None:
    for name in LEGACY_TASKS:
        _ps(f"Stop-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue; "
            f"Unregister-ScheduledTask -TaskName '{name}' -Confirm:$false -ErrorAction SilentlyContinue")
