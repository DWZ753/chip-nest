"""联网识别接口：输入料号/描述 → 返回候选元件与可直接填表的字段。

网络访问都在 services/lookup.py 里，失败一律降级为「查不到」，
这里只负责把结果整理成前端要的形状；online=False 表示网不通。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.db import get_session
from app.services.lookup import Candidate, LookupService, get_lookup_service

router = APIRouter(prefix="/api/v1/lookup", tags=["lookup"])


def _to_out(candidate: Candidate) -> dict:
    return {
        "lcsc": candidate.lcsc,
        "mpn": candidate.mpn,
        "name": candidate.name,
        "value": candidate.value,
        "package": candidate.package,
        "manufacturer": candidate.manufacturer,
        "category": candidate.category,
        "description": candidate.description,
        "stock": candidate.stock,
        "price": candidate.price,
        "datasheet": candidate.datasheet,
        "source": candidate.source,
        "params": candidate.params,
    }


@router.get("/search", response_model=list[schemas.LookupCandidateOut])
async def lookup_search(
    q: str = Query(min_length=1, max_length=64, description="关键词/型号/编号"),
    package: str | None = Query(default=None, max_length=24),
    limit: int = Query(default=10, ge=1, le=30),
    session: AsyncSession = Depends(get_session),
    service: LookupService = Depends(get_lookup_service),
) -> list[dict]:
    """关键词搜索：返回按匹配度排序的候选（可能为空，不代表出错）。"""
    found = await service.search(session, q, package=package, limit=limit)
    return [_to_out(c) for c in found]


@router.get("/detail", response_model=schemas.LookupCandidateOut)
async def lookup_detail(
    lcsc: str = Query(min_length=1, max_length=24, description="立创编号，如 C14663"),
    session: AsyncSession = Depends(get_session),
    service: LookupService = Depends(get_lookup_service),
) -> dict:
    """按立创编号取详情（参数最全）。"""
    candidate = await service.detail(session, lcsc)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"没查到 {lcsc}，检查编号或网络后重试")
    return _to_out(candidate)


@router.post("/autofill", response_model=schemas.LookupResultOut)
async def lookup_autofill(
    body: schemas.LookupRequest,
    session: AsyncSession = Depends(get_session),
    service: LookupService = Depends(get_lookup_service),
) -> dict:
    """自动识别：判断是编号还是关键词，返回最佳候选与填表字段。"""
    result = await service.autofill(session, body.text)
    return {
        "query": result.query,
        "kind": result.kind,
        "best": _to_out(result.best) if result.best else None,
        "candidates": [_to_out(c) for c in result.candidates],
        "fields": result.fields(),
        "online": service.failures == 0,
    }
