"""Add package-level technical/commercial evaluation weights.

This converts the legacy standalone SQL migration into the Alembic chain so
clean installs and already-migrated deployments receive the same schema.
"""

import sqlalchemy as sa
from alembic import op

revision = "p8eval001"
down_revision = "p7clar001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "package_evaluation_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("package_id", sa.Integer(), sa.ForeignKey("procurement_packages.id"), nullable=False),
        sa.Column("technical_weight", sa.Float(), nullable=False, server_default="70.0"),
        sa.Column("commercial_weight", sa.Float(), nullable=False, server_default="30.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("package_id", name="uq_package_evaluation_settings_package"),
    )


def downgrade() -> None:
    op.drop_table("package_evaluation_settings")
