"""Asset product lifecycle schema migration."""

import sqlalchemy as sa
from alembic import op

revision = "p4asset001"
down_revision = "p4life001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("package_id", sa.Integer(), sa.ForeignKey("procurement_packages.id"), nullable=False),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("vendor_offers.id"), nullable=True),
        sa.Column("asset_id", sa.String(length=200), nullable=False),
        sa.Column("manufacturer", sa.String(length=200), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("part_number", sa.String(length=200), nullable=True),
        sa.Column("serial_number", sa.String(length=200), nullable=True),
        sa.Column("installation_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("commissioning_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("warranty_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("warranty_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.UniqueConstraint("package_id", "asset_id", name="uq_asset_products_package_asset"),
    )
    for name, column in [
        ("package_id", "package_id"),
        ("offer_id", "offer_id"),
        ("asset_id", "asset_id"),
        ("manufacturer", "manufacturer"),
        ("model", "model"),
        ("part_number", "part_number"),
        ("serial_number", "serial_number"),
    ]:
        op.create_index(f"ix_asset_products_{name}", "asset_products", [column])


def downgrade() -> None:
    for name in ["serial_number", "part_number", "model", "manufacturer", "asset_id", "offer_id", "package_id"]:
        op.drop_index(f"ix_asset_products_{name}", table_name="asset_products")
    op.drop_table("asset_products")
