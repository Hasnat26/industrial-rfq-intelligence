"""persist vendor offer revision lineage

Revision ID: p2rev001
Revises: b088bb588596
Create Date: 2026-10-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p2rev001"
down_revision: str | None = "b088bb588596"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("vendor_offers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("parent_offer_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_vendor_offers_parent_offer_id", ["parent_offer_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_vendor_offers_parent_offer_id",
            "vendor_offers",
            ["parent_offer_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("vendor_offers", schema=None) as batch_op:
        batch_op.drop_constraint("fk_vendor_offers_parent_offer_id", type_="foreignkey")
        batch_op.drop_index("ix_vendor_offers_parent_offer_id")
        batch_op.drop_column("parent_offer_id")
