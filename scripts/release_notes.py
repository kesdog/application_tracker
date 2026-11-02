"""Extract reviewed changelog notes for an exact version tag."""
import argparse
from pathlib import Path
import re

try:
    from .release_check import ROOT, check
except ImportError:
    from release_check import ROOT, check


def notes(root, tag):
    version = check(root, tag)
    text = (root / 'CHANGELOG.md').read_text(encoding='utf-8')
    match = re.search(r'^## ' + re.escape(version) + r'(?:\s|$).*?\n(.*?)(?=^## |\Z)', text, re.MULTILINE | re.DOTALL)
    if not match or not match.group(1).strip():
        raise ValueError('Add reviewed release notes to CHANGELOG.md before tagging')
    return match.group(1).strip() + '\n\nSee docs/UPGRADING.md for backup, restore and manual upgrade instructions.\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(notes(ROOT, args.tag), encoding='utf-8')
