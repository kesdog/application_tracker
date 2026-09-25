"""Add timeline, audit, undo state, and soft deletion."""
from alembic import op
import sqlalchemy as sa

revision = "0005_activity_audit"
down_revision = "0004_interviews"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("applications", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_table(
        "timeline_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("actor_type", sa.Enum("HUMAN", "AGENT", "SYSTEM", native_enum=False, create_constraint=True, name="actor_type"), nullable=False),
        sa.Column("actor_reference", sa.String(300)),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "audit_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("field", sa.String(100)),
        sa.Column("previous_value", sa.JSON()),
        sa.Column("new_value", sa.JSON()),
        sa.Column("actor_type", sa.Enum("HUMAN", "AGENT", "SYSTEM", native_enum=False, create_constraint=True, name="audit_actor_type"), nullable=False),
        sa.Column("actor_reference", sa.String(300)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reversible", sa.Boolean(), nullable=False),
        sa.Column("undone_at", sa.DateTime()),
    )
    op.create_index("ix_timeline_events_application_id", "timeline_events", ["application_id"])
    op.create_index("ix_timeline_events_event_type", "timeline_events", ["event_type"])
    op.create_index("ix_timeline_events_created_at", "timeline_events", ["created_at"])
    op.create_index("ix_audit_entries_application_id", "audit_entries", ["application_id"])
    op.create_index("ix_audit_entries_created_at", "audit_entries", ["created_at"])


def downgrade():
    op.drop_table("audit_entries")
    op.drop_table("timeline_events")
    with op.batch_alter_table("applications") as batch:
        batch.drop_column("deleted_at")
