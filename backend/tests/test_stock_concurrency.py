"""并发扣减测试：两个任务各扣 10、库存只有 15，必须恰好一个成功。"""

import asyncio

from sqlalchemy import func, select

from app.db import async_session
from app.models import Component, Transaction
from app.services import stock as stock_service


async def _try_decrement(component_id: int, need: int):
    async with async_session() as session:
        component = await session.get(Component, component_id)
        try:
            await stock_service.change_stock(session, component, -need)
            return "ok"
        except stock_service.StockShortage as exc:
            return exc.available


async def test_two_concurrent_decrements_never_negative():
    async with async_session() as session:
        component = await stock_service.create_component(
            session, name="并发电阻", zone=1, layer=1, slot=0, quantity=15,
        )
        component_id = component.id

    results = await asyncio.gather(
        _try_decrement(component_id, 10), _try_decrement(component_id, 10)
    )

    assert sorted(results, key=str) == [5, "ok"]  # 一个成功，另一个报出真实余量

    async with async_session() as session:
        final_qty = await session.scalar(
            select(Component.quantity).where(Component.id == component_id)
        )
        out_rows = await session.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.kind == "out")
        )
        assert final_qty == 5  # 绝不会被扣成负数
        assert out_rows == 1  # 只有成功的那次落审计


async def test_exact_boundary_allowed():
    """刚好扣到 0 是允许的（只禁止负数）。"""
    async with async_session() as session:
        component = await stock_service.create_component(
            session, name="边界电阻", zone=1, layer=1, slot=0, quantity=3,
        )
        await stock_service.change_stock(session, component, -3)
        final_qty = await session.scalar(
            select(Component.quantity).where(Component.id == component.id)
        )
        assert final_qty == 0
