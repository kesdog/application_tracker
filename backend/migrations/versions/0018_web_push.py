"""Persist device opt-ins and the notification delivery outbox."""
from alembic import op
import sqlalchemy as sa

revision = "0018_web_push"
down_revision = "0017_human_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("push_devices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("endpoint_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("endpoint", sa.Text(), nullable=False), sa.Column("keys", sa.JSON(), nullable=False),
        sa.Column("label", sa.String(80), nullable=False), sa.Column("key_fingerprint", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False), sa.Column("reason", sa.String(80)),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("push_deliveries",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("device_id", sa.String(36), sa.ForeignKey("push_devices.id"), nullable=False),
        sa.Column("batch_key", sa.String(100), nullable=False), sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("notice_ids", sa.JSON(), nullable=False), sa.Column("state", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False), sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("lease_until", sa.DateTime()), sa.Column("lease_token", sa.String(36)),
        sa.Column("last_status", sa.Integer()), sa.Column("last_error", sa.String(120)),
        sa.Column("accepted_at", sa.DateTime()), sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("device_id", "batch_key", name="push_batch_unique"))
    for name in ("device_id", "state", "next_attempt_at"):
        op.create_index("ix_push_deliveries_" + name, "push_deliveries", [name])


def downgrade():
    op.drop_table("push_deliveries")
    op.drop_table("push_devices")
