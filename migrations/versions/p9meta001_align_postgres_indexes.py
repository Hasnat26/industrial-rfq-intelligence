"""Align PostgreSQL indexes with ORM metadata.

Revision ID: p9meta001
Revises: p8eval001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p9meta001"
down_revision: str | None = "p8eval001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # These indexes are declared by the ORM but were missing from the
    # historical migration chain.
    op.create_index(
        "ix_package_evaluation_settings_package_id",
        "package_evaluation_settings",
        ["package_id"],
        unique=False,
    )
    op.create_index(
        "ix_rfq_revisions_created_by_user_id",
        "rfq_revisions",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_rfq_revisions_package_id",
        "rfq_revisions",
        ["package_id"],
        unique=False,
    )
    op.create_index(
        "ix_rfq_revisions_supersedes_revision_id",
        "rfq_revisions",
        ["supersedes_revision_id"],
        unique=False,
    )

    # The ORM expresses package_id uniqueness as a unique index. The older
    # migration also created a redundant UNIQUE constraint for the same key.
    # Keep ix_procurement_decisions_package_id (the unique index) and remove
    # only the redundant constraint so schema and metadata converge.
    op.drop_constraint(
        "procurement_decisions_package_id_key",
        "procurement_decisions",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "procurement_decisions_package_id_key",
        "procurement_decisions",
        ["package_id"],
    )
    op.drop_index(
        "ix_rfq_revisions_supersedes_revision_id",
        table_name="rfq_revisions",
    )
    op.drop_index("ix_rfq_revisions_package_id", table_name="rfq_revisions")
    op.drop_index(
        "ix_rfq_revisions_created_by_user_id",
        table_name="rfq_revisions",
    )
    op.drop_index(
        "ix_package_evaluation_settings_package_id",
        table_name="package_evaluation_settings",
    )
