"""P4 lifecycle event foundation."""

import sqlalchemy as sa
from alembic import op

revision = "p4life001"
down_revision = "p3prod001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lifecycle_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "package_id",
            sa.Integer(),
            sa.ForeignKey("procurement_packages.id"),
            nullable=False,
        ),
        sa.Column(
            "offer_id",
            sa.Integer(),
            sa.ForeignKey("vendor_offers.id"),
            nullable=True,
        ),
        sa.Column("asset_id", sa.String(length=200), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lifecycle_events_package_id", "lifecycle_events", ["package_id"])
    op.create_index("ix_lifecycle_events_offer_id", "lifecycle_events", ["offer_id"])
    op.create_index("ix_lifecycle_events_asset_id", "lifecycle_events", ["asset_id"])
    op.create_index("ix_lifecycle_events_event_type", "lifecycle_events", ["event_type"])
    op.create_index("ix_lifecycle_events_event_date", "lifecycle_events", ["event_date"])
    op.create_index(
        "ix_lifecycle_events_created_by_user_id",
        "lifecycle_events",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_lifecycle_events_created_by_user_id", table_name="lifecycle_events")
    op.drop_index("ix_lifecycle_events_event_date", table_name="lifecycle_events")
    op.drop_index("ix_lifecycle_events_event_type", table_name="lifecycle_events")
    op.drop_index("ix_lifecycle_events_asset_id", table_name="lifecycle_events")
    op.drop_index("ix_lifecycle_events_offer_id", table_name="lifecycle_events")
    op.drop_index("ix_lifecycle_events_package_id", table_name="lifecycle_events")
    op.drop_table("lifecycle_events")
