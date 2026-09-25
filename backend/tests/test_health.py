from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.exc import OperationalError

from app.config import PROJECT_ROOT, Settings
from app.main import create_app


def test_health_initializes_database_and_enables_wal(tmp_path):
    data_dir = tmp_path / "nested" / "data"
    application = create_app(Settings(app_data_dir=data_dir, _env_file=None))
    assert not data_dir.exists()
    with TestClient(application) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok", "version": "0.5.0", "database": "connected"
        }
        assert (data_dir / "tracker.sqlite3").is_file()
        with application.state.engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    # Reopening an existing database must also work.
    with TestClient(application) as client:
        assert client.get("/api/health").status_code == 200


def test_health_reports_database_failure(tmp_path):
    application = create_app(Settings(app_data_dir=tmp_path, _env_file=None))
    with TestClient(application) as client:
        with patch.object(application.state.engine, "connect", side_effect=OperationalError("SELECT 1", {}, Exception("unavailable"))):
            response = client.get("/api/health")
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}


def test_settings_load_dotenv_and_environment_takes_precedence(tmp_path, monkeypatch):
    for name in ("APP_HOST", "APP_PORT", "APP_ENV", "APP_DATA_DIR", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text("APP_HOST=0.0.0.0\nAPP_PORT=8123\nAPP_ENV=test\nAPP_DATA_DIR=./test-data\nLOG_LEVEL=DEBUG\n", encoding="utf-8")
    settings = Settings(_env_file=dotenv)
    assert settings.app_host == "0.0.0.0"
    assert settings.app_port == 8123
    assert settings.app_env == "test"
    assert settings.app_data_dir == PROJECT_ROOT / "test-data"
    assert settings.log_level == "debug"
    monkeypatch.setenv("APP_PORT", "9000")
    assert Settings(_env_file=dotenv).app_port == 9000


@pytest.mark.parametrize("port", [0, 65536])
def test_settings_reject_invalid_port(port):
    with pytest.raises(ValueError):
        Settings(app_port=port, _env_file=None)


def test_startup_fails_when_data_directory_is_a_file(tmp_path):
    data_path = tmp_path / "file"
    data_path.write_text("not a directory", encoding="utf-8")
    with pytest.raises(FileExistsError):
        with TestClient(create_app(Settings(app_data_dir=data_path, _env_file=None))):
            pass
