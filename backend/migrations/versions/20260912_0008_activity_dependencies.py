"""Add activity dependencies table for schedule execution order relationships."""

from alembic import op
import sqlalchemy as sa


revision = "20260912_0008"
down_revision = "20260906_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS activity_dependencies (
            dependency_id UUID PRIMARY KEY,
            project_id UUID NOT NULL REFERENCES projects(project_id),
            predecessor_id UUID NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE,
            successor_id UUID NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE,
            dependency_type VARCHAR(50) NOT NULL DEFAULT 'finish_to_start',
            lag_days INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_dependency_pair UNIQUE (predecessor_id, successor_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_dependencies_successor ON activity_dependencies(successor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_dependencies_predecessor ON activity_dependencies(predecessor_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_dependencies_predecessor")
    op.execute("DROP INDEX IF EXISTS ix_dependencies_successor")
    op.execute("DROP TABLE IF EXISTS activity_dependencies")
