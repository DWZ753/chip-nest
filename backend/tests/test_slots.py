"""多格存放：占用格增删、占用判定、合并重复元件。"""

import asyncio

import pytest


async def _create(client, slot: int, **overrides) -> dict:
    payload = {
        "name": "贴片电阻", "value": "10k", "package": "0603",
        "quantity": 100, "threshold": 20, "zone": 1, "layer": 1, "slot": slot,
    }
    payload.update(overrides)
    resp = await client.post("/api/v1/components", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_add_and_remove_slot(client):
    comp = await _create(client, slot=0)
    assert comp["slots"] == [] and comp["slot_count"] == 1

    resp = await client.post(f"/api/v1/components/{comp['id']}/slots",
                             json={"zone": 1, "layer": 1, "slot": 3})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["slot_count"] == 2
    assert [(s["zone"], s["layer"], s["slot"]) for s in body["slots"]] == [(1, 1, 3)]
    # 库存还是一个数
    assert body["quantity"] == 100

    # 重复添加同一个格子：幂等，不报错
    again = await client.post(f"/api/v1/components/{comp['id']}/slots",
                              json={"zone": 1, "layer": 1, "slot": 3})
    assert again.status_code == 200 and again.json()["slot_count"] == 2

    # 列表里也带出来
    rows = (await client.get("/api/v1/components")).json()
    assert rows[0]["slot_count"] == 2

    resp = await client.request("DELETE", f"/api/v1/components/{comp['id']}/slots",
                                params={"zone": 1, "layer": 1, "slot": 3})
    assert resp.status_code == 200, resp.text
    assert resp.json()["slot_count"] == 1 and resp.json()["slots"] == []

    # 再删一次：不存在 -> 409
    resp = await client.request("DELETE", f"/api/v1/components/{comp['id']}/slots",
                                params={"zone": 1, "layer": 1, "slot": 3})
    assert resp.status_code == 409

    txs = (await client.get("/api/v1/transactions")).json()
    assert any("占用格" in (t["detail"] or "") for t in txs)


async def test_slot_is_really_occupied(client):
    """占用格不能被别的元件建档/搬家/互换占用，也不能重复占给自己主格。"""
    a = await _create(client, slot=0, name="A")
    assert (await client.post(f"/api/v1/components/{a['id']}/slots",
                              json={"zone": 1, "layer": 1, "slot": 2})).status_code == 200

    busy = await client.post("/api/v1/components", json={
        "name": "B", "zone": 1, "layer": 1, "slot": 2,
    })
    assert busy.status_code == 409
    assert "占用格" in busy.json()["detail"]

    b = await _create(client, slot=1, name="B")
    moved = await client.patch(f"/api/v1/components/{b['id']}",
                               json={"zone": 1, "layer": 1, "slot": 2})
    assert moved.status_code == 409

    # 占自己的主格 -> 拒绝
    own = await client.post(f"/api/v1/components/{a['id']}/slots",
                            json={"zone": 1, "layer": 1, "slot": 0})
    assert own.status_code == 409


async def test_slot_out_of_layout_rejected(client):
    comp = await _create(client, slot=0)
    resp = await client.post(f"/api/v1/components/{comp['id']}/slots",
                             json={"zone": 1, "layer": 9, "slot": 0})
    assert resp.status_code == 400
    assert "只有" in resp.json()["detail"]


async def test_delete_component_removes_slots(client):
    comp = await _create(client, slot=0)
    await client.post(f"/api/v1/components/{comp['id']}/slots",
                      json={"zone": 1, "layer": 1, "slot": 2})
    assert (await client.delete(f"/api/v1/components/{comp['id']}")).status_code == 204
    # 格子释放了：新元件可以占用它
    again = await client.post("/api/v1/components", json={
        "name": "新料", "zone": 1, "layer": 1, "slot": 2,
    })
    assert again.status_code == 201


async def test_merge_duplicates_dry_run_and_apply(client):
    a = await _create(client, slot=0, name="10k电阻", quantity=100)
    b = await _create(client, slot=1, name="10k电阻", quantity=200, tags=["常用"])
    await _create(client, slot=2, name="别的料", value="1k", quantity=5)

    preview = (await client.post("/api/v1/system/merge-duplicates",
                                 params={"dry_run": "true"})).json()
    assert preview["dry_run"] is True
    assert preview["merged_groups"] == 0  # 预览不落库
    assert len(preview["groups"]) == 1
    group = preview["groups"][0]
    assert group["keep_id"] == a["id"]
    assert group["member_ids"] == [a["id"], b["id"]]
    assert group["total_quantity"] == 300
    assert len((await client.get("/api/v1/components")).json()) == 3

    applied = (await client.post("/api/v1/system/merge-duplicates")).json()
    assert applied["dry_run"] is False
    assert applied["merged_groups"] == 1 and applied["merged_components"] == 1

    rows = (await client.get("/api/v1/components")).json()
    assert len(rows) == 2
    kept = next(r for r in rows if r["name"] == "10k电阻")
    assert kept["quantity"] == 300
    assert kept["slot_count"] == 2               # 主格 + 被合并那条的格子
    assert kept["tags"] == ["常用"]              # 标签取并集
    assert [s["slot"] for s in kept["slots"]] == [1]

    # 再跑一次：没有可合并的了
    again = (await client.post("/api/v1/system/merge-duplicates")).json()
    assert again["groups"] == [] and again["merged_groups"] == 0

    txs = (await client.get("/api/v1/transactions")).json()
    assert any("合并重复元件" in (t["detail"] or "") for t in txs)


async def test_merge_with_extra_slots_and_undo(client):
    """带附加格的重复元件合并时转移格子，撤销后完整还原。"""
    first = await _create(client, 0, tags=["主料"])
    second = await _create(client, 1, quantity=20, tags=["备用料"])
    response = await client.post(
        f"/api/v1/components/{second['id']}/slots",
        json={"zone": 1, "layer": 1, "slot": 3},
    )
    assert response.status_code == 200, response.text
    response = await client.post("/api/v1/system/merge-duplicates")
    assert response.status_code == 200, response.text
    rows = (await client.get("/api/v1/components")).json()
    assert len(rows) == 1 and rows[0]["quantity"] == 120
    assert rows[0]["id"] == first["id"]
    assert sorted(item["slot"] for item in rows[0]["slots"]) == [1, 3]
    search = await client.get("/api/v1/components", params={"q": "备用料"})
    assert len(search.json()) == 1

    response = await client.post("/api/v1/system/undo")
    assert response.status_code == 200 and response.json()["ok"]
    rows = (await client.get("/api/v1/components")).json()
    assert [(row["slot"], row["quantity"]) for row in rows] == [(0, 100), (1, 20)]
    assert rows[0]["slots"] == []
    assert [item["slot"] for item in rows[1]["slots"]] == [3]


async def test_manual_merge_keeps_selected_main_and_restores_slots(client):
    """保留后创建的主格，汇总库存、转移附加格并撤销。"""
    other = await _create(client, 0, quantity=20, tags=["备用料"])
    keep = await _create(client, 1, quantity=100, tags=["主料"], threshold=30)
    await client.post(f"/api/v1/components/{other['id']}/slots",
                      json={"zone": 1, "layer": 1, "slot": 2})
    await client.post(f"/api/v1/components/{keep['id']}/slots",
                      json={"zone": 1, "layer": 1, "slot": 3})
    response = await client.post(
        f"/api/v1/components/{keep['id']}/merge",
        json={"other_id": other["id"]},
    )
    assert response.status_code == 200, response.text
    merged = response.json()
    assert merged["id"] == keep["id"] and merged["slot"] == 1
    assert merged["quantity"] == 120 and merged["threshold"] == 30
    assert sorted(item["slot"] for item in merged["slots"]) == [0, 2, 3]
    assert merged["tags"] == ["主料", "备用料"]
    assert len((await client.get("/api/v1/components")).json()) == 1
    assert len((await client.get("/api/v1/components",
                               params={"q": "备用料"})).json()) == 1
    transactions = (await client.get("/api/v1/transactions")).json()
    assert transactions[0]["kind"] == "adjust"
    assert "数量合计 120" in transactions[0]["detail"]
    response = await client.post("/api/v1/system/undo")
    assert response.status_code == 200 and response.json()["ok"]
    rows = (await client.get("/api/v1/components")).json()
    assert [(row["slot"], row["quantity"]) for row in rows] == [(0, 20), (1, 100)]
    assert [slot["slot"] for slot in rows[0]["slots"]] == [2]
    assert [slot["slot"] for slot in rows[1]["slots"]] == [3]
    assert rows[0]["tags"] == ["备用料"]


@pytest.mark.parametrize("different", [
    {"name": "电容"}, {"value": "1k"}, {"package": "0805"},
    {"manufacturer_part": "OTHER"}, {"supplier_part": "C1234"},
])
async def test_manual_merge_rejects_different_attributes(client, different):
    keep = await _create(client, 0)
    other = await _create(client, 1, **different)
    before = (await client.get("/api/v1/components")).json()
    transactions = (await client.get("/api/v1/transactions")).json()
    response = await client.post(f"/api/v1/components/{keep['id']}/merge",
                                 json={"other_id": other["id"]})
    assert response.status_code == 409, response.text
    assert "元件属性不一致" in response.json()["detail"]
    assert (await client.get("/api/v1/components")).json() == before
    assert (await client.get("/api/v1/transactions")).json() == transactions


async def test_manual_merge_rejects_self_missing_and_tag_overflow(client):
    keep = await _create(client, 0, tags=[f"主料{i}" for i in range(8)])
    other = await _create(client, 1, tags=["备用料"])
    path = f"/api/v1/components/{keep['id']}/merge"
    assert (await client.post(path, json={"other_id": keep["id"]})).status_code \
        == 400
    assert (await client.post(path, json={"other_id": 9999})).status_code == 404
    assert (await client.post(path, json={"other_id": 0})).status_code == 422
    response = await client.post(path, json={"other_id": other["id"]})
    assert response.status_code == 409
    assert response.json()["detail"] == "合并后标签超过 8 个"
    assert len((await client.get("/api/v1/components")).json()) == 2


async def test_manual_merge_concurrent_requests_only_apply_once(client):
    keep = await _create(client, 0)
    other = await _create(client, 1, quantity=20)
    path = f"/api/v1/components/{keep['id']}/merge"
    responses = await asyncio.gather(
        client.post(path, json={"other_id": other["id"]}),
        client.post(path, json={"other_id": other["id"]}),
    )
    assert sorted(response.status_code for response in responses) == [200, 404]
    rows = (await client.get("/api/v1/components")).json()
    assert len(rows) == 1 and rows[0]["quantity"] == 120
    assert rows[0]["slot_count"] == 2
