"""Separate hosted human sessions from agent credentials."""
from alembic import op
import sqlalchemy as sa

revision = "0017_human_sessions"
down_revision = "0016_prepared_followups"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("human_sessions", sa.Column("token_hash", sa.String(64), primary_key=True),
                    sa.Column("credential_fingerprint", sa.String(64), nullable=False),
                    sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("expires_at", sa.DateTime(), nullable=False))
    op.create_index("ix_human_sessions_expires_at", "human_sessions", ["expires_at"])
    op.create_table("login_attempts", sa.Column("key", sa.String(64), primary_key=True),
                    sa.Column("window_started_at", sa.DateTime(), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False))


def downgrade():
    op.drop_table("login_attempts")
    op.drop_table("human_sessions")
