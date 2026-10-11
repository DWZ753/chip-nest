"""库存域逻辑：槽位校验、条件原子扣减、审计流水（与库存同事务）。

防超卖硬保证 = 带 WHERE quantity>=need 的单条 UPDATE（行级原子，
SQLite/PostgreSQL 语义一致）；select_for_update 仅用于产出准确的报错信息，
在 PostgreSQL 下会自动升级为真正的行锁。
"""

import json

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import events
from app.models import (
    BlockedSlot, Component, ComponentSlot, LayoutConfig, Transaction,
)
from app.services import undo as undo_service
from app.services.search import build_search_text


def _load_tags(raw: str) -> list[str]:
    """存储 JSON → 列表（脏数据容错）。"""
    try:
        parsed = json.loads(raw or "[]")
    except ValueError:
        return []
    return [str(x) for x in parsed] if isinstance(parsed, list) else []


_CARD_FIELDS = ("value", "package", "mpn", "supplier")


def _dump_fields(fields) -> str:
    """卡片显示字段 → JSON（白名单，空则回默认 value+package）。"""
    chosen = {str(f).strip() for f in (fields or [])}
    kept = [f for f in _CARD_FIELDS if f in chosen]
    return json.dumps(kept or ["value", "package"])


def _dump_card_items(items, tags) -> str:
    """统一顺序保存；#标签 必须仍存在于 tags（删标签即出列）。"""
    tag_set = {str(t).strip()[:20] for t in (tags or [])}
    kept: list[str] = []
    for raw in items or []:
        token = str(raw).strip()
        if token in _CARD_FIELDS:
            pass
        elif token.startswith("#") and token[1:].strip()[:20] in tag_set:
            token = "#" + token[1:].strip()[:20]
        else:
            continue
        if token not in kept:
            kept.append(token)
    return json.dumps(kept[:24], ensure_ascii=False)


def _dump_display_tags(tags, display, cap: int = 6) -> str:
    """展示标签必须是标签的子集：标签被删掉后，展示位同步清理。"""
    tag_set = [str(t).strip()[:20] for t in (tags or [])]
    keep = [str(d).strip()[:20] for d in (display or []) if str(d).strip()[:20] in tag_set]
    return _dump_tags(keep, cap=cap)


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


class SlotBlocked(Exception):
    """目标格子被标记为不可用（物理容器坏了等）。"""

    def __init__(self, zone: int, layer: int, slot: int):
        self.position = (zone, layer, slot)
        super().__init__(f"该格已标记不可用：{zone}区/{layer}层/{slot}格")


class OutOfLayout(Exception):
    """目标位置超出了当前 LayoutConfig 的网格范围。"""


async def load_layout(session: AsyncSession) -> LayoutConfig:
    row = await session.scalar(select(LayoutConfig).where(LayoutConfig.id == 1))
    if row is None:
        raise OutOfLayout("布局配置缺失，请先重启服务完成初始化")
    return row


def zone_grid(layout: LayoutConfig, zone: int) -> tuple[int, int]:
    """取某区的 (行, 列)：优先 zone_sizes，缺项用全局默认。"""
    try:
        sizes = json.loads(layout.zone_sizes or "[]")
    except ValueError:
        sizes = []
    if isinstance(sizes, list) and 1 <= zone <= len(sizes):
        item = sizes[zone - 1]
        if isinstance(item, list) and len(item) == 2:
            return int(item[0]), int(item[1])
    return layout.row_count, layout.col_count


def zone_layers(layout: LayoutConfig, zone: int) -> int:
    """取某区的层数：优先 zone_layers，缺项用全局默认 layer_count。"""
    try:
        parsed = json.loads(layout.zone_layers or "[]")
    except ValueError:
        parsed = []
    if isinstance(parsed, list) and 1 <= zone <= len(parsed):
        try:
            return max(1, int(parsed[zone - 1]))
        except (TypeError, ValueError):
            pass
    return layout.layer_count


async def validate_position(session: AsyncSession, zone: int, layer: int, slot: int) -> None:
    """校验位置在布局范围内（slot 为层内行主序编号 0..rows*cols-1）。"""
    layout = await load_layout(session)
    if not 1 <= zone <= layout.zone_count:
        raise OutOfLayout(f"超出布局范围：当前共 {layout.zone_count} 个区")
    layers = zone_layers(layout, zone)
    if not 1 <= layer <= layers:
        raise OutOfLayout(f"超出布局范围：第 {zone} 区只有 {layers} 层")
    rows, cols = zone_grid(layout, zone)
    rows, cols = zone_grid(layout, zone)
    cells = rows * cols
    if not 0 <= slot < cells:
        raise OutOfLayout(
            f"第 {zone} 区该层只有 {rows}x{cols} 个格子（slot 0..{cells - 1}）"
        )


async def ensure_position_free(
    session: AsyncSession, zone: int, layer: int, slot: int, exclude_id: int | None = None
) -> None:
    """同区同层同格联合唯一检查：主格与附加格都算占用。"""
    stmt = select(Component).where(
        Component.zone == zone, Component.layer == layer, Component.slot == slot
    )
    if exclude_id is not None:
        stmt = stmt.where(Component.id != exclude_id)
    occupant = await session.scalar(stmt)
    if occupant is not None:
        raise PositionBusy(f"{occupant.name}")

    slot_stmt = select(ComponentSlot).where(
        ComponentSlot.zone == zone, ComponentSlot.layer == layer,
        ComponentSlot.slot == slot,
    )
    if exclude_id is not None:
        slot_stmt = slot_stmt.where(ComponentSlot.component_id != exclude_id)
    borrowed = await session.scalar(slot_stmt)
    if borrowed is not None:
        owner = await session.get(Component, borrowed.component_id)
        raise PositionBusy(f"{owner.name if owner else '别的元件'}（占用格）")

    blocked = await session.scalar(select(BlockedSlot).where(
        BlockedSlot.zone == zone, BlockedSlot.layer == layer, BlockedSlot.slot == slot
    ))
    if blocked is not None:
        raise SlotBlocked(zone, layer, slot)


async def blocked_positions(session: AsyncSession) -> set[tuple[int, int, int]]:
    """当前被标记为不可用的格子。"""
    rows = (await session.scalars(select(BlockedSlot))).all()
    return {(r.zone, r.layer, r.slot) for r in rows}


async def first_free_position(session: AsyncSession) -> tuple[int, int, int] | None:
    """按 区→层→格 顺序找第一个能放东西的格子。"""
    layout = await load_layout(session)
    occupied = {
        (c.zone, c.layer, c.slot)
        for c in (await session.scalars(select(Component))).all()
    }
    occupied |= {
        (s.zone, s.layer, s.slot)
        for s in (await session.scalars(select(ComponentSlot))).all()
    }
    blocked = await blocked_positions(session)
    for zone in range(1, layout.zone_count + 1):
        rows, cols = zone_grid(layout, zone)
        for layer in range(1, zone_layers(layout, zone) + 1):
            for slot in range(rows * cols):
                pos = (zone, layer, slot)
                if pos not in occupied and pos not in blocked:
                    return pos
    return None


async def block_slot(
    session: AsyncSession, zone: int, layer: int, slot: int, source: str = "ui"
) -> None:
    """把某个格子标记为不可用（不能放元件、也不算空位）。"""
    await validate_position(session, zone, layer, slot)
    await ensure_position_free(session, zone, layer, slot)
    session.add(BlockedSlot(zone=zone, layer=layer, slot=slot))
    session.add(Transaction(
        kind="adjust", delta=0, source=source,
        detail=f"标记 {_position(zone, layer, slot)} 不可用",
    ))
    await session.commit()


async def unblock_slot(
    session: AsyncSession, zone: int, layer: int, slot: int, source: str = "ui"
) -> None:
    """恢复某个格子可用。"""
    row = await session.scalar(select(BlockedSlot).where(
        BlockedSlot.zone == zone, BlockedSlot.layer == layer, BlockedSlot.slot == slot
    ))
    if row is None:
        raise PositionBusy("这个格子没有被标记不可用")
    await session.delete(row)
    session.add(Transaction(
        kind="adjust", delta=0, source=source,
        detail=f"恢复 {_position(zone, layer, slot)} 可用",
    ))
    await session.commit()


async def next_led_index(session: AsyncSession) -> int:
    """自动分配灯带序号：现有最大 + 1（0 起）。

    必须取 max：早先写成 select(led_index) 只拿到第一行的值，
    第三个元件起就会和现有序号撞车（多个格子共用一颗灯）。
    """
    max_led = await session.scalar(select(func.max(Component.led_index)))
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
    display_fields: list[str] | None = None,
    card_items: list[str] | None = None,
    source: str = "ui",
) -> Component:
    """建档（含检索文本与审计流水），同一事务提交。"""
    await validate_position(session, zone, layer, slot)
    await ensure_position_free(session, zone, layer, slot)
    if led_index is None:
        led_index = await next_led_index(session)

    component = Component(
        slots=[],  # 显式给空集合：异步会话下不要触发懒加载
        name=name, value=value, package=package,
        quantity=quantity, threshold=threshold,
        zone=zone, layer=layer, slot=slot, led_index=led_index,
        manufacturer_part=manufacturer_part,
        supplier_part=supplier_part,
        tags=_dump_tags(tags),
        display_tags=_dump_display_tags(tags, display_tags),
        display_fields=_dump_fields(display_fields),
        card_items=_dump_card_items(card_items, tags),
        search_text=build_search_text(name, value or "", package or "",
                                      manufacturer_part or "", " ".join(tags or [])),
    )
    session.add(component)
    session.add(Transaction(
        kind="create", delta=quantity, source=source,
        detail=f"建档 {name}（{_position(zone, layer, slot)}），初始库存 {quantity}",
    ))
    await session.flush()
    await undo_service.record(session, f"建档 {name}", {"op": "create", "id": component.id})
    await session.commit()
    events.emit("stock.changed", component)
    return component


async def merge_components(
    session: AsyncSession, keep: Component, other: Component,
) -> Component:
    """合并相同元件的库存和位置；保留主格设置，记录审计与撤销快照。"""
    identity_fields = (
        ("name", "名称"), ("value", "标称值"), ("package", "封装"),
        ("manufacturer_part", "厂商料号"), ("supplier_part", "供应商料号"),
    )
    for field, label in identity_fields:
        if ((getattr(keep, field) or "").strip().casefold() !=
                (getattr(other, field) or "").strip().casefold()):
            raise ValueError(f"元件属性不一致：{label}")
    tags = list(dict.fromkeys(_load_tags(keep.tags) + _load_tags(other.tags)))
    if len(tags) > 8:
        raise ValueError("合并后标签超过 8 个")
    await undo_service.record(
        session, f"合并格 {other.name} → {keep.name}",
        {"op": "snapshot_many", "items": [
            {"id": keep.id, "before": undo_service.snapshot(keep)},
            {"id": other.id, "before": undo_service.snapshot(other)},
        ]},
    )
    keep.quantity += other.quantity
    for extra in list(other.slots):
        keep.slots.append(extra)
    keep.slots.append(ComponentSlot(
        component_id=keep.id, zone=other.zone, layer=other.layer,
        slot=other.slot,
    ))
    keep.tags = _dump_tags(tags)
    keep.search_text = build_search_text(
        keep.name, keep.value or "", keep.package or "",
        keep.manufacturer_part or "", " ".join(tags),
    )
    session.add(Transaction(
        kind="adjust", component_id=keep.id, delta=0, source="ui",
        detail=(f"合并格：{_position(other.zone, other.layer, other.slot)}"
                f" → {_position(keep.zone, keep.layer, keep.slot)}，"
                f"{keep.name} 数量合计 {keep.quantity}"),
    ))
    await session.delete(other)
    await session.commit()
    events.emit("component.removed", other)
    events.emit("stock.changed", keep)
    return keep


async def add_slot(
    session: AsyncSession, component: Component, zone: int, layer: int, slot: int,
    source: str = "ui",
) -> Component:
    """给元件追加一个附加格（不改变库存，只表示"这个物料的另一处存放位置"）。"""
    await validate_position(session, zone, layer, slot)
    if (component.zone, component.layer, component.slot) == (zone, layer, slot):
        raise PositionBusy("就是它自己的主格")
    if any((s.zone, s.layer, s.slot) == (zone, layer, slot) for s in component.slots):
        return component  # 已有：幂等返回
    await ensure_position_free(session, zone, layer, slot, exclude_id=component.id)
    before = undo_service.snapshot(component)

    component.slots.append(ComponentSlot(
        component_id=component.id, zone=zone, layer=layer, slot=slot,
    ))
    session.add(Transaction(
        kind="adjust", delta=0, source=source,
        detail=f"{component.name} 增加占用格 {_position(zone, layer, slot)}",
    ))
    await session.flush()
    await undo_service.record(
        session, f"合并格 {_position(zone, layer, slot)} → {component.name}",
        {"op": "snapshot", "id": component.id, "before": before},
    )
    await session.commit()
    return component


async def remove_slot(
    session: AsyncSession, component: Component, zone: int, layer: int, slot: int,
    source: str = "ui",
) -> Component:
    """解除一个附加格（主格不能这样删）。"""
    target = next((s for s in component.slots
                   if (s.zone, s.layer, s.slot) == (zone, layer, slot)), None)
    if target is None:
        raise PositionBusy("这个格子不是它的占用格")
    before = undo_service.snapshot(component)
    component.slots.remove(target)
    session.add(Transaction(
        kind="adjust", delta=0, source=source,
        detail=f"{component.name} 解除占用格 {_position(zone, layer, slot)}",
    ))
    await session.flush()
    await undo_service.record(
        session, f"解除共用格 {_position(zone, layer, slot)}",
        {"op": "snapshot", "id": component.id, "before": before},
    )
    await session.commit()
    return component


async def delete_position(
    session: AsyncSession, component: Component, zone: int, layer: int, slot: int,
) -> Component | None:
    """只释放指定格子；主格由剩余格接替，最后一格才删除元件。"""
    if (component.zone, component.layer, component.slot) != (zone, layer, slot):
        return await remove_slot(session, component, zone, layer, slot)
    if not component.slots:
        await delete_component(session, component)
        return None
    before = undo_service.snapshot(component)
    successor = min(component.slots, key=lambda s: (s.zone, s.layer, s.slot))
    new_position = (successor.zone, successor.layer, successor.slot)
    component.slots.remove(successor)
    await session.flush()
    component.zone, component.layer, component.slot = new_position
    session.add(Transaction(
        kind="adjust", component_id=component.id, delta=0, source="ui",
        detail=(f"删除格子 {_position(zone, layer, slot)}，"
                f"{component.name} 主格改为 {_position(*new_position)}"),
    ))
    await undo_service.record(
        session, f"删除格子 {_position(zone, layer, slot)}",
        {"op": "snapshot", "id": component.id, "before": before},
    )
    await session.commit()
    return component


# 互换时临时停放用的非法槽位（DB 允许负数，validate_position 不会放行它）
TEMP_SLOT = -1


async def swap_positions(
    session: AsyncSession, a: Component, b: Component, source: str = "ui"
) -> tuple[Component, Component]:
    """两个元件的槽位互换，灯号一起对调（灯带始终对应槽位）。

    联合唯一约束是即时生效的，所以三步走：A 先停到临时槽位 → B 落到 A 的原位
    → A 落到 B 的原位，全程同一事务，中途失败整体回滚，不会出现两格空着或撞车。
    """
    a_pos = (a.zone, a.layer, a.slot)
    b_pos = (b.zone, b.layer, b.slot)
    a_led, b_led = a.led_index, b.led_index
    before = [
        {"id": a.id, "before": undo_service.snapshot(a)},
        {"id": b.id, "before": undo_service.snapshot(b)},
    ]

    await validate_position(session, *a_pos)
    await validate_position(session, *b_pos)

    a.zone, a.layer, a.slot = a_pos[0], a_pos[1], TEMP_SLOT
    await session.flush()

    b.zone, b.layer, b.slot = a_pos
    b.led_index = a_led
    await session.flush()

    a.zone, a.layer, a.slot = b_pos
    a.led_index = b_led
    await session.flush()

    session.add(Transaction(
        kind="adjust", delta=0, source=source,
        detail=(f"互换 {a.name}（{_position(*a_pos)}）与 "
                f"{b.name}（{_position(*b_pos)}）"),
    ))
    await undo_service.record(
        session, f"互换 {a.name} 与 {b.name}",
        {"op": "snapshot_many", "items": before},
    )
    await session.commit()

    # 位置变了，灯带按新库存重新点亮各自槽位
    events.emit("stock.changed", a)
    events.emit("stock.changed", b)
    return a, b


async def update_component(
    session: AsyncSession, component: Component, patch: dict, source: str = "ui"
) -> Component:
    """属性/搬家修改（不允许直接改库存），同事务提交。"""
    changed = []
    before = undo_service.snapshot(component) if patch else None

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
        component.display_tags = _dump_display_tags(
            patch.get("tags", _load_tags(component.tags)),
            patch["display_tags"],
        )
        changed.append("display_tags")
    elif "tags" in patch:
        # 只改了标签：展示标签里已不存在的项同步移除
        component.display_tags = _dump_display_tags(
            patch["tags"], _load_tags(component.display_tags)
        )
    if "display_fields" in patch:
        component.display_fields = _dump_fields(patch["display_fields"])
        changed.append("display_fields")
    if "card_items" in patch:
        component.card_items = _dump_card_items(
            patch["card_items"], patch.get("tags", _load_tags(component.tags))
        )
        changed.append("card_items")
    elif "tags" in patch:
        # 标签被删：统一顺序里的 #token 同步清理
        component.card_items = _dump_card_items(
            json.loads(component.card_items or "[]"), patch["tags"]
        )

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
        await session.flush()
        await undo_service.record(
            session, f"修改 {component.name}：{', '.join(changed)}",
            {"op": "snapshot", "id": component.id, "before": before},
        )
    await session.commit()
    return component


async def delete_component(
    session: AsyncSession, component: Component, source: str = "ui"
) -> None:
    """删除元件并留审计快照，同事务提交。"""
    snapshot = (f"删除元件 {component.name}（{_position(component.zone, component.layer, component.slot)}，"
                f"库存 {component.quantity}，灯 {component.led_index}）")
    payload = undo_service.snapshot(component)
    session.add(Transaction(
        kind="delete", delta=0, source=source, detail=snapshot,
    ))
    await undo_service.record(
        session, f"删除 {component.name}",
        {"op": "delete", "id": component.id, "before": payload},
    )
    await session.delete(component)
    await session.commit()
    events.emit("component.removed", component)


async def change_stock(
    session: AsyncSession,
    component: Component,
    delta: int,
    note: str | None = None,
    source: str = "ui",
    commit: bool = True,
    project_before: dict | None = None,
) -> Component:
    """入/出库：负数为出库，出库带行级原子保护，防并发扣成负数。"""
    if delta == 0:
        raise ValueError("delta 不能为 0")
    before = undo_service.snapshot(component)

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
    await session.flush()
    undo_payload = {"op": "snapshot", "id": component.id, "before": before}
    if project_before is not None:
        undo_payload["project"] = project_before
    await undo_service.record(
        session, f"{verb} {abs(delta)} 个 · {component.name}",
        undo_payload,
    )
    if commit:
        await session.commit()
        events.emit("stock.changed", component)
    return component
