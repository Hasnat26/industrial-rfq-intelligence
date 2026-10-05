"""Add provider and lifecycle fields to organization subscriptions."""

import sqlalchemy as sa
from alembic import op

revision = "p5commercial002"
down_revision = "p5commercial001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organization_subscriptions", sa.Column("billing_provider", sa.String(length=30), nullable=True))
    op.add_column("organization_subscriptions", sa.Column("external_customer_id", sa.String(length=200), nullable=True))
    op.add_column("organization_subscriptions", sa.Column("external_subscription_id", sa.String(length=200), nullable=True))
    op.create_index("ix_organization_subscriptions_external_customer_id", "organization_subscriptions", ["external_customer_id"])
    op.create_index("ix_organization_subscriptions_external_subscription_id", "organization_subscriptions", ["external_subscription_id"])


def downgrade() -> None:
    op.drop_index("ix_organization_subscriptions_external_subscription_id", table_name="organization_subscriptions")
    op.drop_index("ix_organization_subscriptions_external_customer_id", table_name="organization_subscriptions")
    op.drop_column("organization_subscriptions", "external_subscription_id")
    op.drop_column("organization_subscriptions", "external_customer_id")
    op.drop_column("organization_subscriptions", "billing_provider")
