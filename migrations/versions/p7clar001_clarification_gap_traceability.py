"""Add RFQ and evaluation traceability to technical clarifications."""

import sqlalchemy as sa
from alembic import op

revision = "p7clar001"
down_revision = "p6rfq001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("technical_clarifications") as batch:
        batch.add_column(sa.Column("rfq_revision_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("requirement_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("gap_type", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("evaluated_offered", sa.String(length=250), nullable=True))
        batch.add_column(sa.Column("evaluation_status", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("evaluation_evidence", sa.Text(), nullable=True))
        batch.create_index(
            "ix_technical_clarifications_rfq_revision_id",
            ["rfq_revision_id"],
        )
        batch.create_index(
            "ix_technical_clarifications_requirement_id",
            ["requirement_id"],
        )
        batch.create_foreign_key(
            "fk_technical_clarifications_rfq_revision_id",
            "rfq_revisions",
            ["rfq_revision_id"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_technical_clarifications_requirement_id",
            "requirements",
            ["requirement_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("technical_clarifications") as batch:
        batch.drop_constraint(
            "fk_technical_clarifications_requirement_id",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_technical_clarifications_rfq_revision_id",
            type_="foreignkey",
        )
        batch.drop_index("ix_technical_clarifications_requirement_id")
        batch.drop_index("ix_technical_clarifications_rfq_revision_id")
        batch.drop_column("evaluation_evidence")
        batch.drop_column("evaluation_status")
        batch.drop_column("evaluated_offered")
        batch.drop_column("gap_type")
        batch.drop_column("requirement_id")
        batch.drop_column("rfq_revision_id")
