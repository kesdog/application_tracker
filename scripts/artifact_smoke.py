"""Exercise the installed distribution and built UI using an isolated workspace."""
import tempfile
from pathlib import Path


def main():
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app
    from app import __version__
    with tempfile.TemporaryDirectory(prefix='tracker-artifact-') as temporary:
        settings = Settings(app_data_dir=Path(temporary), app_host='127.0.0.1', app_port=8000,
            app_mode='local', app_allow_remote_human=False, app_password_hash=None, app_password_hash_file=None,
            app_push_vapid_key_file=None, app_push_contact=None, _env_file=None)
        with TestClient(create_app(settings), base_url='http://127.0.0.1:8000', headers={'Origin': 'http://127.0.0.1:8000'}) as client:
            assert client.get('/').status_code == 200
            assert client.get('/api/health').json()['version'] == __version__
            record = client.post('/api/applications', json={'company': 'Artifact smoke', 'job_title': 'Engineer',
                'date_applied': '2026-10-01', 'email_reference': 'Synthetic smoke only'})
            assert record.status_code == 201, record.text
            parent = record.json()['id']
            upload = client.post(f'/api/applications/{parent}/documents', data={'document_type': 'CV'}, files={'file': ('cv.txt', b'Synthetic CV')})
            assert upload.status_code == 201
            backup = client.post('/api/workspace/backup')
            assert backup.status_code == 200
            verified = client.post('/api/workspace/recovery/validate', files={'file': ('backup.zip', backup.content)})
            assert verified.status_code == 200 and verified.json()['applications'] == 1
        with TestClient(create_app(settings), base_url='http://127.0.0.1:8000') as client:
            assert client.get('/api/applications').json()[0]['id'] == parent
    print('Installed artifact: UI, health, migration, persistence, document and backup/recovery checks passed.')


if __name__ == '__main__':
    main()
