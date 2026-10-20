"""One Google connection, draft receipts and application edit revisions."""
from alembic import op
import sqlalchemy as sa

revision = '0022_shared_google_agent'
down_revision = '0021_recipient_page_reports'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('applications', sa.Column('revision', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('agent_idempotency_records', sa.Column('request_hash', sa.String(64)))
    op.add_column('audit_entries', sa.Column('request_id', sa.String(36)))
    op.add_column('audit_entries', sa.Column('client_label', sa.String(20)))
    op.create_table('external_connections',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('issuer', sa.String(255)), sa.Column('subject', sa.String(255)),
        sa.Column('email', sa.String(320)), sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(40), nullable=False), sa.Column('secret_reference', sa.String(100)),
        sa.Column('generation', sa.Integer(), nullable=False), sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('verified_at', sa.DateTime()), sa.CheckConstraint('id = 1', name='single_google_connection'))
    op.create_table('mail_draft_operations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('application_id', sa.String(36), sa.ForeignKey('applications.id'), nullable=False),
        sa.Column('followup_id', sa.String(36), sa.ForeignKey('followups.id'), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False), sa.Column('result', sa.JSON()),
        sa.Column('created_at', sa.DateTime(), nullable=False))


def downgrade():
    op.drop_table('mail_draft_operations')
    op.drop_table('external_connections')
    op.drop_column('agent_idempotency_records', 'request_hash')
    op.drop_column('audit_entries', 'client_label')
    op.drop_column('audit_entries', 'request_id')
    op.drop_column('applications', 'revision')
