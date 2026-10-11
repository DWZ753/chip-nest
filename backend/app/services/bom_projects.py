"""BOM 项目的结构化序列化与份数换算。"""
import json

from app import schemas
from app.models import BomProject


def project_out(project: BomProject) -> schemas.BomProjectOut:
    """@brief ORM 的 JSON 列转换为项目契约。"""
    return schemas.BomProjectOut(
        id=project.id, name=project.name,
        lines=json.loads(project.lines),
        selections=json.loads(project.selections), copies=project.copies,
        plan=json.loads(project.plan), cursor=project.cursor,
        revision=project.revision, created_at=project.created_at,
        updated_at=project.updated_at,
    )


def project_values(project: schemas.BomProjectOut) -> dict:
    """@brief 将备份项目转为可直接恢复的 ORM 字段。"""
    values = project.model_dump(exclude={"lines", "selections", "plan"})
    values.update(
        lines=json.dumps([line.model_dump() for line in project.lines],
                         ensure_ascii=False),
        selections=json.dumps(project.selections),
        plan=project.plan.model_dump_json(),
    )
    return values


def scaled_lines(
    lines: list[schemas.BomLineOut], copies: int,
) -> list[schemas.BomLineOut]:
    """@brief 只缩放需求，保存的原始单份数量保持不变。"""
    return [line.model_copy(update={"quantity": line.quantity * copies})
            for line in lines]
