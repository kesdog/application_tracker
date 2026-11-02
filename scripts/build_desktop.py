"""Native PyInstaller builder shared by every OS; includes only explicit assets."""
import json
from importlib.metadata import version
import os
from pathlib import Path
import platform
import plistlib
import subprocess
import sys

from release_check import ROOT, metadata


def main():
    target = {'win32': 'windows', 'linux': 'linux', 'darwin': 'macos'}[sys.platform]
    if not (ROOT / 'frontend/dist/index.html').is_file():
        raise RuntimeError('Run pnpm --dir frontend build first')
    info = metadata()
    info.update(os=target, architecture=platform.machine(), toolchain={
        'python': platform.python_version(), 'pyinstaller': version('pyinstaller')})
    manifest = ROOT / '.run/build-info.json'
    manifest.parent.mkdir(exist_ok=True)
    manifest.write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
        '--name', 'ApplicationTracker', '--paths', str(ROOT / 'backend'), '--distpath', f'build/{target}',
        '--workpath', f'build/pyinstaller-{target}', '--specpath', 'build',
        '--hidden-import', 'sqlalchemy.dialects.sqlite']
    if target in {'windows', 'macos'}:
        command.append('--windowed')
        from PIL import Image
        icon = ROOT / ('.run/tracker.ico' if target == 'windows' else '.run/tracker.icns')
        with Image.open(ROOT / 'frontend/public/icons/icon-512.png') as image:
            image.save(icon)
        command += ['--icon', str(icon)]
    if target == 'windows':
        command += ['--manifest', str(ROOT / 'packaging/windows/app.manifest')]
    if target == 'macos':
        command += ['--osx-bundle-identifier', 'io.github.kesdog.application-tracker']
        if os.environ.get('MACOS_SIGN_IDENTITY'):
            command += ['--codesign-identity', os.environ['MACOS_SIGN_IDENTITY'],
                '--osx-entitlements-file', str(ROOT / 'packaging/macos/entitlements.plist')]
    resources = [('frontend/dist', 'frontend/dist'), ('backend/migrations', 'backend/migrations'),
        ('alembic.ini', '.'), (str(manifest), '.')]
    import ssl
    policy = Path(ssl.__file__).with_name('codex-rejected-cas.pem')
    if policy.is_file():
        resources.append((str(policy), '.'))
    for source, destination in resources:
        # PyInstaller resolves data relative to the generated spec, not cwd.
        command += ['--add-data', str((ROOT / source).resolve()) + os.pathsep + destination]
    for package in ['phonenumbers', 'mf2py', 'extruct', 'pyRdfa', 'rdflib', 'webtoolbox', 'ddgs', 'primp']:
        command += ['--collect-all', package]
    for package in ['pystray', 'uvicorn', 'keyring.backends']:
        command += ['--collect-submodules', package]
    subprocess.run([*command, 'backend/desktop_launcher.py'], cwd=ROOT, check=True)
    if target == 'macos':
        path = ROOT / 'build/macos/ApplicationTracker.app/Contents/Info.plist'
        with path.open('rb') as handle:
            values = plistlib.load(handle)
        values.update(CFBundleShortVersionString=info['version'].split('-')[0],
            CFBundleVersion=info['version'].split('-')[0], NSHighResolutionCapable=True)
        with path.open('wb') as handle:
            plistlib.dump(values, handle)
    print(f'Built {target} {info["architecture"]} {info["version"]} at {info["commit"]}')


if __name__ == '__main__':
    main()
