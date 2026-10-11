"""新增备份策略和 BOM 项目表，保留现有库存结构。"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """@brief 创建本地策略与项目表。"""
    op.create_table(
        "backup_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("interval_hours", sa.Integer(), nullable=False),
        sa.Column("keep_count", sa.Integer(), nullable=False),
        sa.Column("directory", sa.Text(), nullable=False),
        sa.Column("last_backup_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False),
    )
    op.create_table(
        "bom_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("lines", sa.Text(), nullable=False),
        sa.Column("selections", sa.Text(), nullable=False),
        sa.Column("copies", sa.Integer(), nullable=False),
        sa.Column("plan", sa.Text(), nullable=False),
        sa.Column("cursor", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    """@brief 撤销本次新增的表。"""
    op.drop_table("bom_projects")
    op.drop_table("backup_preferences")
