"""每区独立层数：布局读写、位置校验、游离判定与清空数据。"""

from app.db import async_session
from app.models import LayoutConfig
from sqlalchemy import select


async def _put_layout(client, **overrides) -> dict:
    payload = {
        "zone_count": 2, "layer_count": 3, "row_count": 1, "col_count": 4,
        "zone_names": ["主料区", "杂料区"], "zone_sizes": [[1, 4], [1, 4]],
        "zone_layers": [1, 3],
    }
    payload.update(overrides)
    resp = await client.put("/api/v1/layout", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_layout_roundtrip_zone_layers(client):
    """每区层数读回来要跟写进去的一致。"""
    body = await _put_layout(client)
    assert body["zone_layers"] == [1, 3]
    assert body["layer_count"] == 3  # 默认值仍保留，供新建区使用

    again = (await client.get("/api/v1/layout")).json()
    assert again["zone_layers"] == [1, 3]


async def test_zone_layers_default_when_missing(client):
    """没传 zone_layers：各区按默认层数补齐，长度与区数对齐。"""
    body = await _put_layout(client, zone_layers=[], layer_count=2)
    assert body["zone_layers"] == [2, 2]

    partial = await _put_layout(client, zone_layers=[4], layer_count=2)
    assert partial["zone_layers"] == [4, 2]


async def test_zone_layers_out_of_range_rejected(client):
    """层数越界（0 / 21）应被 schema 拒绝。"""
    resp = await client.put("/api/v1/layout", json={
        "zone_count": 1, "layer_count": 3, "row_count": 1, "col_count": 4,
        "zone_layers": [0],
    })
    assert resp.status_code == 422
    resp = await client.put("/api/v1/layout", json={
        "zone_count": 1, "layer_count": 3, "row_count": 1, "col_count": 4,
        "zone_layers": [21],
    })
    assert resp.status_code == 422


async def test_component_position_follows_zone_layers(client):
    """第 2 区只有 3 层：放到 3 层可以，放到 4 层要被拒（第 1 区只 1 层同理）。"""
    await _put_layout(client)

    ok = await client.post("/api/v1/components", json={
        "name": "贴片电阻", "zone": 2, "layer": 3, "slot": 0,
    })
    assert ok.status_code == 201, ok.text

    too_deep = await client.post("/api/v1/components", json={
        "name": "越界", "zone": 2, "layer": 4, "slot": 0,
    })
    assert too_deep.status_code == 400
    assert "第 2 区只有 3 层" in too_deep.json()["detail"]

    zone1_deep = await client.post("/api/v1/components", json={
        "name": "越界", "zone": 1, "layer": 2, "slot": 0,
    })
    assert zone1_deep.status_code == 400
    assert "第 1 区只有 1 层" in zone1_deep.json()["detail"]

    # 搬家同样按目标区层数校验
    moved = await client.post("/api/v1/components", json={
        "name": "电解电容", "zone": 1, "layer": 1, "slot": 1,
    })
    bad_move = await client.patch(f"/api/v1/components/{moved.json()['id']}",
                                  json={"zone": 1, "layer": 2, "slot": 0})
    assert bad_move.status_code == 400

    # 缩到 1 层后，3 层那个元件变成游离（前端据此提示搬家）
    await _put_layout(client, zone_layers=[1, 1])
    rows = (await client.get("/api/v1/components")).json()
    assert [r["layer"] for r in rows] == [1, 3]  # 数据还在，只是超出网格


async def test_reset_clears_zone_layers(client):
    """一键清空要把每区层数也恢复成初始（空数组=用默认层数）。"""
    await _put_layout(client)
    resp = await client.post("/api/v1/system/reset", json={"confirm": "清空"})
    assert resp.status_code == 200, resp.text

    layout = (await client.get("/api/v1/layout")).json()
    assert layout["zone_layers"] == [3]
    assert layout["zone_count"] == 1

    async with async_session() as session:
        row = await session.scalar(select(LayoutConfig).where(LayoutConfig.id == 1))
        assert row is not None and row.zone_layers == "[]"
