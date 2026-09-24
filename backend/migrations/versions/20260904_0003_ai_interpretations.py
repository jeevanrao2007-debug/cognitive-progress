"""Add append-only AI interpretation and normalization records."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260904_0003"
down_revision = "20260904_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    activity_status = postgresql.ENUM(name="activity_status", create_type=False)
    op.create_table(
        "evidence_interpretations",
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence.evidence_id"), nullable=False),
        sa.Column("discipline", sa.String(length=100)),
        sa.Column("location", sa.String(length=255)),
        sa.Column("activity_description", sa.Text(), nullable=False),
        sa.Column("status", activity_status, nullable=False),
        sa.Column("actual_start", sa.Date()),
        sa.Column("actual_end", sa.Date()),
        sa.Column("progress", sa.Float()),
        sa.Column("additional_context", sa.Text()),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=255)),
        sa.Column("raw_provider_response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("progress IS NULL OR progress BETWEEN 0 AND 100", name="ck_evidence_interpretations_interpretation_progress_range"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_evidence_interpretations_interpretation_confidence_range"),
    )
    op.create_index("ix_evidence_interpretations_evidence_created", "evidence_interpretations", ["evidence_id", "created_at"])
    op.create_table(
        "activity_normalizations",
        sa.Column("normalization_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_interpretations.observation_id"), nullable=False),
        sa.Column("normalized_activity_description", sa.Text(), nullable=False),
        sa.Column("normalized_discipline", sa.String(length=100)),
        sa.Column("normalized_location", sa.String(length=255)),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=255)),
        sa.Column("raw_provider_response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_activity_normalizations_normalization_confidence_range"),
    )
    op.create_index("ix_activity_normalizations_observation_created", "activity_normalizations", ["observation_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_activity_normalizations_observation_created", table_name="activity_normalizations")
    op.drop_table("activity_normalizations")
    op.drop_index("ix_evidence_interpretations_evidence_created", table_name="evidence_interpretations")
    op.drop_table("evidence_interpretations")
