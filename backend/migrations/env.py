from alembic import context

from app.config import Settings
from app.database import create_database
from app.models import Base


def run_migrations(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url="sqlite://", target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif context.config.attributes.get("connection") is not None:
    run_migrations(context.config.attributes["connection"])
else:
    engine = create_database(Settings().app_data_dir)
    try:
        with engine.connect() as connection:
            run_migrations(connection)
    finally:
        engine.dispose()
