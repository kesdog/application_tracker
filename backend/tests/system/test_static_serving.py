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
