"""Preserve the original evidence seen by every AI interpretation."""

import sqlalchemy as sa
from alembic import op


revision = "20260906_0004"
down_revision = "20260904_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evidence_interpretations",
        sa.Column("original_evidence", sa.Text(), nullable=True),
    )
    op.add_column(
        "evidence_interpretations",
        sa.Column("original_reference", sa.String(length=2048), nullable=True),
    )
    op.execute(
        "UPDATE evidence_interpretations "
        "SET original_evidence = COALESCE(evidence.raw_text, evidence.raw_reference, ''), "
        "original_reference = evidence.raw_reference "
        "FROM evidence "
        "WHERE evidence_interpretations.evidence_id = evidence.evidence_id"
    )
    op.alter_column("evidence_interpretations", "original_evidence", nullable=False)


def downgrade() -> None:
    op.drop_column("evidence_interpretations", "original_reference")
    op.drop_column("evidence_interpretations", "original_evidence")
