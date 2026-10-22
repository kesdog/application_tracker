import json
import pytest

from app.google_connection import GoogleConnectionError
from app.secret_store import EncryptedFileSecretStore, create_key


def test_server_credentials_survive_restart_without_plaintext_and_fail_closed(tmp_path):
    key = tmp_path / 'master.key'; create_key(key)
    workspace = tmp_path / 'data'
    store = EncryptedFileSecretStore(workspace, key)
    assert store.get('token') is None
    store.put('token', {'refresh_token': 'private-refresh', 'access_token': 'private-access'})
    assert b'private-refresh' not in store.path('token').read_bytes()
    assert EncryptedFileSecretStore(workspace, key).get('token')['refresh_token'] == 'private-refresh'
    other = tmp_path / 'other.key'; create_key(other)
    with pytest.raises(GoogleConnectionError): EncryptedFileSecretStore(workspace, other).get('token')
    raw = store.path('token').read_bytes(); store.path('token').write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    with pytest.raises(GoogleConnectionError): store.get('token')
    store.delete('token'); assert store.get('token') is None
    with pytest.raises(ValueError): EncryptedFileSecretStore(workspace, workspace / 'key')
    with pytest.raises(FileExistsError): create_key(key)
