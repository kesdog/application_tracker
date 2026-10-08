"""Save recruiter contacts and optional posting deadlines."""
from alembic import op
import sqlalchemy as sa

revision = "0015_contact_and_deadline"
down_revision = "0014_application_intermediary"
branch_labels = None
depends_on = None


def upgrade():
    # Add the check inline: SQLite can add nullable columns without rebuilding
    # the parent table or disrupting foreign keys from application work.
    op.add_column("applications", sa.Column("contact_email", sa.String(320), nullable=True))
    op.add_column("applications", sa.Column("contact_name", sa.String(300), nullable=True))
    op.add_column("applications", sa.Column("deadline", sa.Date(), nullable=True))
    op.add_column("applications", sa.Column("deadline_kind", sa.String(19), sa.CheckConstraint("deadline_kind IN ('APPLICATION_CLOSING', 'FIRST_ROUND')", name="deadline_kind"), nullable=True))


def downgrade():
    for name in ("deadline_kind", "deadline", "contact_name", "contact_email"):
        op.drop_column("applications", name)
