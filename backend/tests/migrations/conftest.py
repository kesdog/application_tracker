from contextlib import contextmanager

from alembic import command
from alembic.config import Config
import pytest

from app.config import PROJECT_ROOT
from app.database import create_database


@pytest.fixture
def legacy_database(tmp_path):
    @contextmanager
    def at_revision(revision):
        engine = create_database(tmp_path)
        config = Config(str(PROJECT_ROOT / 'alembic.ini'))
        try:
            with engine.begin() as connection:
                config.attributes['connection'] = connection
                command.upgrade(config, revision)
                yield connection
        finally:
            engine.dispose()
    return at_revision
