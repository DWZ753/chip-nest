"""一键清空数据：确认词校验、自动备份、元件/流水清空、布局恢复。"""

import json
from pathlib import Path

from app import config
from app.db import async_session
from app.models import LayoutConfig, Transaction
from sqlalchemy import func, select


async def _create(client, slot: int, **overrides) -> dict:
    payload = {
        "name": "贴片电阻", "value": "10k", "package": "0603",
        "quantity": 15, "threshold": 3, "zone": 1, "layer": 1, "slot": slot,
        "tags": ["常用"], "display_tags": ["常用"],
    }
    payload.update(overrides)
    resp = await client.post("/api/v1/components", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _count_transactions() -> int:
    async with async_session() as session:
        return await session.scalar(select(func.count()).select_from(Transaction))


async def _set_layout(client, **overrides) -> dict:
    payload = {
        "zone_count": 2, "layer_count": 4, "row_count": 2, "col_count": 3,
        "zone_names": ["主料区", "杂料区"], "zone_sizes": [[2, 3], [1, 4]],
    }
    payload.update(overrides)
    resp = await client.put("/api/v1/layout", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_reset_rejects_wrong_confirm_word(client):
    """确认词不对 -> 400 且数据原样保留。"""
    await _create(client, slot=0)

    resp = await client.post("/api/v1/system/reset", json={"confirm": "清"})
    assert resp.status_code == 400
    assert "清空" in resp.json()["detail"]

    rows = (await client.get("/api/v1/components")).json()
    assert len(rows) == 1
    assert list(config.backup_dir().glob("*.json")) == []


async def test_reset_wipes_components_and_transactions(client):
    """确认词正确 -> 元件与流水清空，布局恢复初始值，且留下 JSON 备份。"""
    await _create(client, slot=0)
    await _create(client, slot=1, name="电解电容", value="100uF", package="0805")
    comp = (await client.get("/api/v1/components")).json()[0]
    resp = await client.post(f"/api/v1/components/{comp['id']}/stock",
                             json={"delta": -2, "note": "取走两只"})
    assert resp.status_code == 200
    await _set_layout(client)
    assert await _count_transactions() > 0

    resp = await client.post("/api/v1/system/reset",
                             json={"confirm": " 清空 ", "reset_layout": True})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted_components"] == 2
    assert body["deleted_transactions"] > 0
    assert body["layout_reset"] is True

    # 元件与流水都空了
    assert (await client.get("/api/v1/components")).json() == []
    assert (await client.get("/api/v1/transactions")).json() == []
    assert await _count_transactions() == 0

    # 布局回到 1 区 x 3 层 x 1 行 4 列，区名/每区尺寸一并清掉
    layout = (await client.get("/api/v1/layout")).json()
    assert (layout["zone_count"], layout["layer_count"]) == (1, 3)
    assert (layout["row_count"], layout["col_count"]) == (1, 4)
    assert layout["zone_names"] == []
    # 与全新初始化的返回一致：库里存空数组，接口按默认尺寸补齐成 [[1, 4]]
    assert layout["zone_sizes"] == [[1, 4]]

    # 库里确实落的是空值（而非「恰好等于默认」的旧数据）
    async with async_session() as session:
        row = await session.scalar(select(LayoutConfig).where(LayoutConfig.id == 1))
        assert row is not None
        assert row.zone_names == "[]" and row.zone_sizes == "[]"

    # 备份文件真实存在且内容完整（可据此手工找回）
    backup = Path(body["backup_path"])
    assert backup.is_file()
    assert backup.parent == config.backup_dir()
    data = json.loads(backup.read_text(encoding="utf-8"))
    assert data["reason"] == "reset"
    assert len(data["components"]) == 2
    assert data["components"][0]["tags"] == ["常用"]
    assert len(data["transactions"]) == body["deleted_transactions"]
    assert data["layout"]["zone_names"] == ["主料区", "杂料区"]

    # 清空后仍然可以继续建档（库结构完好，槽位不冲突）
    fresh = await _create(client, slot=0)
    assert fresh["led_index"] == 0


async def test_reset_keeps_layout_when_asked(client):
    """reset_layout=False：只清内容，分区/区名/尺寸保持不动。"""
    await _create(client, slot=0)
    await _set_layout(client)

    resp = await client.post("/api/v1/system/reset",
                             json={"confirm": "清空", "reset_layout": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["layout_reset"] is False

    layout = (await client.get("/api/v1/layout")).json()
    assert layout["zone_count"] == 2 and layout["layer_count"] == 4
    assert layout["zone_names"] == ["主料区", "杂料区"]
    assert layout["zone_sizes"] == [[2, 3], [1, 4]]
    assert (await client.get("/api/v1/components")).json() == []


async def test_reset_on_empty_db_is_idempotent(client):
    """空库再清一次也不报错，计数为 0，备份照留。"""
    resp = await client.post("/api/v1/system/reset", json={"confirm": "清空"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted_components"] == 0
    assert body["deleted_transactions"] == 0

    async with async_session() as session:
        row = await session.scalar(select(LayoutConfig).where(LayoutConfig.id == 1))
        assert row is not None and row.zone_count == 1
