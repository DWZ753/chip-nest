"""add layout_configs.zone_sizes

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-09

"""
import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "layout_configs",
        sa.Column("zone_sizes", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("layout_configs", "zone_sizes")
