"""元件 CRUD + 槽位唯一性 + 库存事务 + 审计的端到端 API 测试。"""

from app.db import async_session
from app.models import Transaction
from sqlalchemy import func, select


async def _count_transactions() -> int:
    async with async_session() as session:
        return await session.scalar(select(func.count()).select_from(Transaction))


async def _create(client, slot: int = 0, **overrides) -> dict:
    payload = {
        "name": "贴片电阻", "value": "10k", "package": "0603",
        "quantity": 15, "threshold": 3, "zone": 1, "layer": 1, "slot": slot,
    }
    payload.update(overrides)
    resp = await client.post("/api/v1/components", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_full_crud_flow_with_audit(client):
    # 建档：自动分配 led_index 0
    comp = await _create(client, slot=0)
    assert comp["led_index"] == 0 and comp["quantity"] == 15

    # 同槽位重复建档 -> 409 且提示占用者
    resp = await client.post("/api/v1/components", json={
        "name": "另一个", "zone": 1, "layer": 1, "slot": 0,
    })
    assert resp.status_code == 409
    assert "贴片电阻" in resp.json()["detail"]

    # 第二个元件 led 自动 +1
    comp2 = await _create(client, slot=1, name="电解电容", value="100uF")
    assert comp2["led_index"] == 1

    # 列表按位置排序
    rows = (await client.get("/api/v1/components")).json()
    assert [r["name"] for r in rows] == ["贴片电阻", "电解电容"]

    # 修改属性
    resp = await client.patch(f"/api/v1/components/{comp['id']}", json={"name": "贴片电阻 1%"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "贴片电阻 1%"

    # 直接改 quantity 被 422 拒绝（必须走 /stock）
    resp = await client.patch(f"/api/v1/components/{comp['id']}", json={"quantity": 999})
    assert resp.status_code == 422

    # 位置三字段不成组 -> 422
    resp = await client.patch(f"/api/v1/components/{comp['id']}", json={"zone": 1})
    assert resp.status_code == 422

    # 搬到被占的格子 -> 409
    resp = await client.patch(
        f"/api/v1/components/{comp['id']}",
        json={"zone": 1, "layer": 1, "slot": 1},
    )
    assert resp.status_code == 409

    # 入库 +5 / 出库 -12
    resp = await client.post(
        f"/api/v1/components/{comp['id']}/stock", json={"delta": 5, "note": "补货"}
    )
    assert resp.status_code == 200 and resp.json()["quantity"] == 20
    resp = await client.post(
        f"/api/v1/components/{comp['id']}/stock", json={"delta": -12}
    )
    assert resp.status_code == 200 and resp.json()["quantity"] == 8

    # 出库超库存 -> 409 + available
    resp = await client.post(
        f"/api/v1/components/{comp['id']}/stock", json={"delta": -10}
    )
    assert resp.status_code == 409
    body = resp.json()["detail"]
    assert body["available"] == 8

    # 审计：两个建档 + 改属性 + 入库 + 出库 = 5 条；失败的操作不出流水
    assert await _count_transactions() == 5
    tx = (await client.get("/api/v1/transactions")).json()
    assert [t["kind"] for t in tx] == ["out", "in", "adjust", "create", "create"]

    # 删除后列表为空，审计追加删除快照
    resp = await client.delete(f"/api/v1/components/{comp['id']}")
    assert resp.status_code == 204
    assert await _count_transactions() == 6
    assert (await client.get(f"/api/v1/components/{comp['id']}")).status_code == 404
    rows = (await client.get("/api/v1/components")).json()
    assert [r["name"] for r in rows] == ["电解电容"]




async def test_tags_roundtrip_and_search(client):
    """自定义标签：建档携带 → 读取还原 → 修改清空 → 按标签检索。"""
    comp = await _create(client, slot=0, name="主控芯片", value=None,
                         package="QFP-100", tags=["主控", "stm32"])
    assert sorted(comp["tags"]) == ["stm32", "主控"]

    row = (await client.get(f"/api/v1/components/{comp['id']}")).json()
    assert row["tags"] == ["主控", "stm32"]

    # 标签进检索文本
    names = [x["name"] for x in (await client.get(
        "/api/v1/components", params={"q": "主控"})).json()]
    assert "主控芯片" in names

    # 修改：换标签 + 空串/空白清理 + 超长截断 + 去重
    resp = await client.patch(f"/api/v1/components/{comp['id']}", json={
        "tags": [" 主控 ", "主控", "x" * 30, "", "   "],
    })
    assert resp.status_code == 200
    assert resp.json()["tags"] == ["主控", "x" * 20]

    # 清空标签
    resp = await client.patch(f"/api/v1/components/{comp['id']}", json={"tags": []})
    assert resp.status_code == 200 and resp.json()["tags"] == []
async def test_position_out_of_layout_rejected(client):
    resp = await client.post("/api/v1/components", json={
        "name": "越界件", "zone": 2, "layer": 1, "slot": 0,  # 布局只有 1 区
    })
    assert resp.status_code == 400
    resp = await client.post("/api/v1/components", json={
        "name": "越界格", "zone": 1, "layer": 1, "slot": 99,  # 每层只有 4 格
    })
    assert resp.status_code == 400
    assert await _count_transactions() == 0  # 失败不留痕

async def test_display_tags_roundtrip(client):
    """外部显示标签：建档携带 → 读取 → 改选/清空。"""
    comp = await _create(client, slot=0, name="主控芯片", value=None,
                         package="QFP-100", tags=["主控", "常用"],
                         display_tags=["主控"])
    assert comp["display_tags"] == ["主控"]
    row = (await client.get(f"/api/v1/components/{comp['id']}")).json()
    assert row["tags"] == ["主控", "常用"] and row["display_tags"] == ["主控"]

    resp = await client.patch(f"/api/v1/components/{comp['id']}",
                              json={"display_tags": ["常用"]})
    assert resp.status_code == 200
    assert resp.json()["display_tags"] == ["常用"]

    resp = await client.patch(f"/api/v1/components/{comp['id']}", json={"display_tags": []})
    assert resp.status_code == 200 and resp.json()["display_tags"] == []
