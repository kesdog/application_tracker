"""Recipient choices and a durable bounded discovery queue."""
from alembic import op
import sqlalchemy as sa

revision = '0020_recipient_discovery'
down_revision = '0019_agent_last_used'
branch_labels = None
depends_on = None


def upgrade():
    for name, length in [('recipient_email',320), ('recipient_name',300), ('recipient_source_url',2048)]:
        op.add_column('followups', sa.Column(name, sa.String(length), nullable=True))
    op.execute("""UPDATE followups SET
        recipient_email = (SELECT contact_email FROM applications WHERE applications.id = followups.application_id),
        recipient_name = (SELECT contact_name FROM applications WHERE applications.id = followups.application_id)
        WHERE channel != 'PHONE' AND EXISTS (
            SELECT 1 FROM applications WHERE applications.id = followups.application_id
            AND length(trim(coalesce(contact_email, ''))) > 0)""")
    op.create_table('recipient_discovery',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('application_id',sa.String(36),sa.ForeignKey('applications.id'),nullable=False,unique=True),
        sa.Column('state',sa.String(20),nullable=False), sa.Column('context',sa.JSON(),nullable=False),
        sa.Column('requested_at',sa.DateTime(),nullable=False),sa.Column('started_at',sa.DateTime()),
        sa.Column('completed_at',sa.DateTime()),sa.Column('lease_until',sa.DateTime()),sa.Column('lease_id',sa.String(36)),
        sa.Column('attempts',sa.Integer(),nullable=False),sa.Column('error',sa.Text()),sa.Column('warnings',sa.JSON(),nullable=False))
    op.create_index('ix_recipient_discovery_state','recipient_discovery',['state'])
    op.create_table('recipient_candidates',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('application_id',sa.String(36),sa.ForeignKey('applications.id'),nullable=False),
        sa.Column('context',sa.JSON(),nullable=False),sa.Column('value',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False))
    op.create_index('ix_recipient_candidates_application_id','recipient_candidates',['application_id'])


def downgrade():
    op.drop_table('recipient_candidates')
    op.drop_table('recipient_discovery')
    for name in ('recipient_source_url','recipient_name','recipient_email'):
        op.drop_column('followups',name)
