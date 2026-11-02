"""Phone deployment artifacts must contain public shell assets only."""
import importlib.util
from pathlib import Path
from zipfile import ZipFile

import pytest

spec = importlib.util.spec_from_file_location('phone_packager', Path(__file__).resolve().parents[1] / 'scripts/package_phone.py')
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


def public_build(tmp_path, assets='["/assets/phone.js"]'):
    source = tmp_path / 'dist'
    (source / 'phone').mkdir(parents=True)
    (source / 'assets').mkdir()
    (source / 'icons').mkdir()
    for file in ['phone/index.html', 'phone/manifest.webmanifest', 'assets/phone.js', 'icons/icon-192.png', 'icons/icon-512.png']:
        (source / file).write_text('public synthetic artifact', encoding='utf-8')
    (source / 'phone/sw.js').write_text('const ASSETS = ' + assets + '\n', encoding='utf-8')
    return source


def test_phone_package_omits_workspace_credentials_local_coverage_and_desktop_assets(tmp_path):
    source = public_build(tmp_path)
    for name in ['test.md', '.env', 'tracker.sqlite3', 'assets/desktop-only.js']:
        (source / name).write_text('must not ship', encoding='utf-8')
    destination = tmp_path / 'phone.zip'
    assert packager.package(source, destination) == 6
    with ZipFile(destination) as archive:
        assert set(archive.namelist()) == {'phone/index.html', 'phone/manifest.webmanifest', 'phone/sw.js',
            'assets/phone.js', 'icons/icon-192.png', 'icons/icon-512.png', 'index.html', 'DEPLOY.txt'}
        assert not any(b'must not ship' in archive.read(name) for name in archive.namelist())


@pytest.mark.parametrize('problem', ['outside', 'test-build'])
def test_phone_package_rejects_path_escape_and_simulated_builds(tmp_path, problem):
    source = public_build(tmp_path, '["/../private.txt"]' if problem == 'outside' else '["/assets/phone.js"]')
    (tmp_path / 'private.txt').write_text('not public', encoding='utf-8')
    if problem == 'test-build':
        (source / 'assets/phone.js').write_text('fetch("/fixture/google")', encoding='utf-8')
    with pytest.raises(ValueError):
        packager.package(source, tmp_path / 'bad.zip')
    assert not (tmp_path / 'bad.zip').exists()


def test_static_site_preparation_uses_same_public_allowlist_and_preserves_existing_output(tmp_path):
    source = public_build(tmp_path)
    (source / '.env').write_text('private', encoding='utf-8')
    site = tmp_path / 'isolated-site'
    packager.prepare_site(source, site)
    assert not (site / 'dist/.env').exists()
    assert (site / 'dist/assets/phone.js').is_file()
    assert 'same-origin-allow-popups' in (site / 'dist/_headers').read_text()
    with pytest.raises(ValueError, match='empty Site dist'):
        packager.prepare_site(source, site)
