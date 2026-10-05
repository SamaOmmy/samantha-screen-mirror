"""Start the server hidden at every Windows logon, via Task Scheduler (no admin needed).

The task has to run as you, in your desktop session: that is the screen being captured.
"""
import sys
from pathlib import Path
from subprocess import CompletedProcess

from . import proc

TASK = "SamanthaScreenMirror"
LEGACY_TASKS = ("screen-mirror",)  # names used by earlier versions


def _ps(script: str) -> CompletedProcess:
    return proc.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
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
    """'running', 'ready' (installed, not running), 'disabled' (stopped on purpose) or 'missing'."""
    out = _ps(f"(Get-ScheduledTask -TaskName '{TASK}' -ErrorAction SilentlyContinue).State")
    state = out.stdout.strip().lower()
    return state if state in ("running", "ready", "disabled") else ("ready" if state else "missing")


def install(start_now: bool = True) -> None:
    remove_legacy()
    program, arguments = _command()
    script = f"""
$a = New-ScheduledTaskAction -Execute '{program}' -Argument '{arguments}'
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
# A separate time-based trigger (a repeat attached to the logon trigger only begins after the next logon):
# every 5 minutes, start the server if it is not running. MultipleInstances IgnoreNew makes it a no-op otherwise.
# (No separate RestartCount: this trigger is the retry, and a crash loop would otherwise start extra copies.)
$repeat = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) `
            -RepetitionDuration (New-TimeSpan -Days 3650)
$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
       -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName '{TASK}' -Action $a -Trigger @($logon, $repeat) -Settings $s -Force `
  -Description 'Mirror this PC screen to your phone over Tailscale' | Out-Null
"""
    if start_now:
        script += f"Start-ScheduledTask -TaskName '{TASK}'\n"
    out = _ps(script)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout).strip() or "could not register the task")


def pause() -> None:
    """Stop the server now and keep it stopped (no restart at logon or every 5 minutes) until resume()."""
    _ps(f"Disable-ScheduledTask -TaskName '{TASK}' -ErrorAction SilentlyContinue | Out-Null; "
        f"Stop-ScheduledTask -TaskName '{TASK}' -ErrorAction SilentlyContinue; "
        # also a copy started by hand (`samantha-mirror run`, or the hidden pythonw one). Match narrowly:
        # other programs on this PC may have "samantha" in their path too.
        "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'samantha-mirror-service.exe' -or "
        "($_.CommandLine -like '*-m samantha_mirror run*') -or "
        "($_.CommandLine -like '*samantha-mirror.exe* run*') } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")


def resume() -> None:
    out = _ps(f"Enable-ScheduledTask -TaskName '{TASK}' | Out-Null; Start-ScheduledTask -TaskName '{TASK}'")
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout).strip() or "could not start the task")


def remove() -> None:
    _ps(f"Stop-ScheduledTask -TaskName '{TASK}' -ErrorAction SilentlyContinue; "
        f"Unregister-ScheduledTask -TaskName '{TASK}' -Confirm:$false -ErrorAction SilentlyContinue")
    remove_legacy()


def remove_legacy() -> None:
    for name in LEGACY_TASKS:
        _ps(f"Stop-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue; "
            f"Unregister-ScheduledTask -TaskName '{name}' -Confirm:$false -ErrorAction SilentlyContinue")
