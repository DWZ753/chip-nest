"""审计流水接口：最近操作记录（设置页可查）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.db import get_session
from app.models import Transaction

router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])


@router.get("", response_model=list[schemas.TransactionOut])
async def list_transactions(
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[Transaction]:
    """审计流水（最近在前）。"""
    stmt = select(Transaction).order_by(Transaction.id.desc()).limit(limit)
    return list((await session.scalars(stmt)).all())
