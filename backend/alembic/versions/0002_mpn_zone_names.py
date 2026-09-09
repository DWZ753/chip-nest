"""add mpn/supplier_part columns and zone_names

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-08

"""
import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("components", sa.Column("manufacturer_part", sa.String(64)))
    op.add_column("components", sa.Column("supplier_part", sa.String(40)))
    op.add_column(
        "layout_configs",
        sa.Column("zone_names", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("layout_configs", "zone_names")
    op.drop_column("components", "supplier_part")
    op.drop_column("components", "manufacturer_part")
