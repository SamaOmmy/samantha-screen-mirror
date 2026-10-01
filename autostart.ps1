<#
  Start screen-mirror automatically when you log in to Windows (no console window),
  so the phone app can connect any time without you running a command.

    .\autostart.ps1 install     register the logon task and start it now
    .\autostart.ps1 remove      stop and remove the task
    .\autostart.ps1 status      show whether it is registered / running

  No administrator rights needed: the task runs as you, in your desktop session
  (required, because that is the session whose screen gets captured).
  Logs go to screen-mirror.log in this folder.
#>
param([Parameter(Position = 0)][ValidateSet("install", "remove", "status")][string]$Action = "status")

$task = "screen-mirror"
$root = $PSScriptRoot
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"

switch ($Action) {
  "install" {
    if (-not (Test-Path $pythonw)) { throw "Missing $pythonw. Do the venv setup from the README first." }
    if (-not (Test-Path (Join-Path $root ".env"))) { throw "Missing .env. Create it from .env.example first." }
    $a = New-ScheduledTaskAction -Execute $pythonw -Argument "run.py" -WorkingDirectory $root
    $t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
           -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $task -Action $a -Trigger $t -Settings $s -Force `
      -Description "Mirror this PC's screen to your phone over Tailscale" | Out-Null
    Start-ScheduledTask -TaskName $task
    Write-Host "Installed and started. It will also start at every logon."
  }
  "remove" {
    Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed."
  }
  "status" {
    $info = Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
    if ($info) { Write-Host "Registered, state: $($info.State)" } else { Write-Host "Not installed." }
  }
}
