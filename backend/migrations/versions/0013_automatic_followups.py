"""Add automatic follow-up markers."""

from alembic import op
import sqlalchemy as sa


revision = "0013_automatic_followups"
down_revision = "0012_posting_diagnostics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("followups") as batch:
        batch.add_column(sa.Column("is_automatic", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("followups") as batch:
        batch.drop_column("is_automatic")
