"""Replay receipts for reviewed spreadsheet imports."""
from alembic import op
import sqlalchemy as sa

revision = '0026_import_batches'
down_revision = '0025_mail_import_receipts'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('import_batches', sa.Column('id', sa.String(64), primary_key=True),
                    sa.Column('result', sa.JSON(), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False))


def downgrade():
    op.drop_table('import_batches')
