param([Parameter(Mandatory=$true)][string]$Installer, [Parameter(Mandatory=$true)][string]$Version)
$ErrorActionPreference = 'Stop'
$installRoot = Join-Path $env:RUNNER_TEMP ('tracker-install-' + [guid]::NewGuid())
$env:APP_DATA_DIR = Join-Path $env:RUNNER_TEMP ('tracker-install-data-' + [guid]::NewGuid())
$env:APP_DESKTOP_NO_BROWSER = '1'
foreach ($attempt in 1..2) {
    $installed = Start-Process -FilePath $Installer -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', ('/DIR="' + $installRoot + '"')) -PassThru -Wait -WindowStyle Hidden
    if ($installed.ExitCode -ne 0) { throw 'Installer failed' }
    & python scripts/desktop_smoke.py (Join-Path $installRoot 'ApplicationTracker.exe') --version $Version --workspace $env:APP_DATA_DIR
    if ($LASTEXITCODE -ne 0) { throw 'Installed executable smoke failed' }
    # A sentinel models a pre-existing workspace across reinstall/uninstall.
    New-Item -ItemType Directory -Path $env:APP_DATA_DIR -Force | Out-Null
    $sentinel = Join-Path $env:APP_DATA_DIR 'preserve-me.txt'
    if ($attempt -eq 1) { Set-Content -LiteralPath $sentinel -Value 'synthetic workspace' }
    if ((Get-Content -LiteralPath $sentinel) -ne 'synthetic workspace') { throw 'Upgrade damaged user data' }
}
$removed = Start-Process -FilePath (Join-Path $installRoot 'unins000.exe') -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -PassThru -Wait -WindowStyle Hidden
if ($removed.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $sentinel) -or -not (Test-Path -LiteralPath (Join-Path $env:APP_DATA_DIR 'tracker.sqlite3'))) { throw 'Uninstall failed or damaged user data' }
