"""add lookup_cache

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-14

"""
import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lookup_cache",
        sa.Column("key", sa.String(length=160), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("lookup_cache")
