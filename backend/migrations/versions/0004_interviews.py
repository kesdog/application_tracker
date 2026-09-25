"""Add interviews as application work items."""
from alembic import op
import sqlalchemy as sa

revision = "0004_interviews"
down_revision = "0003_application_work"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "interviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("type", sa.Enum("PHONE", "HR", "TECHNICAL", "ONSITE", "FINAL", "OTHER", native_enum=False, create_constraint=True, name="interview_type"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("duration", sa.Integer()),
        sa.Column("location", sa.String(300)),
        sa.Column("meeting_url", sa.String(2048)),
        sa.Column("interviewer", sa.String(300)),
        sa.Column("email_reference", sa.String(2048)),
        sa.Column("notes", sa.Text()),
        sa.Column("result", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("duration IS NULL OR duration > 0", name="interview_duration_positive"),
    )
    op.create_index("ix_interviews_application_id", "interviews", ["application_id"])
    op.create_index("ix_interviews_scheduled_at", "interviews", ["scheduled_at"])


def downgrade():
    op.drop_table("interviews")
