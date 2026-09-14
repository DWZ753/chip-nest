"""add components.card_items

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-10

"""
import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "components",
        sa.Column("card_items", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("components", "card_items")
