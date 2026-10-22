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
$runtimeDataArgs = @()
# Some Python distributions ship an additional CA policy file next to ssl.py.
# Preserve that policy when freezing their standard library.
$runtimeCa = & '.\.venv\Scripts\python.exe' -c "import ssl; from pathlib import Path; p = Path(ssl.__file__).with_name('codex-rejected-cas.pem'); print(str(p) if p.is_file() else '')"
if ($runtimeCa) { $runtimeDataArgs += @('--add-data', ($runtimeCa + ';.')) }
& '.\.venv\Scripts\python.exe' -m PyInstaller --noconfirm --onedir --windowed --name ApplicationTracker --paths backend --distpath $resolvedDist --workpath build/pyinstaller --specpath build --add-data $uiData --add-data $migrationData --add-data $alembicData --collect-all phonenumbers --collect-all mf2py --collect-all extruct --collect-all pyRdfa --collect-all rdflib --collect-all webtoolbox --collect-all ddgs --collect-all primp --collect-submodules pystray --collect-submodules uvicorn --hidden-import sqlalchemy.dialects.sqlite @runtimeDataArgs backend/desktop_launcher.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
Write-Output 'Executable: build/windows/ApplicationTracker/ApplicationTracker.exe'
