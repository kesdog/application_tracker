"""Hash explicit release assets and bind them to one source version/commit."""
import argparse
import hashlib
import json
from pathlib import Path
import re

try:
    from .release_check import metadata
except ImportError:
    from release_check import metadata


def generate(directory, info, require_complete=False):
    paths = sorted(p for p in directory.iterdir() if p.name.startswith('ApplicationTracker-'))
    if not paths or any(p.is_symlink() or not p.is_file() or not re.fullmatch(r'ApplicationTracker-[A-Za-z0-9_.-]+', p.name) for p in paths):
        raise ValueError('Release assets must be regular files with safe names')
    receipts = [json.loads(p.read_text()) for p in paths if p.name.endswith('.build.json')]
    for receipt in receipts:
        if any(receipt.get(key) != info[key] for key in ['version', 'commit', 'compact_sync']):
            raise ValueError('Release asset metadata does not match this commit/version')
    if require_complete:
        expected = {('windows', 'x64'), ('linux', 'x64'), ('macos', 'x64'), ('macos', 'arm64')}
        if len(receipts) != 4 or {(r['os'], r['architecture']) for r in receipts} != expected:
            raise ValueError('A desktop platform is missing from the release')
        if any(not r['signed_release'] for r in receipts if r['os'] in {'windows', 'macos'}):
            raise ValueError('Public desktop releases require signing')
        names = [p.name for p in paths]
        if any('-unsigned' in name for name in names):
            raise ValueError('Unsigned candidates cannot be promoted')
        for suffix in ['windows-x64.exe', 'linux-x64.deb', 'macos-x64.dmg', 'macos-arm64.dmg', 'phone.zip', 'oci.json']:
            if not any(name.endswith(suffix) for name in names):
                raise ValueError(f'Missing release asset: {suffix}')
        allowed = {'ApplicationTracker-phone.zip', 'ApplicationTracker-oci.json'}
        for target, architecture in expected:
            prefix = f'ApplicationTracker-{info["version"]}-{target}-{architecture}'
            allowed.add(prefix + '.build.json')
            allowed.add(prefix + {'windows': '.exe', 'linux': '.deb', 'macos': '.dmg'}[target])
            if target == 'linux':
                allowed.add(prefix + '.tar.gz')
        if set(names) - allowed:
            raise ValueError('Unexpected file in release artifacts')
    assets = []
    for path in paths:
        with path.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        assets.append({'name': path.name, 'sha256': digest, 'size': path.stat().st_size})
    result = {**info, 'builds': receipts, 'assets': assets}
    (directory / 'release-manifest.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    (directory / 'SHA256SUMS').write_text(''.join(f'{a["sha256"]}  {a["name"]}\n' for a in assets), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--require-complete', action='store_true')
    args = parser.parse_args()
    result = generate(args.directory, metadata(tag=args.tag), args.require_complete)
    print(f'Hashed {len(result["assets"])} assets for {result["version"]} at {result["commit"]}')


if __name__ == '__main__':
    main()
