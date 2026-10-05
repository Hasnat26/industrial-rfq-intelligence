"""add procurement workflow audit events

Revision ID: p2audit001
Revises: p2rev001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p2audit001"
down_revision: str | None = "p2rev001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "procurement_audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("from_status", sa.String(length=60), nullable=True),
        sa.Column("to_status", sa.String(length=60), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["package_id"], ["procurement_packages.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["vendor_offers.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_procurement_audit_events_package_id", "procurement_audit_events", ["package_id"])
    op.create_index("ix_procurement_audit_events_offer_id", "procurement_audit_events", ["offer_id"])
    op.create_index("ix_procurement_audit_events_actor_user_id", "procurement_audit_events", ["actor_user_id"])
    op.create_index("ix_procurement_audit_events_event_type", "procurement_audit_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_procurement_audit_events_event_type", table_name="procurement_audit_events")
    op.drop_index("ix_procurement_audit_events_actor_user_id", table_name="procurement_audit_events")
    op.drop_index("ix_procurement_audit_events_offer_id", table_name="procurement_audit_events")
    op.drop_index("ix_procurement_audit_events_package_id", table_name="procurement_audit_events")
    op.drop_table("procurement_audit_events")
