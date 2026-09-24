"""Add source import status and metadata tracking."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260904_0002"
down_revision = "20260904_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'site_diary'")
    import_kind = postgresql.ENUM("schedule", "evidence", name="import_kind", create_type=False)
    import_status = postgresql.ENUM("processing", "completed", "failed", name="import_status", create_type=False)
    import_kind.create(op.get_bind(), checkfirst=True)
    import_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "imported_sources",
        sa.Column("import_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.project_id"), nullable=False),
        sa.Column("import_kind", import_kind, nullable=False),
        sa.Column("source_type", postgresql.ENUM(name="source_type", create_type=False), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("stored_reference", sa.String(length=2048), nullable=False),
        sa.Column("status", import_status, nullable=False),
        sa.Column("records_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("validation_errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_imported_sources_project_status", "imported_sources", ["project_id", "status"])
    op.create_index("ix_imported_sources_project_created", "imported_sources", ["project_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_imported_sources_project_created", table_name="imported_sources")
    op.drop_index("ix_imported_sources_project_status", table_name="imported_sources")
    op.drop_table("imported_sources")
    op.execute("DROP TYPE import_status")
    op.execute("DROP TYPE import_kind")
