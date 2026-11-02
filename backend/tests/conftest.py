"""Shared defaults; every test still gets its own workspace and app lifespan."""
import asyncio
from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def offline_default_recipient_scheduler(monkeypatch):
    """Automatic recipient jobs must never use public web providers in routine tests."""
    from app.recipient_discovery import RecipientScheduler
    original = RecipientScheduler.__init__

    class OfflineResearch:
        async def discover(self, context):
            # Unrelated tests may install their own candidate fixtures. Keep
            # automatic work pending rather than racing to replace those rows.
            # Scheduler tests inject their own deterministic researcher instead.
            await asyncio.Event().wait()

    def initialize(self, engine, settings, researcher=None):
        original(self, engine, settings, researcher if researcher is not None else OfflineResearch())

    monkeypatch.setattr(RecipientScheduler, '__init__', initialize)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(app_data_dir=tmp_path, _env_file=None))) as client:
        yield client
