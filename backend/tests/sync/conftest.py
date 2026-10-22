from uuid import uuid4

import pytest

from app.database import create_database, migrate_database
from app.sync.engine import SyncEngine


from sync_support import MemorySecrets, ObjectStore


@pytest.fixture
def replicas(tmp_path):
    engines = []
    store = ObjectStore()
    def create(label):
        engine = create_database(tmp_path / label)
        migrate_database(engine)
        engines.append(engine)
        return SyncEngine(engine, store, MemorySecrets())
    yield create, store
    for engine in engines:
        engine.dispose()
