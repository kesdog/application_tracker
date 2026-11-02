"""Package only the public independent phone shell after a normal frontend build."""
import argparse
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def public_files(source):
    source = source.resolve()
    worker = (source / 'phone/sw.js').read_text(encoding='utf-8')
    assets = json.loads(re.search(r'const ASSETS = (\[[^\n]*\])', worker).group(1))
    files = ['phone/index.html', 'phone/sw.js', 'phone/manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png']
    files += [asset.lstrip('/') for asset in assets]
    resolved = []
    for name in files:
        path = (source / name).resolve()
        if not path.is_relative_to(source) or not path.is_file():
            raise ValueError('Phone package references a missing or out-of-root asset')
        if path.suffix in {'.html', '.js'}:
            text = path.read_text(encoding='utf-8')
            if 'Synthetic Google HTTP fixture' in text or '/fixture/google' in text:
                raise ValueError('Refusing to package a simulated browser-test build')
        resolved.append((path, name))
    return resolved


def prepare_site(source, directory):
    """Write only verified public assets into a new/empty isolated Site dist."""
    resolved = public_files(source)
    destination = directory.resolve() / 'dist'
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Use an empty Site dist directory; preserve existing deployments')
    destination.mkdir(parents=True, exist_ok=True)
    for path, name in resolved:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    (destination / 'index.html').write_text('<!doctype html><meta http-equiv="refresh" content="0;url=/phone/"><a href="/phone/">Open phone app</a>', encoding='utf-8')
    # Keep the OAuth popup functional; force HTML/worker revalidation for updates.
    (destination / '_headers').write_text('/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: no-referrer\n  Cross-Origin-Opener-Policy: same-origin-allow-popups\n/phone/\n  Cache-Control: no-cache\n/phone/sw.js\n  Cache-Control: no-cache\n', encoding='utf-8')
    return len(resolved)


def package(source, destination):
    resolved = public_files(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
        for path, name in resolved:
            archive.write(path, name)
        archive.writestr('index.html', '<!doctype html><meta http-equiv="refresh" content="0;url=/phone/"><a href="/phone/">Open phone app</a>')
        archive.writestr('DEPLOY.txt', 'Serve these public files from the root of an HTTPS static origin. Open /phone/.\nRegister that origin on a separate Google Web OAuth client in the desktop client project.\nNo backend or user data is included. Keep recovery exports and unlock passphrases outside this package.\n')
    return len(resolved)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'frontend/dist')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/phone-app.zip')
    parser.add_argument('--site-directory', type=Path, help='Also prepare an empty isolated Site dist directory')
    args = parser.parse_args()
    count = package(args.source, args.output)
    if args.site_directory:
        prepare_site(args.source, args.site_directory)
    print(f'Packaged {count} public files at {args.output}; no workspace data or credentials included.')
