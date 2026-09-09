"""布局配置接口：读写货架网格尺寸，修改后前端即时重渲染。"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.db import get_session
from app.models import LayoutConfig

router = APIRouter(prefix="/api/v1/layout", tags=["layout"])


async def get_layout_row(session: AsyncSession) -> LayoutConfig:
    row = await session.scalar(select(LayoutConfig).where(LayoutConfig.id == 1))
    if row is None:
        raise HTTPException(status_code=500, detail="布局配置缺失，请先完成初始化")
    return row


def _zone_names(row: LayoutConfig) -> list[str]:
    """把 JSON 列读成列表（脏数据容错）。"""
    try:
        parsed = json.loads(row.zone_names or "[]")
        return [str(x)[:24] for x in parsed] if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


def _dump_zone_names(names: list[str], count: int) -> str:
    """规范化并序列化：数量与区数对齐，超长截断，空串表示「第N区」。"""
    cleaned = [str(x).strip()[:24] for x in (names or [])]
    while len(cleaned) < count:
        cleaned.append("")
    return json.dumps(cleaned[:count], ensure_ascii=False)


@router.get("", response_model=schemas.LayoutOut)
async def read_layout(session: AsyncSession = Depends(get_session)) -> dict:
    row = await get_layout_row(session)
    return {
        "zone_count": row.zone_count,
        "layer_count": row.layer_count,
        "row_count": row.row_count,
        "col_count": row.col_count,
        "updated_at": row.updated_at,
        "zone_names": _zone_names(row),
    }


@router.put("", response_model=schemas.LayoutOut)
async def update_layout(
    body: schemas.LayoutUpdate, session: AsyncSession = Depends(get_session)
) -> LayoutConfig:
    row = await get_layout_row(session)
    row.zone_count = body.zone_count
    row.layer_count = body.layer_count
    row.row_count = body.row_count
    row.col_count = body.col_count
    row.zone_names = _dump_zone_names(body.zone_names, body.zone_count)
    await session.commit()
    return {
        "zone_count": row.zone_count,
        "layer_count": row.layer_count,
        "row_count": row.row_count,
        "col_count": row.col_count,
        "updated_at": row.updated_at,
        "zone_names": _zone_names(row),
    }