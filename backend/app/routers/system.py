"""系统接口：HAL 状态、数据清空（一键回到干净初始状态）。

清空语义（POST /api/v1/system/reset）：
- 先把手头数据整份写进 JSON 备份（与数据库同目录的 backups/），写失败即中止，
  绝不出现「备份没落盘但数据已删」；
- 再删空元件表与审计流水表，可选把布局恢复为初始的 1 区 x 3 层 x 1 行 4 列；
- 灯带上还亮着的灯位一并熄灭；
- 清空后流水表是空的（保持真正的干净状态），操作痕迹留在日志与备份文件里。
"""

import datetime as dt
import json
from pathlib import Path
from typing import Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import config, schemas
from app.db import get_session
from app.hal.manager import get_manager
from app.models import (
    DEFAULT_LAYOUT, BlockedSlot, Component, ComponentSlot, LayoutConfig,
    Transaction, UndoEntry,
)
from app.services import undo as undo_service
from app.services.search import build_search_text
from app.services.stock import _dump_display_tags, _dump_tags

router = APIRouter(prefix="/api/v1", tags=["system"])

# 前端确认框要求手输的确认词（改这里要同步改 AppSettingsDialog.vue）
RESET_CONFIRM_WORD = "清空"
RESTORE_CONFIRM_WORD = "恢复"


@router.get("/system/status")
async def system_status() -> dict:
    """返回 {mode: serial|mock, connected, device, error}。"""
    return get_manager().status()


@router.post("/system/guide-led", response_model=schemas.GuideLedResult)
async def set_guide_led(
    body: schemas.GuideLedRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """设置或清除 BOM 引导灯位。"""
    component = None
    if body.component_id is not None:
        component = await session.get(Component, body.component_id)
        if component is None:
            raise HTTPException(status_code=404, detail="元件不存在")
    await get_manager().set_guide_led(component)
    return {"ok": True}


@router.get("/system/data-summary", response_model=schemas.DataSummaryOut)
async def data_summary(session: AsyncSession = Depends(get_session)) -> dict:
    """当前有多少元件与流水：都为空时前端把「清空所有数据」按钮禁掉。"""
    components = await session.scalar(select(func.count()).select_from(Component)) or 0
    transactions = await session.scalar(select(func.count()).select_from(Transaction)) or 0
    return {
        "components": components,
        "transactions": transactions,
        "empty": components == 0 and transactions == 0,
    }


@router.post("/system/reindex-leds", response_model=schemas.ReindexResult)
async def reindex_leds(session: AsyncSession = Depends(get_session)) -> dict:
    """按 区 → 层 → 格 重排灯带序号。

    用途：老版本自动分配灯号有 bug（多个格子共用一颗灯），重排一次让
    灯带序号与槽位顺序严格对应，引导取料就不会点错格。
    """
    rows = list((await session.scalars(
        select(Component).order_by(Component.zone, Component.layer, Component.slot)
    )).all())
    changed = 0
    for index, comp in enumerate(rows):
        if comp.led_index != index:
            comp.led_index = index
            changed += 1
    if changed:
        session.add(Transaction(
            kind="adjust", delta=0, source="ui",
            detail=f"重排灯带序号：{len(rows)} 个元件按 区→层→格 顺序编号（{changed} 个有变动）",
        ))
    await session.commit()
    logger.info("重排灯带序号：共 {} 个元件，{} 个有变动", len(rows), changed)
    return {"total": len(rows), "changed": changed}


@router.get("/system/undo", response_model=schemas.UndoPeekOut)
async def peek_undo(session: AsyncSession = Depends(get_session)) -> dict:
    """看一眼下一步会撤销什么（界面用它显示按钮状态）。"""
    info = await undo_service.peek(session)
    if info is None:
        return {"label": "", "ts": None}
    return {"label": info["label"], "ts": info["ts"]}


@router.post("/system/undo", response_model=schemas.UndoOut)
async def undo_last(session: AsyncSession = Depends(get_session)) -> dict:
    """撤销最近一次操作。"""
    return await undo_service.undo_last(session)


def _group_key(comp: Component) -> tuple:
    """合并分组的键：名称 + 标称值 + 封装（都去空白、忽略大小写）。"""
    return (
        (comp.name or "").strip().lower(),
        (comp.value or "").strip().lower(),
        (comp.package or "").strip().lower(),
    )


@router.post("/system/merge-duplicates", response_model=schemas.MergeResultOut)
async def merge_duplicates(
    dry_run: bool = Query(default=False, description="只预览不落库"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """把「同名 + 同标称值 + 同封装」的多条元件合并成一条。

    保留 id 最小的那条：数量相加、标签取并集，其余记录的格子变成它的占用格，
    多余记录删除。dry_run=1 时只返回预览。
    """
    rows = list((await session.scalars(
        select(Component).order_by(Component.id)
    )).all())

    buckets: dict[tuple, list[Component]] = {}
    for comp in rows:
        buckets.setdefault(_group_key(comp), []).append(comp)

    groups: list[dict] = []
    merged_components = 0
    for members in buckets.values():
        if len(members) < 2:
            continue
        keep, rest = members[0], members[1:]
        total = sum(m.quantity for m in members)
        moved = sum(1 + len(m.slots) for m in rest)

        groups.append({
            "name": keep.name,
            "value": keep.value or "",
            "package": keep.package or "",
            "keep_id": keep.id,
            "member_ids": [m.id for m in members],
            "total_quantity": total,
            "moved_slots": moved,
        })
        if dry_run:
            continue

        # 撤销快照：保留者在前，被并掉的在后（还原时先让保留者松开这些格子）
        undo_items = [{"id": keep.id, "before": undo_service.snapshot(keep)}]
        for other in rest:
            undo_items.append({"id": other.id, "before": undo_service.snapshot(other)})
        await undo_service.record(
            session, f"合并重复元件 {keep.name}（{len(members)} 条）",
            {"op": "snapshot_many", "items": undo_items},
        )

        keep.quantity = total
        tags = list(_as_list(keep.tags))
        for other in rest:
            for tag in _as_list(other.tags):
                if tag not in tags and len(tags) < 8:
                    tags.append(tag)
            for extra in list(other.slots):
                keep.slots.append(ComponentSlot(
                    component_id=keep.id, zone=extra.zone, layer=extra.layer,
                    slot=extra.slot,
                ))
            keep.slots.append(ComponentSlot(
                component_id=keep.id, zone=other.zone, layer=other.layer,
                slot=other.slot,
            ))
            await session.delete(other)
            merged_components += 1
        keep.tags = _dump_tags(tags)
        keep.display_tags = _dump_display_tags(tags, _as_list(keep.display_tags))
        session.add(Transaction(
            kind="adjust", delta=0, source="ui",
            detail=(f"合并重复元件：{keep.name} 等 {len(members)} 条 → 一条，"
                    f"数量合计 {total}，多出的 {moved} 个格子转为占用格"),
        ))
        await session.flush()

    if not dry_run and groups:
        await session.commit()

    logger.info("合并重复元件：{} 组（dry_run={}）", len(groups), dry_run)
    return {
        "dry_run": dry_run,
        "groups": groups,
        "merged_groups": 0 if dry_run else len(groups),
        "merged_components": 0 if dry_run else merged_components,
    }


def _as_list(raw: Optional[str]) -> list:
    """JSON 文本列读成列表（脏数据容错），只为备份可读。"""
    try:
        parsed = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _backup_path() -> Path:
    """备份文件名带时间戳；同一秒内重复清空时自动加序号。"""
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = config.backup_dir() / f"chipnest-backup-{stamp}.json"
    index = 1
    while path.exists():
        path = config.backup_dir() / f"chipnest-backup-{stamp}-{index}.json"
        index += 1
    return path


def _write_backup(
    components: Sequence[Component],
    transactions: Sequence[Transaction],
    layout: Optional[LayoutConfig],
    blocked_slots: Sequence[BlockedSlot] = (),
    reason: str = "reset",
) -> Path:
    """整份导出为 JSON（UTF-8，中文不转义），供用户事后手工找回数据。"""
    payload = {
        "app": "ChipNest",
        "reason": reason,
        "exported_at": dt.datetime.now().isoformat(timespec="seconds"),
        "layout": None if layout is None else {
            "zone_count": layout.zone_count,
            "layer_count": layout.layer_count,
            "row_count": layout.row_count,
            "col_count": layout.col_count,
            "zone_names": _as_list(layout.zone_names),
            "zone_sizes": _as_list(layout.zone_sizes),
            "zone_layers": _as_list(layout.zone_layers),
        },
        "components": [
            schemas.ComponentOut.model_validate(c).model_dump() for c in components
        ],
        "transactions": [
            schemas.TransactionOut.model_validate(t).model_dump(mode="json")
            for t in transactions
        ],
        "blocked_slots": [
            schemas.BlockedSlotOut.model_validate(slot).model_dump()
            for slot in blocked_slots
        ],
    }
    path = _backup_path()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


@router.post("/system/reset", response_model=schemas.ResetResult)
async def reset_data(
    body: schemas.ResetRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """清空所有内容：删光元件与操作流水，布局可选恢复初始状态。"""
    if body.confirm.strip() != RESET_CONFIRM_WORD:
        raise HTTPException(
            status_code=400,
            detail=f"请输入「{RESET_CONFIRM_WORD}」两个字确认后再清空",
        )

    components = list((await session.scalars(select(Component))).all())
    transactions = list((await session.scalars(select(Transaction))).all())
    layout = await session.scalar(select(LayoutConfig).where(LayoutConfig.id == 1))
    blocked_slots = list((await session.scalars(select(BlockedSlot))).all())

    # 先备份再删：备份写不成功就直接报错，数据保持原样
    try:
        backup = _write_backup(components, transactions, layout, blocked_slots)
    except OSError as exc:
        logger.exception("清空前的备份写入失败")
        raise HTTPException(status_code=500,
                            detail=f"备份写入失败，已取消清空：{exc}") from exc

    led_indexes = [c.led_index for c in components if c.led_index is not None]

    await session.execute(delete(Transaction))
    await session.execute(delete(Component))
    await session.execute(delete(BlockedSlot))   # 不可用标记属于仓库状态，一并清掉
    await session.execute(delete(UndoEntry))     # 撤销栈也清空
    if body.reset_layout and layout is not None:
        layout.zone_count = DEFAULT_LAYOUT["zone_count"]
        layout.layer_count = DEFAULT_LAYOUT["layer_count"]
        layout.row_count = DEFAULT_LAYOUT["row_count"]
        layout.col_count = DEFAULT_LAYOUT["col_count"]
        layout.zone_names = "[]"
        layout.zone_sizes = "[]"
        layout.zone_layers = "[]"
    await session.commit()

    # 灯带复位属于收尾动作，硬件不在线也不能影响清空结果
    manager = get_manager()
    await manager.set_guide_led(None)
    await manager.clear_leds(led_indexes)

    logger.info("已清空数据：元件 {} 个、流水 {} 条、布局重置={}，备份 {}",
                len(components), len(transactions), body.reset_layout, backup)
    return {
        "deleted_components": len(components),
        "deleted_transactions": len(transactions),
        "backup_path": str(backup),
        "layout_reset": bool(body.reset_layout),
    }


def _validate_backup(backup: schemas.BackupSnapshot) -> None:
    """校验备份中的元件、附加格和停用格没有位置冲突。"""
    seen_ids: set[int] = set()
    occupied: set[tuple[int, int, int]] = set()
    for component in backup.components:
        if component.id < 1 or component.id in seen_ids:
            raise HTTPException(
                status_code=422, detail="备份中的元件编号重复或无效"
            )
        seen_ids.add(component.id)
        if component.quantity < 0 or component.threshold < 0:
            raise HTTPException(status_code=422, detail="备份中的库存数量无效")
        if component.led_index is not None and component.led_index < 0:
            raise HTTPException(status_code=422, detail="备份中的灯带序号无效")

        positions = [(component.zone, component.layer, component.slot)]
        positions.extend(
            (slot.zone, slot.layer, slot.slot) for slot in component.slots
        )
        for position in positions:
            if position[0] < 1 or position[1] < 1 or position[2] < 0:
                raise HTTPException(
                    status_code=422, detail="备份中的格子位置无效"
                )
            if position in occupied:
                raise HTTPException(
                    status_code=422, detail="备份中的格子位置重复"
                )
            occupied.add(position)

    blocked_seen: set[tuple[int, int, int]] = set()
    for slot in backup.blocked_slots:
        position = (slot.zone, slot.layer, slot.slot)
        if position[0] < 1 or position[1] < 1 or position[2] < 0:
            raise HTTPException(status_code=422, detail="备份中的停用格位置无效")
        if position in occupied or position in blocked_seen:
            raise HTTPException(
                status_code=422, detail="备份中的格子位置重复"
            )
        blocked_seen.add(position)

    transaction_ids: set[int] = set()
    for transaction in backup.transactions:
        if transaction.id < 1 or transaction.id in transaction_ids:
            raise HTTPException(status_code=422, detail="备份中的流水编号重复或无效")
        transaction_ids.add(transaction.id)
        if (transaction.component_id is not None
                and transaction.component_id not in seen_ids):
            raise HTTPException(status_code=422, detail="备份中的流水引用了不存在的元件")


@router.post("/system/restore", response_model=schemas.RestoreResult)
async def restore_data(
    body: schemas.RestoreRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """从 JSON 备份恢复仓库内容；覆盖前先备份当前数据。"""
    if body.confirm.strip() != RESTORE_CONFIRM_WORD:
        raise HTTPException(
            status_code=400,
            detail=f"请输入「{RESTORE_CONFIRM_WORD}」两个字确认后再恢复",
        )

    _validate_backup(body.backup)
    current_components = list((await session.scalars(select(Component))).all())
    current_transactions = list((await session.scalars(select(Transaction))).all())
    current_layout = await session.scalar(
        select(LayoutConfig).where(LayoutConfig.id == 1)
    )
    current_blocked = list((await session.scalars(select(BlockedSlot))).all())
    try:
        backup_path = _write_backup(
            current_components, current_transactions, current_layout,
            current_blocked, reason="restore",
        )
    except OSError as exc:
        logger.exception("恢复前的备份写入失败")
        raise HTTPException(
            status_code=500, detail=f"备份写入失败，已取消恢复：{exc}"
        ) from exc

    old_leds = [c.led_index for c in current_components]
    new_leds = [c.led_index for c in body.backup.components]
    try:
        await session.execute(delete(Transaction))
        await session.execute(delete(ComponentSlot))
        await session.execute(delete(Component))
        await session.execute(delete(BlockedSlot))
        await session.execute(delete(UndoEntry))

        layout_data = body.backup.layout
        if layout_data is None:
            layout_values = {
                **DEFAULT_LAYOUT,
                "zone_names": [],
                "zone_sizes": [],
                "zone_layers": [],
            }
        else:
            layout_values = layout_data.model_dump()
        layout = current_layout or LayoutConfig(id=1)
        layout.zone_count = layout_values["zone_count"]
        layout.layer_count = layout_values["layer_count"]
        layout.row_count = layout_values["row_count"]
        layout.col_count = layout_values["col_count"]
        layout.zone_names = json.dumps(
            layout_values["zone_names"], ensure_ascii=False
        )
        layout.zone_sizes = json.dumps(layout_values["zone_sizes"])
        layout.zone_layers = json.dumps(layout_values["zone_layers"])
        session.add(layout)

        restored_components: list[Component] = []
        for item in body.backup.components:
            component = Component(
                id=item.id,
                name=item.name,
                value=item.value,
                package=item.package,
                manufacturer_part=item.manufacturer_part,
                supplier_part=item.supplier_part,
                tags=json.dumps(item.tags, ensure_ascii=False),
                display_tags=json.dumps(item.display_tags, ensure_ascii=False),
                display_fields=json.dumps(item.display_fields),
                card_items=json.dumps(item.card_items, ensure_ascii=False),
                quantity=item.quantity,
                threshold=item.threshold,
                zone=item.zone,
                layer=item.layer,
                slot=item.slot,
                led_index=item.led_index,
                search_text=build_search_text(
                    item.name, item.value or "", item.package or "",
                    item.manufacturer_part or "", " ".join(item.tags),
                ),
            )
            component.slots = [
                ComponentSlot(zone=slot.zone, layer=slot.layer, slot=slot.slot)
                for slot in item.slots
            ]
            session.add(component)
            restored_components.append(component)

        for slot in body.backup.blocked_slots:
            session.add(BlockedSlot(zone=slot.zone, layer=slot.layer, slot=slot.slot))
        for item in body.backup.transactions:
            session.add(Transaction(
                id=item.id,
                ts=item.ts,
                kind=item.kind,
                component_id=item.component_id,
                delta=item.delta,
                detail=item.detail,
                source=item.source,
            ))
        session.add(Transaction(
            kind="adjust",
            delta=0,
            source="system",
            detail=(f"从备份恢复：元件 {len(body.backup.components)} 个，"
                    f"流水 {len(body.backup.transactions)} 条，"
                    f"停用格 {len(body.backup.blocked_slots)} 个"),
        ))
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    manager = get_manager()
    await manager.set_guide_led(None)
    await manager.clear_leds(old_leds + new_leds)
    for component in restored_components:
        await manager.sync_component_led(component)

    logger.info("从备份恢复：元件 {} 个、流水 {} 条、停用格 {} 个，覆盖前备份 {}",
                len(body.backup.components), len(body.backup.transactions),
                len(body.backup.blocked_slots), backup_path)
    return {
        "components": len(body.backup.components),
        "transactions": len(body.backup.transactions),
        "blocked_slots": len(body.backup.blocked_slots),
        "backup_path": str(backup_path),
    }
