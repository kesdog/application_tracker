"""Opt-in compact replica journal; frozen schema, no credentials or document fields."""
from alembic import op

revision = '0023_compact_sync'
down_revision = '0022_shared_google_agent'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE TABLE sync_workspace (\n\tid INTEGER NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tdevice_id VARCHAR(36) NOT NULL, \n\tlabel VARCHAR(100) NOT NULL, \n\tsubject VARCHAR(255) NOT NULL, \n\tsecret_reference VARCHAR(100), \n\tnext_seq INTEGER NOT NULL, \n\tcursor TEXT, \n\tlast_success DATETIME, \n\tlast_error VARCHAR(500), \n\tretry_at DATETIME, \n\tfailures INTEGER NOT NULL, \n\tremote_bytes INTEGER NOT NULL, \n\tremote_objects INTEGER NOT NULL, \n\trestored BOOLEAN NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT single_sync_workspace CHECK (id = 1)\n)')
    op.execute('CREATE TABLE sync_mutations (\n\tevent_id VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tdevice_id VARCHAR(36) NOT NULL, \n\tdevice_seq INTEGER NOT NULL, \n\tentity VARCHAR(20) NOT NULL, \n\tentity_id VARCHAR(36) NOT NULL, \n\tpayload JSON NOT NULL, \n\tapplied BOOLEAN NOT NULL, \n\tPRIMARY KEY (event_id), \n\tCONSTRAINT sync_device_sequence UNIQUE (device_id, device_seq)\n)')
    op.execute('CREATE INDEX ix_sync_mutations_entity ON sync_mutations (entity)')
    op.execute('CREATE INDEX ix_sync_mutations_entity_id ON sync_mutations (entity_id)')
    op.execute('CREATE TABLE sync_records (\n\t"key" VARCHAR(80) NOT NULL, \n\theads JSON NOT NULL, \n\tapplied_heads JSON NOT NULL, \n\tstate JSON NOT NULL, \n\timported BOOLEAN NOT NULL, \n\tPRIMARY KEY ("key")\n)')
    op.execute('CREATE TABLE sync_outbox (\n\tevent_id VARCHAR(36) NOT NULL, \n\tbatch_id VARCHAR(36), \n\tuploaded BOOLEAN NOT NULL, \n\tPRIMARY KEY (event_id)\n)')
    op.execute('CREATE INDEX ix_sync_outbox_batch_id ON sync_outbox (batch_id)')
    op.execute('CREATE TABLE sync_inbox (\n\tfile_id VARCHAR(255) NOT NULL, \n\tdigest VARCHAR(64) NOT NULL, \n\tbatch_id VARCHAR(36) NOT NULL, \n\tquota_bytes INTEGER NOT NULL, \n\tPRIMARY KEY (file_id)\n)')
    op.execute('CREATE TABLE sync_batches (\n\tbatch_id VARCHAR(36) NOT NULL, \n\tciphertext BLOB NOT NULL, \n\tuploaded BOOLEAN NOT NULL, \n\tPRIMARY KEY (batch_id)\n)')
    op.execute('CREATE TABLE sync_conflicts (\n\tid VARCHAR(64) NOT NULL, \n\trecord_key VARCHAR(80) NOT NULL, \n\theads JSON NOT NULL, \n\tvariants JSON NOT NULL, \n\tbase JSON NOT NULL, \n\treason VARCHAR(100) NOT NULL, \n\tresolved BOOLEAN NOT NULL, \n\tPRIMARY KEY (id)\n)')
    op.execute('CREATE INDEX ix_sync_conflicts_record_key ON sync_conflicts (record_key)')
    op.execute('CREATE TABLE sync_devices (\n\tdevice_id VARCHAR(36) NOT NULL, \n\tacknowledgments JSON NOT NULL, \n\tlast_seen DATETIME NOT NULL, \n\tPRIMARY KEY (device_id)\n)')
    op.execute('CREATE TABLE sync_checkpoints (\n\tbatch_id VARCHAR(36) NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tevent_count INTEGER NOT NULL, \n\tuploaded BOOLEAN NOT NULL, \n\tPRIMARY KEY (batch_id)\n)')


def downgrade():
    for name in ('sync_checkpoints', 'sync_devices', 'sync_conflicts', 'sync_batches', 'sync_inbox', 'sync_outbox',
                 'sync_records', 'sync_mutations', 'sync_workspace'):
        op.drop_table(name)
