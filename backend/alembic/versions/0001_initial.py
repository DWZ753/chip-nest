"""initial tables + default layout seed

Revision ID: 0001
Revises:
Create Date: 2026-09-08

"""
import datetime as dt

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def upgrade() -> None:
    # 货架布局（单例 id=1）
    op.create_table(
        "layout_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("zone_count", sa.Integer(), nullable=False),
        sa.Column("layer_count", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("col_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    layout = sa.table(
        "layout_configs",
        sa.column("id", sa.Integer),
        sa.column("zone_count", sa.Integer),
        sa.column("layer_count", sa.Integer),
        sa.column("row_count", sa.Integer),
        sa.column("col_count", sa.Integer),
        sa.column("updated_at", sa.DateTime),
    )
    # 默认布局：1 区 x 3 层 x 1 行 4 列
    op.bulk_insert(layout, [
        {"id": 1, "zone_count": 1, "layer_count": 3,
         "row_count": 1, "col_count": 4, "updated_at": _now()},
    ])

    # 元件槽位
    op.create_table(
        "components",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("value", sa.String(32)),
        sa.Column("package", sa.String(32)),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("threshold", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("zone", sa.Integer(), nullable=False),
        sa.Column("layer", sa.Integer(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("led_index", sa.Integer()),
        sa.Column("search_text", sa.String(256), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("zone", "layer", "slot", name="uq_component_position"),
    )
    op.create_index("ix_component_led", "components", ["led_index"])

    # 库存审计流水
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("component_id", sa.Integer(),
                  sa.ForeignKey("components.id", ondelete="SET NULL")),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("source", sa.String(16)),
    )
    op.create_index("ix_transactions_ts", "transactions", ["ts"])
    op.create_index("ix_transactions_component_id", "transactions", ["component_id"])


def downgrade() -> None:
    op.drop_table("transactions")
    op.drop_table("components")
    op.drop_table("layout_configs")
