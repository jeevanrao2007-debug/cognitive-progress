"""Add execution records and deviations for Phase 5 execution memory."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260913_0010"
down_revision = "20260912_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add delay columns to evidence_interpretations
    op.add_column("evidence_interpretations", sa.Column("delay_cause", sa.Text(), nullable=True))
    op.add_column("evidence_interpretations", sa.Column("delay_category", sa.String(length=50), nullable=True))
    op.add_column("evidence_interpretations", sa.Column("constraint", sa.Text(), nullable=True))
    op.add_column("evidence_interpretations", sa.Column("impact_description", sa.Text(), nullable=True))
    op.add_column("evidence_interpretations", sa.Column("delay_confidence", sa.Float(), nullable=True))

    # Create execution_records
    op.create_table(
        "execution_records",
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column("external_activity_id", sa.String(length=255), nullable=False),
        sa.Column("activity_name", sa.Text(), nullable=False),
        sa.Column("discipline", sa.String(length=100), nullable=True),
        sa.Column("contractor", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("planned_start", sa.Date(), nullable=True),
        sa.Column("planned_finish", sa.Date(), nullable=True),
        sa.Column("actual_start", sa.Date(), nullable=True),
        sa.Column("actual_end", sa.Date(), nullable=True),
        sa.Column("planned_duration_days", sa.Float(), nullable=True),
        sa.Column("actual_duration_days", sa.Float(), nullable=True),
        sa.Column("variance_days", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("percent_complete", sa.Float(), nullable=True),
        sa.Column("reconciliation_decision", sa.String(length=50), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence_reference", sa.String(length=2048), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dependency_status", sa.String(length=50), nullable=True),
        sa.Column("deviation_type", sa.String(length=50), nullable=False),
        sa.Column("delay_cause", sa.Text(), nullable=True),
        sa.Column("delay_category", sa.String(length=50), nullable=True),
        sa.Column("delay_source_evidence", sa.Text(), nullable=True),
        sa.Column("delay_confidence", sa.Float(), nullable=True),
        sa.Column("planner_override", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("planner_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.activity_id"]),
        sa.PrimaryKeyConstraint("record_id"),
    )
    op.create_index("ix_execution_records_project_activity", "execution_records", ["project_id", "activity_id"])
    op.create_index("ix_execution_records_discipline", "execution_records", ["discipline"])
    op.create_index("ix_execution_records_contractor", "execution_records", ["contractor"])
    op.create_index("ix_execution_records_deviation", "execution_records", ["deviation_type"])
    op.create_index("ix_execution_records_delay_category", "execution_records", ["delay_category"])

    # Create execution_deviations
    op.create_table(
        "execution_deviations",
        sa.Column("deviation_id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("deviation_type", sa.String(length=50), nullable=False),
        sa.Column("metric_days", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["record_id"], ["execution_records.record_id"]),
        sa.PrimaryKeyConstraint("deviation_id"),
    )
    op.create_index("ix_deviations_record_type", "execution_deviations", ["record_id", "deviation_type"])


def downgrade() -> None:
    op.drop_table("execution_deviations")
    op.drop_table("execution_records")
    op.drop_column("evidence_interpretations", "delay_confidence")
    op.drop_column("evidence_interpretations", "impact_description")
    op.drop_column("evidence_interpretations", "constraint")
    op.drop_column("evidence_interpretations", "delay_category")
    op.drop_column("evidence_interpretations", "delay_cause")
