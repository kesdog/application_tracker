"""Persist templates, prepared messages and reminder notices without losing legacy work."""
from alembic import op
import sqlalchemy as sa

revision = "0016_prepared_followups"
down_revision = "0015_contact_and_deadline"
branch_labels = None
depends_on = None


def upgrade():
    # Native ADD COLUMN avoids dropping the parent table with live child FKs.
    op.add_column("applications", sa.Column("followup_instructions", sa.Text(), nullable=False, server_default=""))
    op.add_column("applications", sa.Column("followup_customization", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("applications", sa.Column("followup_paused", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    # Widen the constraint before converting stored legacy values.
    with op.batch_alter_table("followups") as batch:
        batch.drop_constraint("followup_status", type_="check")
        batch.create_check_constraint("followup_status", "status IN ('PREPARED','READY','SENT','CANCELLED','PENDING','DRAFTED')")
        for name in ("subject", "body", "instructions"):
            batch.add_column(sa.Column(name, sa.Text(), nullable=False, server_default=""))
        for name in ("template_snapshot", "variable_snapshot", "customization"):
            batch.add_column(sa.Column(name, sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("approved_revision", sa.Integer(), nullable=True))
        for name in ("prepared_at", "snoozed_until", "archived_at"):
            batch.add_column(sa.Column(name, sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        batch.add_column(sa.Column("parent_followup_id", sa.String(36), nullable=True))
    op.execute("UPDATE followups SET archived_at = CURRENT_TIMESTAMP WHERE status = 'CANCELLED'")
    op.execute("UPDATE followups SET status = 'PREPARED' WHERE status IN ('PENDING','DRAFTED','CANCELLED')")
    with op.batch_alter_table("followups") as batch:
        batch.drop_constraint("followup_status", type_="check")
        batch.create_check_constraint("followup_status", "status IN ('PREPARED','READY','SENT','CANCELLED')")
    op.create_table("general_settings", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("values", sa.JSON(), nullable=False), sa.Column("revision", sa.Integer(), nullable=False),
                    sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("followup_notices", sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("followup_id", sa.String(36), sa.ForeignKey("followups.id"), nullable=False),
                    sa.Column("schedule_key", sa.String(160), nullable=False), sa.Column("due_at", sa.DateTime(), nullable=False),
                    sa.Column("state", sa.String(30), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False),
                    sa.Column("read_at", sa.DateTime()),
                    sa.UniqueConstraint("followup_id", "schedule_key", name="followup_notice_unique"))
    op.create_index("ix_followup_notices_followup_id", "followup_notices", ["followup_id"])


def downgrade():
    op.drop_table("followup_notices")
    op.drop_table("general_settings")
    with op.batch_alter_table("followups") as batch:
        batch.drop_constraint("followup_status", type_="check")
    op.execute("UPDATE followups SET status = CASE WHEN archived_at IS NOT NULL THEN 'CANCELLED' WHEN status = 'READY' THEN 'DRAFTED' WHEN status = 'PREPARED' THEN 'PENDING' ELSE status END")
    with op.batch_alter_table("followups") as batch:
        batch.create_check_constraint("followup_status", "status IN ('PENDING','DRAFTED','SENT','CANCELLED')")
        for name in ("subject", "body", "instructions", "template_snapshot", "variable_snapshot", "customization", "revision", "approved_revision", "prepared_at", "updated_at", "snoozed_until", "archived_at", "parent_followup_id"):
            batch.drop_column(name)
    # Native DROP COLUMN preserves child foreign keys (SQLite >= 3.35).
    for name in ("followup_instructions", "followup_customization", "followup_paused"):
        op.drop_column("applications", name)
