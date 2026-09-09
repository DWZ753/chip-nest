"""add components.display_tags

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-09

"""
import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "components",
        sa.Column("display_tags", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("components", "display_tags")
