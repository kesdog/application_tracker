"""Create the initial applications table."""
from alembic import op
import sqlalchemy as sa

revision = "0001_applications"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "applications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_title", sa.String(300), nullable=False),
        sa.Column("company", sa.String(300), nullable=False),
        sa.Column("date_applied", sa.Date(), nullable=False),
        sa.Column("job_url", sa.String(2048)),
        sa.Column("email_reference", sa.String(2048)),
        sa.Column("location", sa.String(300)),
        sa.Column("remote_policy", sa.String(300)),
        sa.Column("contract_type", sa.String(300)),
        sa.Column("source", sa.String(300)),
        sa.Column("description", sa.Text()),
        sa.Column("requirements", sa.Text()),
        sa.Column("status", sa.Enum("SUBMITTED", "INTERVIEW", "CLOSED", native_enum=False, create_constraint=True, name="application_status"), nullable=False, server_default="SUBMITTED"),
        sa.Column("outcome", sa.Enum("SUCCESSFUL", "UNSUCCESSFUL", "WITHDRAWN", "JOB_CANCELLED", "GHOSTED", native_enum=False, create_constraint=True, name="application_outcome")),
        sa.CheckConstraint("length(trim(coalesce(job_url, ''))) > 0 OR length(trim(coalesce(email_reference, ''))) > 0", name="application_source_required"),
        sa.CheckConstraint("length(trim(job_title)) > 0 AND length(trim(company)) > 0", name="application_title_company_required"),
    )


def downgrade():
    op.drop_table("applications")
