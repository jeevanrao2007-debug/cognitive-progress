"""Create the CognitiveProgress MVP domain schema."""

from alembic import op

from app.database.base import Base
import app.database.models  # noqa: F401 - registers model metadata


revision = "20260904_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    initial_tables = [
        Base.metadata.tables[name]
        for name in (
            "projects", "schedules", "activities", "evidence", "activity_matches",
            "reconciliations", "evidence_conflicts", "planner_reviews", "audit_events",
        )
    ]
    Base.metadata.create_all(bind=op.get_bind(), tables=initial_tables)
    op.execute(
        """
        CREATE FUNCTION prevent_evidence_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Evidence records are append-only; create a new evidence record instead.';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER evidence_append_only
        BEFORE UPDATE OR DELETE ON evidence
        FOR EACH ROW EXECUTE FUNCTION prevent_evidence_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS evidence_append_only ON evidence")
    op.execute("DROP FUNCTION IF EXISTS prevent_evidence_mutation()")
    Base.metadata.drop_all(bind=op.get_bind())
