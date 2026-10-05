"""Add explicit product identity fields to vendor offers.

Revision ID: p3prod001
Revises: p2decision001
"""

from alembic import op
import sqlalchemy as sa

revision = "p3prod001"
down_revision = "p2decision001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vendor_offers", sa.Column("manufacturer", sa.String(length=200), nullable=True))
    op.add_column("vendor_offers", sa.Column("model", sa.String(length=200), nullable=True))
    op.add_column("vendor_offers", sa.Column("part_number", sa.String(length=200), nullable=True))
    op.create_index("ix_vendor_offers_manufacturer", "vendor_offers", ["manufacturer"], unique=False)
    op.create_index("ix_vendor_offers_model", "vendor_offers", ["model"], unique=False)
    op.create_index("ix_vendor_offers_part_number", "vendor_offers", ["part_number"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_vendor_offers_part_number", table_name="vendor_offers")
    op.drop_index("ix_vendor_offers_model", table_name="vendor_offers")
    op.drop_index("ix_vendor_offers_manufacturer", table_name="vendor_offers")
    op.drop_column("vendor_offers", "part_number")
    op.drop_column("vendor_offers", "model")
    op.drop_column("vendor_offers", "manufacturer")
