"""add layout_configs.zone_layers

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-14

"""
import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "layout_configs",
        sa.Column("zone_layers", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("layout_configs", "zone_layers")
