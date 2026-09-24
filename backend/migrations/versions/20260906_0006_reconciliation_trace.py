"""Add deterministic reconciliation trace data and decision states."""

from alembic import op


revision = "20260906_0006"
down_revision = "20260906_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for value in ("AUTO_ACCEPT", "PLANNER_REVIEW", "REJECT", "NO_DECISION"):
        op.execute(f"ALTER TYPE reconciliation_decision ADD VALUE IF NOT EXISTS '{value}'")
    # The initial MVP migration uses metadata to create this pre-existing table,
    # so IF NOT EXISTS also keeps a fresh full migration chain safe.
    op.execute("ALTER TABLE reconciliations ADD COLUMN IF NOT EXISTS supporting_evidence JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE reconciliations ADD COLUMN IF NOT EXISTS conflicting_evidence JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE reconciliations ADD COLUMN IF NOT EXISTS recommended_action TEXT NOT NULL DEFAULT 'Review reconciliation evidence.'")


def downgrade() -> None:
    op.drop_column("reconciliations", "recommended_action")
    op.drop_column("reconciliations", "conflicting_evidence")
    op.drop_column("reconciliations", "supporting_evidence")
