"""Align PostgreSQL indexes with ORM metadata.

Revision ID: p9meta001
Revises: p8eval001
"""

from __future__ import annotations

from collections.abc import Sequence

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



def downgrade() -> None:
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
