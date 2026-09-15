"""add component_slots

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-15

"""
import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "component_slots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=False),
        sa.Column("zone", sa.Integer(), nullable=False),
        sa.Column("layer", sa.Integer(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("zone", "layer", "slot", name="uq_slot_position"),
    )
    op.create_index("ix_component_slots_component_id", "component_slots", ["component_id"])


def downgrade() -> None:
    op.drop_index("ix_component_slots_component_id", table_name="component_slots")
    op.drop_table("component_slots")
