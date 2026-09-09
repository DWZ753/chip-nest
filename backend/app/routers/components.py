"""元件接口：建档/查询/修改/删除 + 入出库（原子扣减）。

查询支持模糊检索：q 命中「名称+值+封装+拼音首字母」预计算文本，
如 "0603" 可搜出所有 0603 封装，字母 "dz" 可搜出「电阻」。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.db import get_session
from app.models import Component
from app.services import stock as stock_service

router = APIRouter(prefix="/api/v1/components", tags=["components"])


async def _get_component(session: AsyncSession, component_id: int) -> Component:
    component = await session.get(Component, component_id)
    if component is None:
        raise HTTPException(status_code=404, detail=f"元件 #{component_id} 不存在")
    return component


def _map_error(exc: Exception) -> HTTPException:
    """把库存域异常映射为带中文提示的 HTTP 错误。"""
    if isinstance(exc, stock_service.PositionBusy):
        return HTTPException(status_code=409, detail=f"槽位已被占用：{exc.occupant}")
    if isinstance(exc, stock_service.OutOfLayout):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, stock_service.StockShortage):
        return HTTPException(status_code=409, detail={"message": str(exc), "available": exc.available})
    return HTTPException(status_code=500, detail=f"库存操作失败：{exc}")


@router.get("", response_model=list[schemas.ComponentOut])
async def list_components(
    q: str | None = Query(default=None, max_length=64),
    zone: int | None = Query(default=None, ge=1),
    layer: int | None = Query(default=None, ge=1),
    limit: int = Query(default=2000, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
) -> list[Component]:
    """元件列表：可按 q 模糊检索、按区/层过滤，按位置排序。"""
    stmt = select(Component).order_by(Component.zone, Component.layer, Component.slot)
    if zone is not None:
        stmt = stmt.where(Component.zone == zone)
    if layer is not None:
        stmt = stmt.where(Component.layer == layer)
    if q and q.strip():
        stmt = stmt.where(Component.search_text.contains(q.strip().lower(), autoescape=True))
    stmt = stmt.limit(limit)
    rows = (await session.scalars(stmt)).all()
    return list(rows)


@router.post("", response_model=schemas.ComponentOut, status_code=201)
async def create_component(
    body: schemas.ComponentCreate, session: AsyncSession = Depends(get_session)
) -> Component:
    try:
        return await stock_service.create_component(
            session, name=body.name.strip(), value=body.value, package=body.package,
            quantity=body.quantity, threshold=body.threshold,
            zone=body.zone, layer=body.layer, slot=body.slot, led_index=body.led_index,
            manufacturer_part=body.manufacturer_part,
            supplier_part=body.supplier_part,
            tags=body.tags,
            display_tags=body.display_tags,
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="槽位已被占用（并发写入）")
    except stock_service.PositionBusy as exc:
        raise HTTPException(status_code=409, detail=f"槽位已被占用：{exc.occupant}")
    except stock_service.OutOfLayout as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{component_id}", response_model=schemas.ComponentOut)
async def get_component(
    component_id: int, session: AsyncSession = Depends(get_session)
) -> Component:
    return await _get_component(session, component_id)


@router.patch("/{component_id}", response_model=schemas.ComponentOut)
async def update_component(
    component_id: int,
    body: schemas.ComponentUpdate,
    session: AsyncSession = Depends(get_session),
) -> Component:
    component = await _get_component(session, component_id)
    patch = body.model_dump(exclude_unset=True)

    # 空串清空可选字段；name/threshold 不允许显式置空（视为未提供）
    if patch.get("value") == "":
        patch["value"] = None
    if patch.get("package") == "":
        patch["package"] = None
    if patch.get("manufacturer_part") == "":
        patch["manufacturer_part"] = None
    if patch.get("supplier_part") == "":
        patch["supplier_part"] = None
    if patch.get("name") is None:
        patch.pop("name", None)
    if patch.get("threshold") is None:
        patch.pop("threshold", None)

    try:
        return await stock_service.update_component(session, component, patch)
    except (stock_service.PositionBusy, stock_service.OutOfLayout) as exc:
        raise _map_error(exc)


@router.delete("/{component_id}", status_code=204)
async def delete_component(
    component_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    component = await _get_component(session, component_id)
    await stock_service.delete_component(session, component)


@router.post("/{component_id}/stock", response_model=schemas.ComponentOut)
async def change_stock(
    component_id: int,
    body: schemas.StockChange,
    session: AsyncSession = Depends(get_session),
) -> Component:
    """入出库：delta 为负表示出库，库存不足返回 409 + available。"""
    if body.delta == 0:
        raise HTTPException(status_code=422, detail="delta 不能为 0")
    component = await _get_component(session, component_id)
    try:
        return await stock_service.change_stock(
            session, component, body.delta, note=body.note, source=body.source
        )
    except stock_service.StockShortage as exc:
        raise HTTPException(
            status_code=409, detail={"message": str(exc), "available": exc.available}
        )