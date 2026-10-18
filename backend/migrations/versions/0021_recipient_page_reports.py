"""Reusable extracted page reports and configurable research budgets."""
from alembic import op
import sqlalchemy as sa

revision = '0021_recipient_page_reports'
down_revision = '0020_recipient_discovery'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('applications', sa.Column('recipient_page_limit', sa.Integer(), nullable=True))
    op.add_column('recipient_discovery', sa.Column('page_limit', sa.Integer(), nullable=False, server_default='6'))
    op.add_column('recipient_discovery', sa.Column('refresh_pages', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('recipient_discovery', sa.Column('page_counts', sa.JSON(), nullable=False, server_default='{}'))
    op.create_table('recipient_page_reports',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('url', sa.String(2048), nullable=False, unique=True),
        sa.Column('resolved_url', sa.String(2048)),
        sa.Column('report', sa.JSON(), nullable=True), sa.Column('fetched_at', sa.DateTime()),
        sa.Column('lease_id', sa.String(36)), sa.Column('lease_until', sa.DateTime()))
    op.create_index('ix_recipient_page_reports_resolved_url', 'recipient_page_reports', ['resolved_url'])
    op.create_table('recipient_page_uses',
        sa.Column('application_id', sa.String(36), sa.ForeignKey('applications.id'), primary_key=True),
        sa.Column('report_id', sa.String(64), sa.ForeignKey('recipient_page_reports.id'), primary_key=True),
        sa.Column('context', sa.JSON(), nullable=False), sa.Column('used_at', sa.DateTime(), nullable=False))


def downgrade():
    op.drop_table('recipient_page_uses')
    op.drop_table('recipient_page_reports')
    op.drop_column('recipient_discovery', 'refresh_pages')
    op.drop_column('recipient_discovery', 'page_counts')
    op.drop_column('recipient_discovery', 'page_limit')
    op.drop_column('applications', 'recipient_page_limit')
