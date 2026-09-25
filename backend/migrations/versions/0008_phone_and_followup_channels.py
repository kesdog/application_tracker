"""Add normalized application phone numbers and follow-up channels."""
from alembic import op
import sqlalchemy as sa


revision = "0008_phone_and_followup_channels"
down_revision = "0007_agent_access"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("applications", sa.Column("phone_number", sa.String(20)))
    op.add_column("followups", sa.Column("channel", sa.String(5), nullable=False, server_default="EMAIL"))


def downgrade():
    op.drop_column("followups", "channel")
    op.drop_column("applications", "phone_number")
