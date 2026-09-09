"""BOM 导入接口：粘贴文本 → 解析预览 → 库存匹配规划 → 逐格引导取料。

/bom/pick 复用 services/stock.change_stock 的原子扣减，因此与 /stock
共享同一份防超卖与 409 语义；source 固定为 guide，审计 kind=bom_pick。
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.db import get_session
from app.models import Component
from app.services import bom as bom_service
from app.services import stock as stock_service

router = APIRouter(prefix="/api/v1/bom", tags=["bom"])


@router.post("/import", response_model=schemas.BomParseOut)
async def import_bom_excel(
    file: UploadFile = File(...),
) -> schemas.BomParseOut:
    """上传 .xlsx BOM 文件：识别常见表头后转成与 /bom/parse 同构的行列表。"""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="文件为空")
    try:
        lines = bom_service.parse_excel_bytes(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return schemas.BomParseOut(
        lines=[schemas.BomLineOut(**line.to_dict()) for line in lines],
        total_quantity=sum(line.quantity for line in lines),
    )


@router.post("/parse", response_model=schemas.BomParseOut)
async def parse_bom(body: schemas.BomImport) -> schemas.BomParseOut:
    """纯解析预览：只拆行还原四要素，不查库存、不落任何流水。"""
    lines = bom_service.parse_text(body.text)
    return schemas.BomParseOut(
        lines=[schemas.BomLineOut(**line.to_dict()) for line in lines],
        total_quantity=sum(line.quantity for line in lines),
    )


@router.post("/plan", response_model=schemas.BomPlanOut)
async def plan_bom(
    body: schemas.BomImport, session: AsyncSession = Depends(get_session)
) -> schemas.BomPlanOut:
    """解析 + 库存打分匹配：足料出引导步骤，缺料/找不到进 missing。"""
    lines = bom_service.parse_text(body.text)
    if not lines:
        raise HTTPException(status_code=422, detail="没有可识别的元件行")

    comps = list((await session.scalars(
        select(Component).order_by(Component.zone, Component.layer, Component.slot)
    )).all())
    plan = bom_service.plan_pure(lines, comps)

    steps = [
        schemas.BomStepOut(
            component=schemas.ComponentOut.model_validate(step["component"]),
            quantity=step["quantity"],
            line_indexes=step["line_indexes"],
        )
        for step in plan["steps"]
    ]
    missing = [schemas.BomMissingOut(**item) for item in plan["missing"]]
    return schemas.BomPlanOut(
        steps=steps, missing=missing,
        requested=plan["requested"], complete=not missing,
    )


@router.post("/pick", response_model=schemas.ComponentOut)
async def pick_for_bom(
    body: schemas.BomPick, session: AsyncSession = Depends(get_session)
) -> Component:
    """引导取料扣减：amount 由规划步骤给出，缺货时 409 提示补料。"""
    component = await session.get(Component, body.component_id)
    if component is None:
        raise HTTPException(status_code=404, detail=f"元件 #{body.component_id} 不存在")
    try:
        return await stock_service.change_stock(
            session, component, -body.amount,
            note="BOM 引导取料", source="guide",
        )
    except stock_service.StockShortage as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "available": exc.available},
        )