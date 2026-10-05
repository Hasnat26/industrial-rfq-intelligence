"""Add idempotent billing webhook receipt ledger."""

import sqlalchemy as sa
from alembic import op

revision = "p5commercial003"
down_revision = "p5commercial002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("external_event_id", sa.String(length=200), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "provider",
            "external_event_id",
            name="uq_billing_webhook_provider_event",
        ),
    )
    op.create_index(
        "ix_billing_webhook_events_organization_id",
        "billing_webhook_events",
        ["organization_id"],
    )
    op.create_index(
        "ix_billing_webhook_events_provider",
        "billing_webhook_events",
        ["provider"],
    )


def downgrade() -> None:
    op.drop_index("ix_billing_webhook_events_provider", table_name="billing_webhook_events")
    op.drop_index(
        "ix_billing_webhook_events_organization_id",
        table_name="billing_webhook_events",
    )
    op.drop_table("billing_webhook_events")
