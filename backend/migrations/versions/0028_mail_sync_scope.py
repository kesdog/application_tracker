"""Persist the user-selected lower bound for first-time Gmail scans."""
from alembic import op
import sqlalchemy as sa

revision = '0028_mail_sync_scope'
down_revision = '0027_mail_sync_boundary'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('mail_sync_scopes',
                    sa.Column('account', sa.String(64), primary_key=True),
                    sa.Column('scan_after', sa.Integer(), nullable=False),
                    sa.Column('lookback_months', sa.Integer(), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=False))


def downgrade():
    op.drop_table('mail_sync_scopes')
