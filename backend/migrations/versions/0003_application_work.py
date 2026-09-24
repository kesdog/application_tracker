"""Add application notes, tasks, follow-ups, and nullable preference overrides."""
from alembic import op
import sqlalchemy as sa

revision = "0003_application_work"
down_revision = "0002_application_lifecycle"
branch_labels = None
depends_on = None


def identity():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=False),
    ]


def upgrade():
    op.add_column("applications", sa.Column("followup_delay_days", sa.Integer(), nullable=True))
    op.add_column("applications", sa.Column("max_followup_suggestions", sa.Integer(), nullable=True))
    op.create_table("notes", *identity(),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("type", sa.Enum("GENERAL", "ASSESSMENT", "EMAIL_DRAFT", "INTERVIEW", "AGENT", native_enum=False, create_constraint=True, name="note_type"), nullable=False),
        sa.Column("created_by", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(trim(content)) > 0", name="note_content_required"),
    )
    op.create_table("tasks", *identity(),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("due_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("status", sa.Enum("PENDING", "COMPLETED", "CANCELLED", native_enum=False, create_constraint=True, name="task_status"), nullable=False),
        sa.CheckConstraint("length(trim(title)) > 0", name="task_title_required"),
        sa.CheckConstraint("(status = 'COMPLETED' AND completed_at IS NOT NULL) OR (status != 'COMPLETED' AND completed_at IS NULL)", name="task_completion_consistent"),
    )
    op.create_table("followups", *identity(),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime()),
        sa.Column("status", sa.Enum("PENDING", "DRAFTED", "SENT", "CANCELLED", native_enum=False, create_constraint=True, name="followup_status"), nullable=False),
        sa.Column("template_reference", sa.String(2048)),
        sa.UniqueConstraint("application_id", "sequence_number", name="followup_sequence_unique"),
        sa.CheckConstraint("sequence_number > 0", name="followup_sequence_positive"),
        sa.CheckConstraint("(status = 'SENT' AND sent_at IS NOT NULL) OR (status != 'SENT' AND sent_at IS NULL)", name="followup_sent_consistent"),
    )
    for table in ("notes", "tasks", "followups"):
        op.create_index(f"ix_{table}_application_id", table, ["application_id"])


def downgrade():
    for table in ("followups", "tasks", "notes"):
        op.drop_table(table)
    with op.batch_alter_table("applications") as batch:
        batch.drop_column("max_followup_suggestions")
        batch.drop_column("followup_delay_days")
