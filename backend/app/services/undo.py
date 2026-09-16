"""撤销栈：改元件之前先留快照，撤销时按快照还原。

设计取舍：不做"每种操作写一个逆操作"，而是**统一存快照**（位置 + 全部字段 +
附加占用格），撤销时整体还原 —— 搬家、改字段、改库存、加减占用格、删除都能覆盖；
互换存两条快照。栈只保留最近 30 条，落地在 undo_log 表（重启也不丢）。
"""

import json
from typing import Any, Optional

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BlockedSlot, Component, ComponentSlot, UndoEntry, utcnow

KEEP = 30

SNAPSHOT_FIELDS = (
    "name", "value", "package", "manufacturer_part", "supplier_part",
    "tags", "display_tags", "display_fields", "card_items",
    "quantity", "threshold", "zone", "layer", "slot", "led_index",
)


def snapshot(comp: Component) -> dict[str, Any]:
    """把元件拍成可 JSON 化的快照（含附加占用格）。"""
    data = {field: getattr(comp, field) for field in SNAPSHOT_FIELDS}
    data["slots"] = [
        {"zone": s.zone, "layer": s.layer, "slot": s.slot} for s in comp.slots
    ]
    return data


async def record(session: AsyncSession, label: str, payload: dict) -> None:
    """把一条撤销记录挂进当前事务（调用方负责 commit）。"""
    session.add(UndoEntry(
        label=label[:120],
        payload=json.dumps(payload, ensure_ascii=False),
        ts=utcnow(),
    ))
    await session.flush()
    # 只留最近 KEEP 条
    keep_ids = select(UndoEntry.id).order_by(UndoEntry.id.desc()).limit(KEEP)
    await session.execute(
        delete(UndoEntry).where(UndoEntry.id.not_in(keep_ids))
    )


async def peek(session: AsyncSession) -> Optional[dict]:
    """看一眼最新一条（给界面显示"将要撤销什么"）。"""
    row = await session.scalar(select(UndoEntry).order_by(UndoEntry.id.desc()).limit(1))
    if row is None:
        return None
    return {"id": row.id, "label": row.label, "ts": row.ts}


async def undo_last(session: AsyncSession) -> dict:
    """撤销最近一次操作。"""
    row = await session.scalar(select(UndoEntry).order_by(UndoEntry.id.desc()).limit(1))
    if row is None:
        return {"ok": False, "label": "", "message": "没有可撤销的操作"}

    payload = json.loads(row.payload or "{}")
    label = row.label
    touched: list[int] = []
    notes: list[str] = []

    op = payload.get("op")
    if op == "create":
        comp = await session.get(Component, payload.get("id"))
        if comp is not None:
            touched.append(comp.id)
            await session.delete(comp)
    elif op in ("snapshot", "delete", "snapshot_many"):
        items = payload.get("items") or [{
            "id": payload.get("id"),
            "before": payload.get("before") or {},
        }]
        if len(items) > 1:
            # 多个元件互相挡路（互换）：先各自停到临时槽位，再逐个还原
            from app.services.stock import TEMP_SLOT
            for offset, item in enumerate(items):
                comp = await session.get(Component, item.get("id")) if item.get("id") else None
                if comp is not None:
                    comp.slot = TEMP_SLOT - offset
                    await session.flush()
        for item in items:
            comp, note = await _restore(session, item.get("id"), item.get("before") or {})
            if comp is not None:
                touched.append(comp.id)
            if note:
                notes.append(note)
    else:
        return {"ok": False, "label": label, "message": f"这条操作不支持撤销：{label}"}

    await session.delete(row)
    await session.commit()
    logger.info("撤销：{}（影响 {} 个元件）", label, len(touched))
    message = "；".join(notes) if notes else "已还原"
    return {"ok": True, "label": label, "message": message,
            "component_ids": touched}


async def _restore(session: AsyncSession, comp_id: Optional[int],
                   data: dict) -> tuple[Optional[Component], str]:
    """按快照还原：元件还在就改回去，被删了就重建。返回 (元件, 说明)。"""
    from app.services.search import build_search_text
    from app.services.stock import ensure_position_free, first_free_position

    note = ""
    fields = {k: v for k, v in data.items() if k in SNAPSHOT_FIELDS}
    comp = await session.get(Component, comp_id) if comp_id else None

    if comp is None:
        target = (fields.get("zone"), fields.get("layer"), fields.get("slot"))
        try:
            await ensure_position_free(session, *target)
        except Exception:
            moved = await first_free_position(session)
            if moved is None:
                return None, "原位置已被占用，且没有空格可放"
            fields["zone"], fields["layer"], fields["slot"] = moved
            note = f"原位置已被占用，放到 {moved[0]}区/{moved[1]}层/{moved[2]}格"
        comp = Component(slots=[], **fields)
        comp.search_text = build_search_text(
            comp.name, comp.value or "", comp.package or "",
            comp.manufacturer_part or "", " ".join(json.loads(comp.tags or "[]")),
        )
        session.add(comp)
        await session.flush()
    else:
        target = (fields.get("zone", comp.zone), fields.get("layer", comp.layer),
                  fields.get("slot", comp.slot))
        # 先把非位置字段写回去，位置最后处理（否则会被下面的循环覆盖）
        for field, value in fields.items():
            if field in ("zone", "layer", "slot"):
                continue
            setattr(comp, field, value)
        if (comp.zone, comp.layer, comp.slot) != target:
            try:
                await ensure_position_free(session, *target, exclude_id=comp.id)
                comp.zone, comp.layer, comp.slot = target
            except Exception:
                note = "原位置已被占用，位置保持不动"
        tags = json.loads(comp.tags or "[]")
        comp.search_text = build_search_text(
            comp.name, comp.value or "", comp.package or "",
            comp.manufacturer_part or "", " ".join(tags),
        )
        await session.flush()

    # 附加占用格：先清空再按快照补回（占不到的位置跳过并说明）
    wanted = data.get("slots") or []
    for extra in list(comp.slots):
        comp.slots.remove(extra)
    await session.flush()
    blocked = {r for r in (await session.scalars(select(BlockedSlot))).all()}
    blocked_pos = {(b.zone, b.layer, b.slot) for b in blocked}
    skipped = 0
    for item in wanted:
        pos = (item.get("zone"), item.get("layer"), item.get("slot"))
        if pos in blocked_pos:
            skipped += 1
            continue
        try:
            await ensure_position_free(session, *pos, exclude_id=comp.id)
        except Exception:
            skipped += 1
            continue
        comp.slots.append(ComponentSlot(
            component_id=comp.id, zone=pos[0], layer=pos[1], slot=pos[2],
        ))
    if skipped and not note:
        note = f"{skipped} 个占用格已被占用，没有恢复"
    await session.flush()
    return comp, note
