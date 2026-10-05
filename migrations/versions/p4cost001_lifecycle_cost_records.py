"""Lifecycle cost input migration."""

import sqlalchemy as sa
from alembic import op

revision = "p4cost001"
down_revision = "p4asset001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lifecycle_cost_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.String(length=200), nullable=False),
        sa.Column("package_id", sa.Integer(), sa.ForeignKey("procurement_packages.id"), nullable=False),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("lifecycle_events.id"), nullable=True),
        sa.Column("cost_type", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("cost_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, column in [
        ("asset_id", "asset_id"),
        ("package_id", "package_id"),
        ("event_id", "event_id"),
        ("cost_type", "cost_type"),
        ("cost_date", "cost_date"),
        ("created_by_user_id", "created_by_user_id"),
    ]:
        op.create_index(f"ix_lifecycle_cost_records_{name}", "lifecycle_cost_records", [column])


def downgrade() -> None:
    for name in ["created_by_user_id", "cost_date", "cost_type", "event_id", "package_id", "asset_id"]:
        op.drop_index(f"ix_lifecycle_cost_records_{name}", table_name="lifecycle_cost_records")
    op.drop_table("lifecycle_cost_records")
