from fastapi.testclient import TestClient

from app.backup import backup_workspace, restore_workspace
from app.config import Settings
from app.main import create_app


def test_supported_old_workspace_backup_restores_and_upgrades_without_changing_original(tmp_path, legacy_database):
    with legacy_database('0021_recipient_page_reports') as connection:
        connection.exec_driver_sql("INSERT INTO applications (id, job_title, company, date_applied, email_reference) VALUES ('release-old', 'Engineer', 'Synthetic upgrade', '2026-10-01', 'Synthetic source')")
    backup = tmp_path.parent / (tmp_path.name + '-backup')
    restored = tmp_path.parent / (tmp_path.name + '-restored')
    backup_workspace(tmp_path, backup)
    before = (backup / 'tracker.sqlite3').read_bytes()
    restore_workspace(backup, restored)
    settings = Settings(app_data_dir=restored, _env_file=None)
    with TestClient(create_app(settings)) as client:
        record = client.get('/api/applications/release-old').json()
        assert record['company'] == 'Synthetic upgrade'
        assert client.patch('/api/applications/release-old', json={'job_title': 'Upgraded engineer'}).status_code == 200
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/applications/release-old').json()['job_title'] == 'Upgraded engineer'
    assert (backup / 'tracker.sqlite3').read_bytes() == before
