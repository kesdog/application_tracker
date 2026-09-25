"""Add agent credential and UI invalidation events."""
from alembic import op
import sqlalchemy as sa


revision = "0007_agent_access"
down_revision = "0006_documents"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "invalidation_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("topic", sa.String(80), nullable=False),
        sa.Column("application_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("invalidation_events")
    op.drop_table("agent_credentials")
