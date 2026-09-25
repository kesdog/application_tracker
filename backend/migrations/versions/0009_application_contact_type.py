"""Record the selected application contact method."""
from alembic import op
import sqlalchemy as sa


revision = "0009_application_contact_type"
down_revision = "0008_phone_and_followup_channels"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("applications", sa.Column("contact_type", sa.String(5), nullable=False, server_default="EMAIL"))


def downgrade():
    op.drop_column("applications", "contact_type")
