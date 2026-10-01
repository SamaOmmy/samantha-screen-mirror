<#
  One-step installer for Samantha Screen Mirror (Windows).

  From the project folder, in PowerShell:
      .\install.ps1          (add -Yes to accept every default without asking)

  It finds (or installs) Python, creates a private virtual environment in .venv,
  installs the app, then starts the guided setup (Tailscale, token, HTTPS, autostart, phone QR code).
  No administrator rights needed. Safe to run again.
#>
param([switch]$Yes)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Find-Python {
  foreach ($cmd in @(@("py", "-3"), @("python"))) {
    try {
      $exe = $cmd[0]; $extra = $cmd[1..($cmd.Length - 1)]
      $v = & $exe @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
      if ($LASTEXITCODE -eq 0 -and [version]$v -ge [version]"3.10") { return ,@($exe) + $extra }
    } catch { }
  }
  return $null
}

$py = Find-Python
if (-not $py) {
  Write-Host "Python 3.10 or newer was not found."
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    $answer = Read-Host "Install Python 3.12 now with winget? [Y/n]"
    if ($answer -eq "" -or $answer -match "^[Yy]") {
      winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
      Write-Host "`nPython installed. Close this window, open a new PowerShell, and run .\install.ps1 again."
      exit 0
    }
  }
  Write-Host "Install Python from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run .\install.ps1 again."
  exit 1
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  Write-Host "Creating virtual environment..."
  & $py[0] @($py[1..($py.Length - 1)]) -m venv .venv
}

Write-Host "Installing (this can take a minute)..."
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet -e .
if ($LASTEXITCODE -ne 0) { Write-Host "Install failed."; exit 1 }

if ($Yes) {
  & .\.venv\Scripts\python.exe -m samantha_mirror setup --yes
} else {
  & .\.venv\Scripts\python.exe -m samantha_mirror setup
}
exit $LASTEXITCODE
