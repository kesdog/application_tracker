"""Allow manually timestamped timeline entries."""


revision = "0010_manual_timeline_entries"
down_revision = "0009_application_contact_type"
branch_labels = None
depends_on = None


def upgrade():
    # Manual entries reuse the existing timeline event shape. No schema change is needed.
    pass


def downgrade():
    pass
