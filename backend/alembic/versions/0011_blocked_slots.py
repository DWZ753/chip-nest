"""add blocked_slots

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-16

"""
import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blocked_slots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("zone", sa.Integer(), nullable=False),
        sa.Column("layer", sa.Integer(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("zone", "layer", "slot", name="uq_blocked_position"),
    )


def downgrade() -> None:
    op.drop_table("blocked_slots")
