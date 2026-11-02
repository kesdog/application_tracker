"""Validate version agreement without importing the app or reading dotenv files."""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r'\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?')


def check(root=ROOT, tag=None):
    versions = {'pyproject.toml': tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']}
    module = ast.parse((root / 'backend/app/__init__.py').read_text())
    versions['backend'] = next(ast.literal_eval(node.value) for node in module.body
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__version__' for t in node.targets))
    for name in ['frontend/package.json', 'frontend/public/manifest.webmanifest',
                 'frontend/public/phone/manifest.webmanifest', 'packaging/application.json']:
        versions[name] = json.loads((root / name).read_text(encoding='utf-8'))['version']
    version = versions['pyproject.toml']
    if not VERSION.fullmatch(version) or set(versions.values()) != {version}:
        raise ValueError(f'Application versions disagree or are invalid: {versions}')
    if tag is not None and tag != 'v' + version:
        raise ValueError(f'Tag {tag!r} must equal v{version}')
    return version


def metadata(root=ROOT, tag=None):
    version = check(root, tag)
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    return {'version': version, 'commit': sha, 'compact_sync': {'minimum': 1, 'maximum': 1}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = metadata(tag=args.tag)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
