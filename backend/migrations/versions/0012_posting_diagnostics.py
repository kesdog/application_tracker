"""Persist explainable deterministic posting-check diagnostics."""
from alembic import op
import sqlalchemy as sa


revision = "0012_posting_diagnostics"
down_revision = "0011_agent_idempotency"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("applications", sa.Column("posting_http_status", sa.Integer(), nullable=True))
    op.add_column("applications", sa.Column("posting_final_url", sa.String(length=2048), nullable=True))
    op.add_column("applications", sa.Column("posting_check_method", sa.String(length=32), nullable=True))
    op.add_column("applications", sa.Column("posting_check_reason", sa.String(length=500), nullable=True))
    op.add_column("applications", sa.Column("posting_check_failures", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("applications", "posting_check_failures")
    op.drop_column("applications", "posting_check_reason")
    op.drop_column("applications", "posting_check_method")
    op.drop_column("applications", "posting_final_url")
    op.drop_column("applications", "posting_http_status")
