import hashlib
import json
from pathlib import Path
import shutil

import pytest

from scripts.release_check import ROOT, check
from scripts.release_manifest import generate
from scripts.package_desktop import audit_bundle
from scripts.release_notes import notes


def version_tree(tmp_path):
    for name in ['pyproject.toml', 'backend/app/__init__.py', 'frontend/package.json',
                 'frontend/public/manifest.webmanifest', 'frontend/public/phone/manifest.webmanifest', 'packaging/application.json']:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    return tmp_path


def test_version_check_rejects_stale_manifests_and_wrong_tags(tmp_path):
    root = version_tree(tmp_path)
    version = check(root)
    assert check(root, 'v' + version) == version
    with pytest.raises(ValueError, match='Tag'):
        check(root, 'v0.0.0')
    path = root / 'frontend/public/phone/manifest.webmanifest'
    data = json.loads(path.read_text())
    data['version'] = '0.0.1'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='disagree'):
        check(root)


def test_manifest_binds_checksums_to_exact_source_and_rejects_mixed_artifacts(tmp_path):
    info = {'version': '1.2.3', 'commit': 'a' * 40, 'compact_sync': {'minimum': 1, 'maximum': 1}}
    asset = tmp_path / 'ApplicationTracker-phone.zip'
    asset.write_bytes(b'synthetic public package')
    result = generate(tmp_path, info)
    assert result['assets'][0]['sha256'] == hashlib.sha256(asset.read_bytes()).hexdigest()
    assert asset.name in (tmp_path / 'SHA256SUMS').read_text()
    receipt = tmp_path / 'ApplicationTracker-linux-x64.build.json'
    receipt.write_text(json.dumps({**info, 'commit': 'b' * 40}))
    with pytest.raises(ValueError, match='metadata'):
        generate(tmp_path, info)


def test_complete_release_rejects_missing_or_unsigned_platforms(tmp_path):
    info = {'version': '1.2.3', 'commit': 'a' * 40, 'compact_sync': {'minimum': 1, 'maximum': 1}}
    (tmp_path / 'ApplicationTracker-phone.zip').write_bytes(b'public')
    with pytest.raises(ValueError, match='missing'):
        generate(tmp_path, info, require_complete=True)
    for target, arch in [('windows', 'x64'), ('linux', 'x64'), ('macos', 'x64'), ('macos', 'arm64')]:
        (tmp_path / f'ApplicationTracker-{target}-{arch}.build.json').write_text(json.dumps({**info,
            'os': target, 'architecture': arch, 'signed_release': False}))
    with pytest.raises(ValueError, match='signing'):
        generate(tmp_path, info, require_complete=True)


def test_complete_release_has_all_platforms_and_refuses_unexpected_payload(tmp_path):
    info = {'version': '1.2.3', 'commit': 'a' * 40, 'compact_sync': {'minimum': 1, 'maximum': 1}}
    for target, arch in [('windows', 'x64'), ('linux', 'x64'), ('macos', 'x64'), ('macos', 'arm64')]:
        prefix = tmp_path / f'ApplicationTracker-1.2.3-{target}-{arch}'
        Path(str(prefix) + '.build.json').write_text(json.dumps({**info, 'os': target, 'architecture': arch, 'signed_release': target != 'linux'}))
        Path(str(prefix) + {'windows': '.exe', 'linux': '.deb', 'macos': '.dmg'}[target]).write_bytes(b'synthetic package')
    (tmp_path / 'ApplicationTracker-phone.zip').write_bytes(b'public')
    (tmp_path / 'ApplicationTracker-oci.json').write_text('[]')
    assert len(generate(tmp_path, info, require_complete=True)['builds']) == 4
    (tmp_path / 'ApplicationTracker-private.zip').write_bytes(b'must not ship')
    with pytest.raises(ValueError, match='Unexpected'):
        generate(tmp_path, info, require_complete=True)


def test_desktop_audit_rejects_user_database_and_dotenv(tmp_path):
    (tmp_path / 'tracker.sqlite3').write_bytes(b'private')
    with pytest.raises(ValueError, match='Private workspace'):
        audit_bundle(tmp_path)
    (tmp_path / 'tracker.sqlite3').unlink()
    (tmp_path / '.env').write_text('private')
    with pytest.raises(ValueError, match='Private workspace'):
        audit_bundle(tmp_path)


def test_release_notes_exclude_unreleased_and_other_versions(tmp_path):
    root = version_tree(tmp_path)
    version = check(root)
    (root / 'CHANGELOG.md').write_text(f'# Changelog\n\n## Unreleased\n\nFuture feature\n\n## {version} — Release\n\nReviewed behavior\n\n## 0.0.1\n\nOld behavior\n', encoding='utf-8')
    result = notes(root, 'v' + version)
    assert 'Reviewed behavior' in result
    assert 'Future feature' not in result and 'Old behavior' not in result
