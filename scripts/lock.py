"""Regenerate hashed platform-aware locks with uv 0.13.5."""
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--uv', default=shutil.which('uv') or 'uv')
    args = parser.parse_args()
    base = [args.uv, 'pip', 'compile', 'pyproject.toml',
        'libs/portable-webtoolbox-embedded-v0.7.0/webtoolbox-embedded/pyproject.toml', 'requirements-build.in',
        '--extra', 'search', '--universal', '--python-version', '3.12', '--generate-hashes', '--no-annotate',
        '--custom-compile-command', 'python scripts/lock.py']
    for name, extras in [('requirements-dev.lock', ['dev', 'desktop', 'build-desktop']), ('requirements-runtime.lock', [])]:
        command = [*base]
        for extra in extras: command.extend(['--extra', extra])
        if (ROOT / name).exists(): command.extend(['-c', name])
        subprocess.run([*command, '-o', name], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
