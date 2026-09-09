"""库存域逻辑：槽位校验、条件原子扣减、审计流水（与库存同事务）。

防超卖硬保证 = 带 WHERE quantity>=need 的单条 UPDATE（行级原子，
SQLite/PostgreSQL 语义一致）；select_for_update 仅用于产出准确的报错信息，
在 PostgreSQL 下会自动升级为真正的行锁。
"""

import json

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import events
from app.models import Component, LayoutConfig, Transaction
from app.services.search import build_search_text


def _load_tags(raw: str) -> list[str]:
    """存储 JSON → 列表（脏数据容错）。"""
    try:
        parsed = json.loads(raw or "[]")
    except ValueError:
        return []
    return [str(x) for x in parsed] if isinstance(parsed, list) else []


def _dump_tags(tags, cap: int = 8) -> str:
    """标签列表 → 存储 JSON（容错任意输入；cap 限制条数）。"""
    if not tags:
        return "[]"
    cleaned = []
    for raw in tags:
        item = str(raw).strip()[:20]
        if item and item not in cleaned and len(cleaned) < cap:
            cleaned.append(item)
    return json.dumps(cleaned, ensure_ascii=False)


class StockShortage(Exception):
    """出库量超出当前库存（available 为发起请求时读到的最新值）。"""

    def __init__(self, available: int):
        self.available = available
        super().__init__(f"库存不足，当前剩余 {available}")


class PositionBusy(Exception):
    """zone/layer/slot 已被其他元件占用。"""

    def __init__(self, occupant: str):
        self.occupant = occupant
        super().__init__(f"槽位已被占用：{occupant}")


class OutOfLayout(Exception):
    """目标位置超出了当前 LayoutConfig 的网格范围。"""


async def load_layout(session: AsyncSession) -> LayoutConfig:
    row = await session.scalar(select(LayoutConfig).where(LayoutConfig.id == 1))
    if row is None:
        raise OutOfLayout("布局配置缺失，请先重启服务完成初始化")
    return row


async def validate_position(session: AsyncSession, zone: int, layer: int, slot: int) -> None:
    """校验位置在布局范围内（slot 为层内行主序编号 0..rows*cols-1）。"""
    layout = await load_layout(session)
    cells = layout.row_count * layout.col_count
    if not (1 <= zone <= layout.zone_count and 1 <= layer <= layout.layer_count):
        raise OutOfLayout(
            f"超出布局范围：当前 {layout.zone_count} 区 x {layout.layer_count} 层"
        )
    if not 0 <= slot < cells:
        raise OutOfLayout(
            f"该层只有 {layout.row_count}x{layout.col_count} 个格子（slot 0..{cells - 1}）"
        )


async def ensure_position_free(
    session: AsyncSession, zone: int, layer: int, slot: int, exclude_id: int | None = None
) -> None:
    """同区同层同格联合唯一检查。"""
    stmt = select(Component).where(
        Component.zone == zone, Component.layer == layer, Component.slot == slot
    )
    if exclude_id is not None:
        stmt = stmt.where(Component.id != exclude_id)
    occupant = await session.scalar(stmt)
    if occupant is not None:
        raise PositionBusy(f"{occupant.name}")


async def next_led_index(session: AsyncSession) -> int:
    """自动分配灯带序号：现有最大 + 1（0 起）。"""
    max_led = await session.scalar(select(Component.led_index))
    return (max_led + 1) if max_led is not None else 0


def _position(zone: int, layer: int, slot: int) -> str:
    return f"{zone}区/{layer}层/{slot}格"


async def create_component(
    session: AsyncSession,
    *,
    name: str,
    zone: int,
    layer: int,
    slot: int,
    value: str | None = None,
    package: str | None = None,
    quantity: int = 0,
    threshold: int = 5,
    led_index: int | None = None,
    manufacturer_part: str | None = None,
    supplier_part: str | None = None,
    tags: list[str] | None = None,
    display_tags: list[str] | None = None,
    source: str = "ui",
) -> Component:
    """建档（含检索文本与审计流水），同一事务提交。"""
    await validate_position(session, zone, layer, slot)
    await ensure_position_free(session, zone, layer, slot)
    if led_index is None:
        led_index = await next_led_index(session)

    component = Component(
        name=name, value=value, package=package,
        quantity=quantity, threshold=threshold,
        zone=zone, layer=layer, slot=slot, led_index=led_index,
        manufacturer_part=manufacturer_part,
        supplier_part=supplier_part,
        tags=_dump_tags(tags),
        display_tags=_dump_tags(display_tags, cap=3),
        search_text=build_search_text(name, value or "", package or "",
                                      manufacturer_part or "", " ".join(tags or [])),
    )
    session.add(component)
    session.add(Transaction(
        kind="create", delta=quantity, source=source,
        detail=f"建档 {name}（{_position(zone, layer, slot)}），初始库存 {quantity}",
    ))
    await session.commit()
    events.emit("stock.changed", component)
    return component


async def update_component(
    session: AsyncSession, component: Component, patch: dict, source: str = "ui"
) -> Component:
    """属性/搬家修改（不允许直接改库存），同事务提交。"""
    changed = []

    if "zone" in patch:  # 搬家：三字段必成组（路由已校验）
        zone, layer, slot = patch["zone"], patch["layer"], patch["slot"]
        await validate_position(session, zone, layer, slot)
        await ensure_position_free(session, zone, layer, slot, exclude_id=component.id)
        component.zone, component.layer, component.slot = zone, layer, slot
        changed.append(f"搬到 {_position(zone, layer, slot)}")

    for key in ("name", "value", "package", "threshold", "led_index",
                 "manufacturer_part", "supplier_part"):
        if key in patch:
            setattr(component, key, patch[key])
            changed.append(key)
    if "tags" in patch:
        component.tags = _dump_tags(patch["tags"] or [])
        changed.append("tags")
    if "display_tags" in patch:
        component.display_tags = _dump_tags(patch["display_tags"] or [], cap=3)
        changed.append("display_tags")

    if changed:  # 名称/值/封装变动时重建检索文本
        component.search_text = build_search_text(
            component.name, component.value or "", component.package or "",
            component.manufacturer_part or "",
            " ".join(_load_tags(component.tags)),
        )
        session.add(Transaction(
            kind="adjust", component_id=component.id, delta=0, source=source,
            detail=f"修改 {component.name}：{', '.join(changed)}",
        ))
    await session.commit()
    return component


async def delete_component(
    session: AsyncSession, component: Component, source: str = "ui"
) -> None:
    """删除元件并留审计快照，同事务提交。"""
    snapshot = (f"删除元件 {component.name}（{_position(component.zone, component.layer, component.slot)}，"
                f"库存 {component.quantity}，灯 {component.led_index}）")
    session.add(Transaction(
        kind="delete", delta=0, source=source, detail=snapshot,
    ))
    await session.delete(component)
    await session.commit()
    events.emit("component.removed", component)


async def change_stock(
    session: AsyncSession,
    component: Component,
    delta: int,
    note: str | None = None,
    source: str = "ui",
) -> Component:
    """入/出库：负数为出库，出库带行级原子保护，防并发扣成负数。"""
    if delta == 0:
        raise ValueError("delta 不能为 0")

    if delta > 0:
        component.quantity += delta
        kind, verb = "in", "入库"
    else:
        need = -delta
        cur = await session.scalar(
            select(Component.quantity).where(Component.id == component.id).with_for_update()
        )
        if cur is None:
            raise StockShortage(0)
        if cur < need:
            raise StockShortage(cur)
        result = await session.execute(
            update(Component)
            .where(Component.id == component.id, Component.quantity >= need)
            .values(quantity=Component.quantity - need),
            execution_options={"synchronize_session": "fetch"},  # 回读对象，勿再手动减
        )
        if result.rowcount == 0:  # 并发竞争者先扣走：以真实值报错
            fresh = await session.scalar(
                select(Component.quantity).where(Component.id == component.id)
            )
            raise StockShortage(fresh or 0)
        kind = "bom_pick" if source == "guide" else "out"
        verb = "出库"

    session.add(Transaction(
        kind=kind, component_id=component.id, delta=delta, source=source,
        detail=f"{verb} {abs(delta)} 个（{note or '无备注'}）",
    ))
    await session.commit()
    events.emit("stock.changed", component)
    return component