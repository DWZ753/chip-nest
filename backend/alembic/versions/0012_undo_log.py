"""add undo_log

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-16

"""
import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "undo_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("done", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_undo_log_ts", "undo_log", ["ts"])


def downgrade() -> None:
    op.drop_index("ix_undo_log_ts", table_name="undo_log")
    op.drop_table("undo_log")
