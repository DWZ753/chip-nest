"""add components.display_fields

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-10

"""
import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "components",
        sa.Column("display_fields", sa.Text(), nullable=False,
                  server_default='["value", "package"]'),
    )


def downgrade() -> None:
    op.drop_column("components", "display_fields")
