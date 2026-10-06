"""Separate the employer from the organization forwarding a CV."""
from alembic import op
import sqlalchemy as sa

revision = "0014_application_intermediary"
down_revision = "0013_automatic_followups"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("applications", sa.Column("intermediary", sa.String(300), nullable=True))


def downgrade():
    op.drop_column("applications", "intermediary")
