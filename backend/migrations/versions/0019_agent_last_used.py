"""Track actual authenticated agent activity for draft task availability."""
from alembic import op
import sqlalchemy as sa

revision = "0019_agent_last_used"
down_revision = "0018_web_push"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_credentials", sa.Column("last_used_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("agent_credentials", "last_used_at")
