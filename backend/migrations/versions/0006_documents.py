"""Add application CV and cover-letter documents."""
from alembic import op
import sqlalchemy as sa


revision = "0006_documents"
down_revision = "0005_activity_audit"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "application_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column(
            "type",
            sa.Enum("CV", "COVER_LETTER", native_enum=False, create_constraint=True, name="document_type"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("storage_path", sa.String(2048)),
        sa.Column("external_reference", sa.String(2048)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "(storage_path IS NOT NULL AND external_reference IS NULL) OR "
            "(storage_path IS NULL AND external_reference IS NOT NULL)",
            name="document_upload_or_reference",
        ),
        sa.CheckConstraint("length(trim(filename)) > 0", name="document_filename_required"),
    )
    op.create_index("ix_application_documents_application_id", "application_documents", ["application_id"])


def downgrade():
    op.drop_table("application_documents")
