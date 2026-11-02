$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
& '.\.venv\Scripts\python.exe' scripts/build_desktop.py
if ($LASTEXITCODE -ne 0) { throw "Desktop build failed with exit code $LASTEXITCODE" }
Write-Output 'Executable: build/windows/ApplicationTracker/ApplicationTracker.exe'
