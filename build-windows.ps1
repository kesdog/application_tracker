$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
if (-not (Test-Path 'frontend/dist/index.html')) { throw 'Run pnpm --dir frontend build first.' }
$resolvedRoot = [IO.Path]::GetFullPath($root).TrimEnd([IO.Path]::DirectorySeparatorChar)
$resolvedDist = [IO.Path]::GetFullPath((Join-Path $root 'build/windows'))
if (-not $resolvedDist.StartsWith($resolvedRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Build output must stay inside this project.' }
$uiData = (Join-Path $root 'frontend/dist') + ';frontend/dist'
$migrationData = (Join-Path $root 'backend/migrations') + ';backend/migrations'
$alembicData = (Join-Path $root 'alembic.ini') + ';.'
& '.\.venv\Scripts\python.exe' -m PyInstaller --noconfirm --onedir --windowed --name ApplicationTracker --paths backend --distpath $resolvedDist --workpath build/pyinstaller --specpath build --add-data $uiData --add-data $migrationData --add-data $alembicData --collect-all phonenumbers --collect-submodules pystray --collect-submodules uvicorn --hidden-import sqlalchemy.dialects.sqlite backend/desktop_launcher.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
Write-Output 'Executable: build/windows/ApplicationTracker/ApplicationTracker.exe'
