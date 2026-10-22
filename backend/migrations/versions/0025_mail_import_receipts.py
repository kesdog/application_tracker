"""Account-scoped deduplication and review evidence for application mail sync."""
from alembic import op
import sqlalchemy as sa

revision = '0025_mail_import_receipts'
down_revision = '0024_sync_work_queue'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('mail_import_receipts',
        sa.Column('account', sa.String(64), primary_key=True),
        sa.Column('message_id', sa.String(64), primary_key=True),
        sa.Column('thread_id', sa.String(64), nullable=False),
        sa.Column('application_id', sa.String(36), sa.ForeignKey('applications.id')),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('subject', sa.String(500), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('message_at', sa.DateTime()),
        sa.Column('lifecycle_applied', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index('ix_mail_import_receipts_thread_id', 'mail_import_receipts', ['thread_id'])
    op.create_index('ix_mail_import_receipts_application_id', 'mail_import_receipts', ['application_id'])


def downgrade():
    op.drop_table('mail_import_receipts')
