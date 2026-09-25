"""Store completed agent create-operation responses for safe retries."""
from alembic import op
import sqlalchemy as sa


revision = "0011_agent_idempotency"
down_revision = "0010_manual_timeline_entries"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_idempotency_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", "operation", "idempotency_key", name="agent_idempotency_key_unique"),
    )
    op.create_index("ix_agent_idempotency_records_token_hash", "agent_idempotency_records", ["token_hash"])
    op.create_index("ix_agent_idempotency_records_expires_at", "agent_idempotency_records", ["expires_at"])


def downgrade():
    op.drop_index("ix_agent_idempotency_records_expires_at", table_name="agent_idempotency_records")
    op.drop_index("ix_agent_idempotency_records_token_hash", table_name="agent_idempotency_records")
    op.drop_table("agent_idempotency_records")
