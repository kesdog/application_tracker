"""Create unsigned CI candidates or package already-signed native bundles."""
import argparse
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile

try:
    from .release_check import ROOT, metadata
except ImportError:
    from release_check import ROOT, metadata


def audit_bundle(root):
    forbidden = {'.env', '.env.local', 'tracker.sqlite3', 'credentials.json', 'token.json',
        'recovery-success.txt', 'test.md', 'startup-error.log', 'desktop.log'}
    for path in root.rglob('*'):
        if path.name in forbidden or path.name.endswith(('.sqlite3', '.sqlite3-wal', '.sqlite3-shm')):
            raise ValueError(f'Private workspace file in desktop bundle: {path.relative_to(root)}')


def linux_deb(bundle, output, version):
    staging = ROOT / 'build/deb-root'
    if staging.exists():
        raise ValueError('Use a clean build/deb-root for each package')
    app = staging / 'opt/application-tracker'
    shutil.copytree(bundle, app, symlinks=True)
    (staging / 'DEBIAN').mkdir()
    (staging / 'DEBIAN/control').write_text(
        f'Package: application-tracker\nVersion: {version.replace("-", "~")}\nArchitecture: amd64\n'
        'Maintainer: Application Tracker contributors\nSection: utils\nPriority: optional\n'
        'Depends: libc6 (>= 2.39), libstdc++6, libgcc-s1, xdg-utils, libdbus-1-3\n'
        'Description: Local-first application tracker with optional encrypted phone sync\n', encoding='utf-8')
    launcher = staging / 'usr/bin/application-tracker'
    launcher.parent.mkdir(parents=True)
    launcher.write_text('#!/bin/sh\nexec /opt/application-tracker/ApplicationTracker "$@"\n')
    launcher.chmod(0o755)
    entry = staging / 'usr/share/applications/application-tracker.desktop'
    entry.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / 'packaging/linux/application-tracker.desktop', entry)
    icon = staging / 'usr/share/icons/hicolor/512x512/apps/application-tracker.png'
    icon.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / 'frontend/public/icons/icon-512.png', icon)
    subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(staging), str(output)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', action='store_true', help='Package a bundle signed by the protected release job')
    args = parser.parse_args()
    info = metadata()
    target = {'win32': 'windows', 'linux': 'linux', 'darwin': 'macos'}[sys.platform]
    arch = 'arm64' if platform.machine().lower() in {'arm64', 'aarch64'} else 'x64'
    prefix = f'ApplicationTracker-{info["version"]}-{target}-{arch}'
    built = json.loads((ROOT / '.run/build-info.json').read_text(encoding='utf-8'))
    if any(built.get(key) != info[key] for key in ['version', 'commit', 'compact_sync']) or built.get('os') != target:
        raise ValueError('Build metadata does not match the current source and platform')
    bundle = ROOT / f'build/{target}/ApplicationTracker'
    output = ROOT / '.run'
    output.mkdir(exist_ok=True)
    audit_bundle(bundle)
    if target == 'windows':
        if not args.release:
            shutil.make_archive(str(output / (prefix + '-unsigned')), 'zip', bundle.parent, bundle.name)
        compiler = shutil.which('ISCC.exe') or str(Path('C:/Program Files (x86)/Inno Setup 6/ISCC.exe'))
        subprocess.run([compiler, f'/DAppVersion={info["version"]}',
            f'/DOutputName={prefix}' + ('' if args.release else '-unsigned'),
            str(ROOT / 'packaging/windows/tracker.iss')], check=True)
    elif target == 'linux':
        with tarfile.open(output / (prefix + '.tar.gz'), 'w:gz') as archive:
            archive.add(bundle, arcname=bundle.name)
        linux_deb(bundle, output / (prefix + '.deb'), info['version'])
    else:
        app = bundle.with_suffix('.app')
        audit_bundle(app)
        staging = ROOT / 'build/dmg-root'
        staging.mkdir(exist_ok=False)
        # ditto preserves native bundle metadata and the stapled ticket.
        subprocess.run(['ditto', str(app), str(staging / app.name)], check=True)
        (staging / 'Applications').symlink_to('/Applications', target_is_directory=True)
        subprocess.run(['hdiutil', 'create', '-volname', 'Application Tracker', '-srcfolder', str(staging),
            '-ov', '-format', 'UDZO', str(output / (prefix + ('' if args.release else '-unsigned') + '.dmg'))], check=True)
    (output / (prefix + '.build.json')).write_text(json.dumps({**built, 'os': target, 'architecture': arch,
        'signed_release': args.release and target in {'windows', 'macos'}}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
