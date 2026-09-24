"""Add append-only L5/L6 observation matching results and candidates."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260906_0005"
down_revision = "20260906_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    outcome = postgresql.ENUM(
        "MATCHED",
        "AMBIGUOUS",
        "NEEDS_REVIEW",
        "NO_MATCH",
        name="observation_match_outcome",
        create_type=False,
    )
    outcome.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "observation_match_results",
        sa.Column("result_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_interpretations.observation_id"), nullable=False),
        sa.Column("outcome", outcome, nullable=False),
        sa.Column("ambiguity_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("best_score", sa.Float()),
        sa.Column("high_confidence_threshold", sa.Float(), nullable=False),
        sa.Column("ambiguous_score_delta", sa.Float(), nullable=False),
        sa.Column("no_match_threshold", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("best_score IS NULL OR best_score BETWEEN 0 AND 1", name="ck_observation_match_results_match_result_best_score_range"),
    )
    op.create_index("ix_observation_match_results_outcome_created", "observation_match_results", ["outcome", "created_at"])
    op.create_index("ix_observation_match_results_observation_created", "observation_match_results", ["observation_id", "created_at"])
    op.create_table(
        "observation_match_candidates",
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("observation_match_results.result_id"), nullable=False),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("activities.activity_id"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("contextual_score", sa.Float(), nullable=False),
        sa.Column("final_score", sa.Float(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.CheckConstraint("similarity_score BETWEEN 0 AND 1", name="ck_observation_match_candidates_observation_candidate_similarity_range"),
        sa.CheckConstraint("contextual_score BETWEEN 0 AND 1", name="ck_observation_match_candidates_observation_candidate_context_range"),
        sa.CheckConstraint("final_score BETWEEN 0 AND 1", name="ck_observation_match_candidates_observation_candidate_final_range"),
        sa.UniqueConstraint("result_id", "activity_id"),
    )
    op.create_index("ix_observation_match_candidates_result_rank", "observation_match_candidates", ["result_id", "rank"])


def downgrade() -> None:
    op.drop_index("ix_observation_match_candidates_result_rank", table_name="observation_match_candidates")
    op.drop_table("observation_match_candidates")
    op.drop_index("ix_observation_match_results_observation_created", table_name="observation_match_results")
    op.drop_index("ix_observation_match_results_outcome_created", table_name="observation_match_results")
    op.drop_table("observation_match_results")
    postgresql.ENUM(name="observation_match_outcome").drop(op.get_bind(), checkfirst=True)
