"""Persist recipient queue interruption and manual priority."""
from alembic import op
import sqlalchemy as sa

revision = '0030_recipient_queue_controls'
down_revision = '0029_followup_message_versions'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('recipient_discovery', sa.Column('priority', sa.Integer(), nullable=False, server_default='0'))
    op.create_table('recipient_queue_control',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('paused', sa.Boolean(), nullable=False),
                    sa.Column('updated_at', sa.DateTime(), nullable=False))


def downgrade():
    op.drop_table('recipient_queue_control')
    op.drop_column('recipient_discovery', 'priority')
