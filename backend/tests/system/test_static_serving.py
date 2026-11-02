from fastapi.testclient import TestClient

from app import __version__
from app.config import Settings
from app.main import create_app


def test_frontend_assets_and_deep_links_are_served_without_swallowing_api_404s(tmp_path):
    static = tmp_path / 'static'
    (static / 'assets').mkdir(parents=True)
    (static / 'index.html').write_text('<title>Application Tracker</title>', encoding='utf-8')
    (static / 'assets' / 'app.js').write_text('fixture asset', encoding='utf-8')
    with TestClient(create_app(Settings(app_data_dir=tmp_path / 'data', app_static_dir=static, _env_file=None))) as client:
        assert client.get('/').text == '<title>Application Tracker</title>'
        assert client.get('/applications/example').text == client.get('/').text
        assert client.get('/assets/app.js').text == 'fixture asset'
        assert client.get('/api/health').json()['version'] == __version__
        assert client.get('/api/missing').status_code == 404


def test_independent_phone_shell_is_public_and_scoped_without_exposing_workspace_apis(tmp_path):
    from app.human_auth import hash_password
    static = tmp_path / 'static'
    (static / 'assets').mkdir(parents=True)
    (static / 'phone').mkdir()
    (static / 'index.html').write_text('<title>Desktop</title>', encoding='utf-8')
    for filename, body in [('index.html', '<title>Independent phone</title>'), ('sw.js', '// phone worker'), ('manifest.webmanifest', '{"scope":"/phone/"}')]:
        (static / 'phone' / filename).write_text(body, encoding='utf-8')
    settings = Settings(app_data_dir=tmp_path / 'data', app_static_dir=static, app_mode='hosted', app_host='0.0.0.0',
        app_public_url='https://tracker.test', app_password_hash=hash_password('synthetic-password'), _env_file=None)
    with TestClient(create_app(settings), base_url='https://tracker.test') as client:
        response = client.get('/phone/')
        assert response.status_code == 200 and 'Independent phone' in response.text
        assert 'https://www.googleapis.com' in response.headers['content-security-policy']
        assert 'https://openidconnect.googleapis.com' in response.headers['content-security-policy']
        assert 'https://accounts.google.com/gsi/client' in response.headers['content-security-policy']
        assert response.headers['cross-origin-opener-policy'] == 'same-origin-allow-popups'
        worker = client.get('/phone/sw.js')
        assert worker.headers['service-worker-allowed'] == '/phone/' and worker.headers['cache-control'] == 'no-cache'
        assert client.get('/phone/manifest.webmanifest').json()['scope'] == '/phone/'
        assert client.get('/api/applications').status_code == 401
        assert client.post('/api/sync/probe/start', json={'phone_client_id': 'phone.apps.googleusercontent.com'}).status_code == 401
