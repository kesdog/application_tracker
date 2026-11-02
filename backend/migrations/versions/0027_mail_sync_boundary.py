"""Per-account completed Gmail scan boundaries."""
from alembic import op
import sqlalchemy as sa

revision = '0027_mail_sync_boundary'
down_revision = '0026_import_batches'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('mail_sync_boundaries',
                    sa.Column('account', sa.String(64), primary_key=True),
                    sa.Column('checked_through', sa.Integer(), nullable=False),
                    sa.Column('updated_at', sa.DateTime(), nullable=False))


def downgrade():
    op.drop_table('mail_sync_boundaries')
