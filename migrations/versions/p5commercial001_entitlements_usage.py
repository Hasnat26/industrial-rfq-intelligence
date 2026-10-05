"""Commercial subscription entitlement and usage metering foundation."""

import sqlalchemy as sa
from alembic import op

revision = "p5commercial001"
down_revision = "p4cost001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("plan_key", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", name="uq_organization_subscriptions_org"),
    )
    op.create_index(
        "ix_organization_subscriptions_organization_id",
        "organization_subscriptions",
        ["organization_id"],
    )
    op.create_table(
        "usage_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("metric", sa.String(length=50), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
    )
    for name, column in [("organization_id", "organization_id"), ("metric", "metric"), ("recorded_at", "recorded_at")]:
        op.create_index(f"ix_usage_records_{name}", "usage_records", [column])


def downgrade() -> None:
    for name in ["recorded_at", "metric", "organization_id"]:
        op.drop_index(f"ix_usage_records_{name}", table_name="usage_records")
    op.drop_table("usage_records")
    op.drop_index(
        "ix_organization_subscriptions_organization_id",
        table_name="organization_subscriptions",
    )
    op.drop_table("organization_subscriptions")
