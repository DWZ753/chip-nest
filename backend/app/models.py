"""ORM 模型：元件、布局配置、库存审计流水。"""

import datetime as dt
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> dt.datetime:
    """无时区 UTC 时间，统一入库格式。"""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """全部 ORM 模型的基类（供 alembic 收集元数据）。"""


class Component(Base):
    """货架上的一个元件槽位。

    zone/layer/slot 共同定位抽屉格（联合唯一），
    led_index 对应灯带上的序号，grid 缩容后可能无灯。
    """

    __tablename__ = "components"
    __table_args__ = (
        UniqueConstraint("zone", "layer", "slot", name="uq_component_position"),
        Index("ix_component_led", "led_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    value: Mapped[Optional[str]] = mapped_column(String(32))
    package: Mapped[Optional[str]] = mapped_column(String(32))
    # 厂商料号（MPN）与供应商编号（Supplier Part）：BOM 采购/识别依据
    manufacturer_part: Mapped[Optional[str]] = mapped_column(String(64))
    supplier_part: Mapped[Optional[str]] = mapped_column(String(40))
    # 用户自定义标签（JSON 数组，如 ["主控","stm32"]）；用于检索/筛选
    tags: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    # 外部可见标签：从 tags 中挑选 1~3 个，显示在格子上（与元件名一起）
    display_tags: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    threshold: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    zone: Mapped[int] = mapped_column(Integer)
    layer: Mapped[int] = mapped_column(Integer)
    slot: Mapped[int] = mapped_column(Integer)
    led_index: Mapped[Optional[int]] = mapped_column(Integer)
    search_text: Mapped[str] = mapped_column(String(256), default="", server_default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Transaction(Base):
    """库存审计流水：入库/出库/引导取料/建档/删除各落一条，与库存同事务提交。"""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(16))  # create/delete/in/out/bom_pick/adjust
    component_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("components.id", ondelete="SET NULL"), index=True
    )
    delta: Mapped[int] = mapped_column(Integer)
    detail: Mapped[Optional[str]] = mapped_column(Text)  # JSON 快照或说明
    source: Mapped[Optional[str]] = mapped_column(String(16))  # ui / guide / system


class LayoutConfig(Base):
    """货架布局（单例行 id=1）：几个区，每区几层，每层 行x列 个格子。"""

    __tablename__ = "layout_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zone_count: Mapped[int] = mapped_column(Integer, default=1)
    layer_count: Mapped[int] = mapped_column(Integer, default=3)
    row_count: Mapped[int] = mapped_column(Integer, default=1)
    col_count: Mapped[int] = mapped_column(Integer, default=4)
    # 每区可自定义名称（JSON 数组，如 ["LimeRC遥控器","通用料"]）；空数组=用「第N区」
    zone_names: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    # 每区独立网格尺寸（JSON 数组，每项 [行, 列]，如 [[1,4],[2,3]]）；缺项用 row/col 默认值
    zone_sizes: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)