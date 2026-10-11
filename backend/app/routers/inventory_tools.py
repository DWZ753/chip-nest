"""库存盘点与采购需求汇总。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import events, schemas
from app.db import get_session
from app.models import BomProject, Component, Transaction
from app.routers.bom_projects import build_project_plan
from app.services import undo
from app.services.bom_projects import project_out

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])


@router.post("/stocktake", response_model=schemas.StocktakeResult)
async def stocktake(
    body: schemas.StocktakeRequest, session: AsyncSession = Depends(get_session),
):
    """@brief 按元件整体盘点；账面数量变化则整批取消。"""
    ids = [item.component_id for item in body.entries]
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=422, detail="盘点元件重复")
    await session.execute(text("BEGIN IMMEDIATE"))
    rows = {item.id: item for item in (await session.scalars(
        select(Component).where(Component.id.in_(ids)),
    )).all()}
    item = component = None
    for item in body.entries:
        component = rows.get(item.component_id)
        if component is None or component.quantity != item.expected_quantity:
            raise HTTPException(status_code=409, detail="盘点期间库存已变化")
    changed = [item for item in body.entries
               if item.quantity != item.expected_quantity]
    if changed:
        await undo.record(session, f"库存盘点 · {len(changed)} 个元件", {
            "op": "snapshot_many", "stocktake": True,
            "items": [{"id": item.component_id,
                       "before": undo.snapshot(rows[item.component_id])}
                      for item in changed],
        })
    for item in changed:
        component = rows[item.component_id]
        component.quantity = item.quantity
        session.add(Transaction(
            kind="stocktake", component_id=component.id, source="ui",
            delta=item.quantity - item.expected_quantity,
            detail=(f"盘点 {component.name}：{item.expected_quantity} → "
                    f"{item.quantity}" + (f" · {body.note}" if body.note else "")),
        ))
    await session.commit()
    for item in changed:
        events.emit("stock.changed", rows[item.component_id])
    return {"changed": len(changed),
            "components": [schemas.ComponentOut.model_validate(rows[key])
                           for key in ids]}


@router.post("/replenishment", response_model=schemas.ReplenishmentOut)
async def replenishment(
    body: schemas.ReplenishmentRequest,
    session: AsyncSession = Depends(get_session),
):
    """@brief 汇总剩余项目需求，采购后仍保留补货阈值数量。"""
    components = {item.id: item for item in
                  (await session.scalars(select(Component))).all()}
    items: dict[str, schemas.ReplenishmentItem] = {}
    comp = row = project = step = line = data = None
    pending = 0
    for comp in components.values():
        items[str(comp.id)] = schemas.ReplenishmentItem(
            component_id=comp.id, name=comp.name, value=comp.value or "",
            package=comp.package or "",
            manufacturer_part=comp.manufacturer_part or "",
            supplier_part=comp.supplier_part or "", available=comp.quantity,
            threshold=comp.threshold if body.include_thresholds else 0,
        )
    for project_id in set(body.project_ids):
        row = await session.get(BomProject, project_id)
        if row is None:
            raise HTTPException(status_code=404, detail="BOM 项目不存在")
        project = project_out(row)
        data = await build_project_plan(
            session, project.lines, project.copies, project.selections,
            project.plan.steps[:project.cursor],
        )
        steps = data.steps[project.cursor:]
        missing, choices = data.missing, data.choices
        for step in steps:
            key = str(step.component.id)
            if key not in items:
                items[key] = schemas.ReplenishmentItem(
                    name=step.component.name, value=step.component.value or "",
                    package=step.component.package or "", unresolved=True,
                )
            items[key].demand += step.quantity
        for line in missing:
            if line.component_id is not None and str(line.component_id) in items:
                items[str(line.component_id)].demand += line.quantity
            else:
                key = "missing:" + repr((line.name, line.value, line.package,
                                         line.raw))
                if key not in items:
                    original = next((item for item in project.lines
                                     if item.raw == line.raw), None)
                    items[key] = schemas.ReplenishmentItem(
                        name=line.name or line.raw, value=line.value or "",
                        package=line.package or "", unresolved=True,
                        manufacturer_part=(original.manufacturer_part or "")
                        if original else "",
                        supplier_part=(original.supplier_part or "")
                        if original else "",
                    )
                items[key].demand += line.quantity
        pending += len(choices)
    result = []
    for item in items.values():
        item.purchase = max(0, item.demand + item.threshold - item.available)
        if item.purchase:
            result.append(item)
    return {"items": result, "pending_choices": pending}
