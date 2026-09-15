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
    DEFAULT_LAYOUT, Component, ComponentSlot, LayoutConfig, Transaction,
)
from app.services.stock import _dump_display_tags, _dump_tags

router = APIRouter(prefix="/api/v1", tags=["system"])

# 前端确认框要求手输的确认词（改这里要同步改 AppSettingsDialog.vue）
RESET_CONFIRM_WORD = "清空"


@router.get("/system/status")
async def system_status() -> dict:
    """返回 {mode: serial|mock, connected, device, error}。"""
    return get_manager().status()


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
) -> Path:
    """整份导出为 JSON（UTF-8，中文不转义），供用户事后手工找回数据。"""
    payload = {
        "app": "ChipNest",
        "reason": "reset",
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

    # 先备份再删：备份写不成功就直接报错，数据保持原样
    try:
        backup = _write_backup(components, transactions, layout)
    except OSError as exc:
        logger.exception("清空前的备份写入失败")
        raise HTTPException(status_code=500,
                            detail=f"备份写入失败，已取消清空：{exc}") from exc

    led_indexes = [c.led_index for c in components if c.led_index is not None]

    await session.execute(delete(Transaction))
    await session.execute(delete(Component))
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
    await get_manager().clear_leds(led_indexes)

    logger.info("已清空数据：元件 {} 个、流水 {} 条、布局重置={}，备份 {}",
                len(components), len(transactions), body.reset_layout, backup)
    return {
        "deleted_components": len(components),
        "deleted_transactions": len(transactions),
        "backup_path": str(backup),
        "layout_reset": bool(body.reset_layout),
    }
