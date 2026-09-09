"""add components.tags

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-08

"""
import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "components",
        sa.Column("tags", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("components", "tags")
