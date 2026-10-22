"""Durable incremental merge queue and hot-path lookup indexes."""
from alembic import op
import sqlalchemy as sa

revision = '0024_sync_work_queue'
down_revision = '0023_compact_sync'
branch_labels = None
depends_on = None

INDEXES = {
    'ix_sync_mutations_record': ('sync_mutations', ['entity', 'entity_id']),
    'ix_sync_mutations_applied_device': ('sync_mutations', ['applied', 'device_id', 'device_seq']),
    'ix_sync_outbox_pending': ('sync_outbox', ['uploaded', 'batch_id']),
    'ix_sync_outbox_unbatched': ('sync_outbox', ['batch_id', 'event_id']),
    'ix_sync_batches_pending': ('sync_batches', ['uploaded', 'batch_id']),
    'ix_sync_inbox_batch': ('sync_inbox', ['batch_id']),
    'ix_sync_conflicts_open_record': ('sync_conflicts', ['resolved', 'record_key']),
}


def upgrade():
    op.create_table('sync_dirty', sa.Column('key', sa.String(80), primary_key=True))
    # Existing prototype replicas get one safe recomputation after upgrading.
    op.execute("INSERT INTO sync_dirty(key) SELECT DISTINCT entity || ':' || entity_id FROM sync_mutations")
    for name, (table, columns) in INDEXES.items():
        op.create_index(name, table, columns)


def downgrade():
    for name, (table, _) in reversed(list(INDEXES.items())):
        op.drop_index(name, table_name=table)
    op.drop_table('sync_dirty')
