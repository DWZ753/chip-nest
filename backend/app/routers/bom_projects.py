"""持久化 BOM 项目；库存扣减和取料进度在同一事务完成。"""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import events, schemas
from app.db import get_session
from app.models import BomProject, Component, Transaction
from app.routers.bom import _build_plan
from app.services.bom import BomLine
from app.services.bom_projects import project_out, scaled_lines
from app.services.stock import StockShortage, change_stock

router = APIRouter(prefix="/api/v1/bom/projects", tags=["bom-projects"])


async def require_project(session: AsyncSession, project_id: int) -> BomProject:
    """@brief 找到项目，否则给出明确的不存在状态。"""
    project = await session.get(BomProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="BOM 项目不存在")
    return project


@router.get("", response_model=list[schemas.BomProjectOut])
async def list_projects(session: AsyncSession = Depends(get_session)):
    """@brief 按最近更新时间返回已保存项目。"""
    rows = (await session.scalars(
        select(BomProject).order_by(BomProject.updated_at.desc()),
    )).all()
    return [project_out(row) for row in rows]


async def save_project(
    session: AsyncSession, body: schemas.BomProjectSave,
    project_id: int | None = None,
) -> schemas.BomProjectOut:
    """@brief 验证版本与进度，重新规划后保存项目。"""
    await session.execute(text("BEGIN IMMEDIATE"))
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="项目名称为空")
    project = None
    if project_id is not None:
        project = await require_project(session, project_id)
        if body.revision != project.revision:
            raise HTTPException(status_code=409, detail="项目已变化")
        if project.cursor and (
            body.copies != project.copies
            or body.lines != project_out(project).lines
        ):
            raise HTTPException(status_code=409, detail="已取料项目清单已变化")
    finished = (project_out(project).plan.steps[:project.cursor]
                if project is not None else [])
    plan = await build_project_plan(
        session, body.lines, body.copies, body.selections, finished,
    )
    if project is None:
        project = BomProject(name=name, lines="[]", plan="{}")
        session.add(project)
    else:
        project.revision += 1
    project.name = name
    project.lines = json.dumps([line.model_dump() for line in body.lines],
                              ensure_ascii=False)
    project.selections = json.dumps(body.selections)
    project.copies = body.copies
    project.plan = plan.model_dump_json()
    session.add(Transaction(
        kind="project", delta=0, source="ui", detail=f"保存 BOM 项目：{name}",
    ))
    await session.commit()
    return project_out(project)


async def build_project_plan(
    session: AsyncSession, lines: list[schemas.BomLineOut], copies: int,
    selections: dict[int, int], finished: list[schemas.BomStepOut],
) -> schemas.BomPlanOut:
    """@brief 保留已取步骤，仅规划尚未取料的原始行。"""
    scaled = scaled_lines(lines, copies)
    if any(index < 0 or index >= len(lines) for index in selections):
        raise HTTPException(status_code=422, detail="BOM 匹配行无效")
    completed = {index for step in finished for index in step.line_indexes}
    indexes = [index for index, line in enumerate(scaled)
               if index not in completed and line.quantity > 0]
    if indexes:
        plan = await _build_plan(
            [BomLine(**scaled[index].model_dump()) for index in indexes],
            session, {index: selections[original]
                      for index, original in enumerate(indexes)
                      if original in selections},
        )
    else:
        plan = schemas.BomPlanOut(
            steps=[], missing=[], requested=0, complete=True,
        )
    step = choice = None
    for step in plan.steps:
        step.line_indexes = [indexes[index] for index in step.line_indexes]
    for choice in plan.choices:
        choice.line_index = indexes[choice.line_index]
    plan.steps = finished + plan.steps
    plan.requested = sum(line.quantity for line in scaled)
    return plan


@router.post("", response_model=schemas.BomProjectOut, status_code=201)
async def create_project(
    body: schemas.BomProjectSave, session: AsyncSession = Depends(get_session),
):
    """@brief 保存新项目或从旧项目新建制作副本。"""
    return await save_project(session, body)


@router.put("/{project_id}", response_model=schemas.BomProjectOut)
async def update_project(
    project_id: int, body: schemas.BomProjectSave,
    session: AsyncSession = Depends(get_session),
):
    """@brief 保存匹配并重新规划剩余取料行。"""
    return await save_project(session, body, project_id)


@router.get("/{project_id}", response_model=schemas.BomProjectOut)
async def get_project(
    project_id: int, session: AsyncSession = Depends(get_session),
):
    """@brief 恢复已保存的清单、匹配关系和进度。"""
    return project_out(await require_project(session, project_id))


@router.delete("/{project_id}", response_model=schemas.ActionResult)
async def delete_project(
    project_id: int, session: AsyncSession = Depends(get_session),
):
    """@brief 删除项目记录，已经发生的出库保留。"""
    project = await require_project(session, project_id)
    session.add(Transaction(
        kind="project", delta=0, source="ui",
        detail=f"删除 BOM 项目：{project.name}",
    ))
    await session.delete(project)
    await session.commit()
    return {"ok": True}


@router.post("/{project_id}/pick", response_model=schemas.ProjectPickResult)
async def pick_project(
    project_id: int, body: schemas.ProjectPickRequest,
    session: AsyncSession = Depends(get_session),
):
    """@brief 原子扣库存并推进步骤；过期请求不能重复扣减。"""
    await session.execute(text("BEGIN IMMEDIATE"))
    project = await require_project(session, project_id)
    if project.cursor != body.cursor or project.revision != body.revision:
        raise HTTPException(status_code=409, detail="取料进度已变化")
    plan = schemas.BomPlanOut.model_validate_json(project.plan)
    if plan.choices or project.cursor >= len(plan.steps):
        raise HTTPException(status_code=409, detail="项目没有可执行的取料步骤")
    step = plan.steps[project.cursor]
    component = await session.get(Component, step.component.id)
    if component is None:
        raise HTTPException(status_code=409, detail="项目元件已不存在")
    fields = ("name", "value", "package", "manufacturer_part", "supplier_part")
    if any((getattr(component, field) or "").strip().casefold()
           != (getattr(step.component, field) or "").strip().casefold()
           for field in fields):
        raise HTTPException(status_code=409, detail="项目元件规格已变化")
    try:
        await change_stock(
            session, component, -step.quantity, source="guide",
            note=f"BOM 项目：{project.name}", commit=False,
            project_before={"id": project.id, "cursor": project.cursor},
        )
    except StockShortage as exc:
        raise HTTPException(status_code=409, detail={
            "message": str(exc), "available": exc.available,
        }) from exc
    project.cursor += 1
    project.revision += 1
    await session.commit()
    events.emit("stock.changed", component)
    return {"component": schemas.ComponentOut.model_validate(component),
            "project": project_out(project)}
