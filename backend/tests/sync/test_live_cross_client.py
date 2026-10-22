"""Explicit opt-in integration probe; synthetic encrypted data, no tracker records.

Provide two .env files for already-consented installations using different OAuth
clients in the same Cloud project. Never copy refresh tokens between devices.
"""
import os
import secrets
from pathlib import Path
from uuid import uuid4

import pytest

from app.config import Settings
from app.database import create_database
from app.google_connection import GoogleConnection
from app.sync.crypto import open_envelope, seal
from app.sync.drive import DriveTransport
from app.sync.schemas import Batch


@pytest.mark.skipif(os.environ.get('TRACKER_SYNC_CROSS_CLIENT') != '1', reason='Requires explicit operator opt-in and two independently authorized OAuth clients')
def test_real_appdata_visibility_and_feed_in_both_directions():
    paths = [os.environ.get('TRACKER_SYNC_CLIENT_A_ENV'), os.environ.get('TRACKER_SYNC_CLIENT_B_ENV')]
    assert all(paths), 'Set both client .env file paths; no credentials are printed'
    settings = [Settings(_env_file=Path(path)) for path in paths]
    assert settings[0].google_client_id != settings[1].google_client_id, 'Use distinct OAuth clients'
    engines = [create_database(item.app_data_dir) for item in settings]
    uploaded = []
    try:
        connections = [GoogleConnection(engine, item) for engine, item in zip(engines, settings)]
        transports = [DriveTransport(connection) for connection in connections]
        assert transports[0].identity() == transports[1].identity(), 'Use the same verified Google account'
        workspace, key = uuid4(), secrets.token_bytes(32)
        for source, target in ((0, 1), (1, 0)):
            cursor = transports[target].start_cursor()
            batch = Batch(workspace_id=workspace, device_id=uuid4(), batch_id=uuid4(), kind='ack')
            file_id = transports[source].upload_immutable(str(batch.batch_id), seal(batch, key))
            uploaded.append((connections[source], file_id))
            assert file_id in {item['id'] for item in transports[target].list_files()}
            assert open_envelope(transports[target].download(file_id), key, str(workspace)) == batch
            observed = set()
            while True:
                files, _, cursor, more = transports[target].changes(cursor)
                observed.update(item['id'] for item in files)
                if not more:
                    break
            assert file_id in observed, 'Opposite OAuth client must observe the new file in its change feed'
    finally:
        try:
            for connection, file_id in uploaded:
                connection.api('drive', 'DELETE', 'drive/v3/files/' + file_id)
        finally:
            for engine in engines:
                engine.dispose()
