"""add procurement final decision

Revision ID: p2decision001
Revises: p2audit001
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
revision: str = "p2decision001"
down_revision: str | None = "p2audit001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.create_table(
        "procurement_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("selected_offer_id", sa.Integer(), nullable=False),
        sa.Column("decision_status", sa.String(length=30), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("decided_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["package_id"], ["procurement_packages.id"]),
        sa.ForeignKeyConstraint(["selected_offer_id"], ["vendor_offers.id"]),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_id"),
    )
    op.create_index("ix_procurement_decisions_package_id", "procurement_decisions", ["package_id"], unique=True)
    op.create_index("ix_procurement_decisions_selected_offer_id", "procurement_decisions", ["selected_offer_id"])
    op.create_index("ix_procurement_decisions_decided_by_user_id", "procurement_decisions", ["decided_by_user_id"])

def downgrade() -> None:
    op.drop_index("ix_procurement_decisions_decided_by_user_id", table_name="procurement_decisions")
    op.drop_index("ix_procurement_decisions_selected_offer_id", table_name="procurement_decisions")
    op.drop_index("ix_procurement_decisions_package_id", table_name="procurement_decisions")
    op.drop_table("procurement_decisions")
