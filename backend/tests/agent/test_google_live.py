"""Operator opt-in, read-only smoke against the already connected real account."""
import os

import pytest

from app.config import Settings
from app.database import create_database
from app.google_connection import GoogleConnection, GoogleMailProvider


@pytest.mark.skipif(os.environ.get('TRACKER_GOOGLE_SMOKE') != '1', reason='Real Google smoke requires explicit operator opt-in')
def test_real_google_mailbox_lookup():
    query = os.environ.get('TRACKER_GOOGLE_SMOKE_QUERY')
    assert query, 'Set TRACKER_GOOGLE_SMOKE_QUERY to a known application email query'
    settings = Settings()
    engine = create_database(settings.app_data_dir)
    try:
        google = GoogleConnection(engine, settings)
        assert google.status()['capabilities']['gmail_read'], 'Connect Gmail read in Settings first'
        result = GoogleMailProvider(google).search(query, limit=1)
        assert isinstance(result['messages'], list)
    finally:
        engine.dispose()
