"""Add immutable RFQ revisions and baseline links.

The migration keeps the existing package/requirement/offer rows intact while
introducing the revision boundary needed for auditable RFQ refinement.
"""

import sqlalchemy as sa
from alembic import op

revision = "p6rfq001"
down_revision = "p5commercial004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rfq_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="CURRENT"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes_revision_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["package_id"], ["procurement_packages.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["supersedes_revision_id"], ["rfq_revisions.id"]),
        sa.UniqueConstraint(
            "package_id",
            "revision",
            name="uq_rfq_revisions_package_revision",
        ),
    )

    with op.batch_alter_table("procurement_packages") as batch:
        batch.add_column(sa.Column("current_rfq_revision_id", sa.Integer(), nullable=True))
        batch.create_index(
            "ix_procurement_packages_current_rfq_revision_id",
            ["current_rfq_revision_id"],
        )
        batch.create_foreign_key(
            "fk_procurement_packages_current_rfq_revision_id",
            "rfq_revisions",
            ["current_rfq_revision_id"],
            ["id"],
        )

    with op.batch_alter_table("requirements") as batch:
        batch.add_column(sa.Column("rfq_revision_id", sa.Integer(), nullable=True))
        batch.create_index("ix_requirements_rfq_revision_id", ["rfq_revision_id"])
        batch.create_foreign_key(
            "fk_requirements_rfq_revision_id",
            "rfq_revisions",
            ["rfq_revision_id"],
            ["id"],
        )

    with op.batch_alter_table("vendor_offers") as batch:
        batch.add_column(sa.Column("rfq_revision_id", sa.Integer(), nullable=True))
        batch.create_index("ix_vendor_offers_rfq_revision_id", ["rfq_revision_id"])
        batch.create_foreign_key(
            "fk_vendor_offers_rfq_revision_id",
            "rfq_revisions",
            ["rfq_revision_id"],
            ["id"],
        )

    op.execute(
        """
        INSERT INTO rfq_revisions (
            package_id, revision, status, reason, created_at
        )
        SELECT
            p.id, 'R1', 'CURRENT', 'Initial RFQ baseline', CURRENT_TIMESTAMP
        FROM procurement_packages AS p
        WHERE NOT EXISTS (
            SELECT 1
            FROM rfq_revisions AS r
            WHERE r.package_id = p.id
              AND r.revision = 'R1'
        )
        """
    )
    op.execute(
        """
        UPDATE procurement_packages
        SET current_rfq_revision_id = (
            SELECT r.id
            FROM rfq_revisions AS r
            WHERE r.package_id = procurement_packages.id
              AND r.revision = 'R1'
        )
        WHERE current_rfq_revision_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE requirements
        SET rfq_revision_id = (
            SELECT r.id
            FROM rfq_revisions AS r
            WHERE r.package_id = requirements.package_id
              AND r.revision = 'R1'
        )
        WHERE rfq_revision_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE vendor_offers
        SET rfq_revision_id = (
            SELECT r.id
            FROM rfq_revisions AS r
            WHERE r.package_id = vendor_offers.package_id
              AND r.revision = 'R1'
        )
        WHERE rfq_revision_id IS NULL
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("vendor_offers") as batch:
        batch.drop_constraint("fk_vendor_offers_rfq_revision_id", type_="foreignkey")
        batch.drop_index("ix_vendor_offers_rfq_revision_id")
        batch.drop_column("rfq_revision_id")

    with op.batch_alter_table("requirements") as batch:
        batch.drop_constraint("fk_requirements_rfq_revision_id", type_="foreignkey")
        batch.drop_index("ix_requirements_rfq_revision_id")
        batch.drop_column("rfq_revision_id")

    with op.batch_alter_table("procurement_packages") as batch:
        batch.drop_constraint("fk_procurement_packages_current_rfq_revision_id", type_="foreignkey")
        batch.drop_index("ix_procurement_packages_current_rfq_revision_id")
        batch.drop_column("current_rfq_revision_id")

    op.drop_table("rfq_revisions")
