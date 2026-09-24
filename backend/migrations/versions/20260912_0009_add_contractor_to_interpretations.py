"""Add contractor column to evidence interpretations."""

from alembic import op
import sqlalchemy as sa


revision = "20260912_0009"
down_revision = "20260912_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evidence_interpretations",
        sa.Column("contractor", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evidence_interpretations", "contractor")
