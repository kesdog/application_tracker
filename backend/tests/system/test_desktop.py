import socket
import sys

import pytest

from app.config import Settings, desktop_data_dir
from app.desktop import LoopbackHost, workspace_lock


@pytest.mark.parametrize('platform, suffix', [
    ('win32', 'ApplicationTracker'), ('darwin', 'Library/Application Support/ApplicationTracker'),
    ('linux', '.local/share/ApplicationTracker'),
])
def test_installed_data_paths_follow_platform_conventions(monkeypatch, platform, suffix):
    monkeypatch.setattr(sys, 'platform', platform)
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    monkeypatch.delenv('XDG_DATA_HOME', raising=False)
    assert desktop_data_dir().as_posix().endswith(suffix)


def test_linux_xdg_override_must_be_absolute(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path))
    assert desktop_data_dir() == tmp_path / 'ApplicationTracker'
    monkeypatch.setenv('XDG_DATA_HOME', 'relative-is-invalid')
    assert desktop_data_dir().is_absolute()
    assert 'relative-is-invalid' not in str(desktop_data_dir())


def test_workspace_lock_rejects_second_owner_and_releases_after_failure(tmp_path):
    with pytest.raises(ValueError):
        with workspace_lock(tmp_path):
            with pytest.raises(RuntimeError, match='already using'):
                with workspace_lock(tmp_path):
                    pytest.fail('Second owner acquired workspace')
            raise ValueError('simulated UI failure')
    with workspace_lock(tmp_path):
        assert (tmp_path / '.desktop.lock').is_file()


def test_port_collision_does_not_migrate_or_create_another_database(tmp_path):
    (tmp_path / 'ui').mkdir()
    (tmp_path / 'ui/index.html').write_text('<html>synthetic UI</html>')
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1', 0))
        settings = Settings(app_data_dir=tmp_path / 'untouched', app_static_dir=tmp_path / 'ui',
            app_port=occupied.getsockname()[1], _env_file=None)
        with pytest.raises(OSError):
            with LoopbackHost(settings):
                pytest.fail('Port collision was ignored')
    assert not settings.app_data_dir.exists()


def test_loopback_host_stops_on_ui_error_and_releases_listener(tmp_path):
    (tmp_path / 'ui').mkdir()
    (tmp_path / 'ui/assets').mkdir()
    (tmp_path / 'ui/index.html').write_text('<html>synthetic UI</html>')
    with socket.socket() as selection:
        selection.bind(('127.0.0.1', 0))
        port = selection.getsockname()[1]
    settings = Settings(app_data_dir=tmp_path / 'workspace', app_static_dir=tmp_path / 'ui', app_port=port, _env_file=None)
    with pytest.raises(ValueError):
        with LoopbackHost(settings) as host:
            assert host.server.started
            raise ValueError('simulated tray failure')
    assert not host.thread.is_alive()
    with socket.socket() as released:
        released.bind(('127.0.0.1', port))
    assert (settings.app_data_dir / 'tracker.sqlite3').is_file()


def test_desktop_rejects_remote_listener_before_database_access(tmp_path):
    with pytest.raises(RuntimeError, match='loopback'):
        with LoopbackHost(Settings(app_host='0.0.0.0', app_data_dir=tmp_path / 'untouched', _env_file=None)):
            pass
    assert not (tmp_path / 'untouched').exists()
