"""Add commercial reconciliation run audit ledger."""

import sqlalchemy as sa
from alembic import op

revision = "p5commercial004"
down_revision = "p5commercial003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commercial_reconciliation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rolled_over", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("commercial_reconciliation_runs")
