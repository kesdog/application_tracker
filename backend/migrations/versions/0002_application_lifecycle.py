"""Add posting state and enforce valid application outcomes."""
from alembic import op
import sqlalchemy as sa

revision = "0002_application_lifecycle"
down_revision = "0001_applications"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("applications") as batch:
        batch.add_column(sa.Column("posting_status", sa.String(7), nullable=False, server_default="UNKNOWN"))
        batch.add_column(sa.Column("posting_last_checked_at", sa.DateTime(), nullable=True))
        batch.create_check_constraint("posting_status", "posting_status IN ('UNKNOWN', 'LIVE', 'CLOSED')")
        batch.create_check_constraint("application_outcome_requires_closed", "outcome IS NULL OR status = 'CLOSED'")


def downgrade():
    with op.batch_alter_table("applications") as batch:
        batch.drop_constraint("application_outcome_requires_closed", type_="check")
        batch.drop_constraint("posting_status", type_="check")
        batch.drop_column("posting_last_checked_at")
        batch.drop_column("posting_status")
