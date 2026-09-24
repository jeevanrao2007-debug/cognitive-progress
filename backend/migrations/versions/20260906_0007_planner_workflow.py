"""Add internal schedule-update provenance and planner review links."""

from alembic import op


revision = "20260906_0007"
down_revision = "20260906_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS actual_start DATE")
    op.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS actual_end DATE")
    op.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS actual_progress DOUBLE PRECISION")
    op.execute("ALTER TABLE planner_reviews ADD COLUMN IF NOT EXISTS reconciliation_id UUID REFERENCES reconciliations(reconciliation_id)")
    op.execute("ALTER TABLE planner_reviews ADD COLUMN IF NOT EXISTS selected_activity_id UUID REFERENCES activities(activity_id)")
    op.execute("ALTER TABLE planner_reviews ADD COLUMN IF NOT EXISTS reviewer VARCHAR(255)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS schedule_updates (
            update_id UUID PRIMARY KEY,
            activity_id UUID NOT NULL REFERENCES activities(activity_id),
            reconciliation_id UUID REFERENCES reconciliations(reconciliation_id),
            review_id UUID REFERENCES planner_reviews(review_id),
            previous_value JSONB NOT NULL,
            new_value JSONB NOT NULL,
            reason TEXT NOT NULL,
            evidence JSONB NOT NULL,
            decision_source VARCHAR(100) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_schedule_updates_activity_created ON schedule_updates(activity_id, created_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_schedule_updates_activity_created")
    op.execute("DROP TABLE IF EXISTS schedule_updates")
    op.drop_column("planner_reviews", "reviewer")
    op.drop_column("planner_reviews", "selected_activity_id")
    op.drop_column("planner_reviews", "reconciliation_id")
    op.drop_column("activities", "actual_progress")
    op.drop_column("activities", "actual_end")
    op.drop_column("activities", "actual_start")
