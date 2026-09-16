"""不可用格标记 与 撤销上一步。"""


async def _create(client, slot: int, **overrides) -> dict:
    payload = {
        "name": "贴片电阻", "value": "10k", "package": "0603",
        "quantity": 100, "threshold": 20, "zone": 1, "layer": 1, "slot": slot,
    }
    payload.update(overrides)
    resp = await client.post("/api/v1/components", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------- 不可用格 ----------

async def test_block_and_unblock_slot(client):
    comp = await _create(client, slot=0)

    resp = await client.post("/api/v1/layout/blocked", json={"zone": 1, "layer": 1, "slot": 2})
    assert resp.status_code == 200, resp.text
    assert [(b["zone"], b["layer"], b["slot"]) for b in resp.json()] == [(1, 1, 2)]
    layout = (await client.get("/api/v1/layout")).json()
    assert [(b["zone"], b["layer"], b["slot"]) for b in layout["blocked"]] == [(1, 1, 2)]

    # 标记过的格子不能放元件
    bad = await client.post("/api/v1/components", json={
        "name": "新料", "zone": 1, "layer": 1, "slot": 2,
    })
    assert bad.status_code == 409 and "不可用" in bad.json()["detail"]

    # 也不能搬过去、不能当占用格
    moved = await client.patch(f"/api/v1/components/{comp['id']}",
                               json={"zone": 1, "layer": 1, "slot": 2})
    assert moved.status_code == 409
    slot = await client.post(f"/api/v1/components/{comp['id']}/slots",
                             json={"zone": 1, "layer": 1, "slot": 2})
    assert slot.status_code == 409

    # 已占用的格子不能标记
    busy = await client.post("/api/v1/layout/blocked", json={"zone": 1, "layer": 1, "slot": 0})
    assert busy.status_code == 409

    # 解除后可以正常使用
    resp = await client.request("DELETE", "/api/v1/layout/blocked",
                                params={"zone": 1, "layer": 1, "slot": 2})
    assert resp.status_code == 200 and resp.json() == []
    ok = await client.post("/api/v1/components", json={
        "name": "新料", "zone": 1, "layer": 1, "slot": 2,
    })
    assert ok.status_code == 201

    # 再解除一次：没标记过 -> 404
    again = await client.request("DELETE", "/api/v1/layout/blocked",
                                 params={"zone": 1, "layer": 1, "slot": 2})
    assert again.status_code == 404

    txs = (await client.get("/api/v1/transactions")).json()
    assert any("不可用" in (t["detail"] or "") for t in txs)


async def test_block_out_of_layout_and_reset(client):
    resp = await client.post("/api/v1/layout/blocked", json={"zone": 1, "layer": 9, "slot": 0})
    assert resp.status_code == 409

    await client.post("/api/v1/layout/blocked", json={"zone": 1, "layer": 1, "slot": 1})
    await _create(client, slot=0)
    assert (await client.post("/api/v1/system/reset", json={"confirm": "清空"})).status_code == 200
    layout = (await client.get("/api/v1/layout")).json()
    assert layout["blocked"] == []


# ---------- 撤销 ----------

async def _undo(client) -> dict:
    resp = await client.post("/api/v1/system/undo")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_undo_create_and_delete(client):
    comp = await _create(client, slot=0, name="电阻A")
    assert len((await client.get("/api/v1/components")).json()) == 1

    out = await _undo(client)                       # 撤销建档
    assert out["ok"] is True and "建档" in out["label"]
    assert (await client.get("/api/v1/components")).json() == []

    comp = await _create(client, slot=0, name="电阻A", quantity=42)
    assert (await client.delete(f"/api/v1/components/{comp['id']}")).status_code == 204
    out = await _undo(client)                       # 撤销删除
    assert out["ok"] is True and "删除" in out["label"]
    rows = (await client.get("/api/v1/components")).json()
    assert len(rows) == 1
    assert rows[0]["name"] == "电阻A" and rows[0]["quantity"] == 42
    assert (rows[0]["zone"], rows[0]["layer"], rows[0]["slot"]) == (1, 1, 0)


async def test_undo_move_and_swap(client):
    a = await _create(client, slot=0, name="A")
    b = await _create(client, slot=1, name="B")

    await client.patch(f"/api/v1/components/{a['id']}",
                       json={"zone": 1, "layer": 1, "slot": 3})
    assert [r["slot"] for r in (await client.get("/api/v1/components")).json()] == [1, 3]
    out = await _undo(client)
    assert out["ok"] is True and "搬到" in out["label"]
    assert [r["slot"] for r in (await client.get("/api/v1/components")).json()] == [0, 1]

    await client.post("/api/v1/components/swap", json={"a_id": a["id"], "b_id": b["id"]})
    rows = (await client.get("/api/v1/components")).json()
    assert [(r["name"], r["slot"]) for r in rows] == [("B", 0), ("A", 1)]
    out = await _undo(client)
    assert out["ok"] is True and "互换" in out["label"]
    rows = (await client.get("/api/v1/components")).json()
    assert [(r["name"], r["slot"], r["led_index"]) for r in rows] == [("A", 0, 0), ("B", 1, 1)]


async def test_undo_stock_and_slot(client):
    comp = await _create(client, slot=0, name="电容C", quantity=10)

    await client.post(f"/api/v1/components/{comp['id']}/stock", json={"delta": -4})
    assert (await client.get(f"/api/v1/components/{comp['id']}")).json()["quantity"] == 6
    out = await _undo(client)
    assert out["ok"] is True and "出库" in out["label"]
    assert (await client.get(f"/api/v1/components/{comp['id']}")).json()["quantity"] == 10

    await client.post(f"/api/v1/components/{comp['id']}/slots",
                      json={"zone": 1, "layer": 1, "slot": 2})
    assert (await client.get(f"/api/v1/components/{comp['id']}")).json()["slot_count"] == 2
    out = await _undo(client)
    assert out["ok"] is True and "合并格" in out["label"]
    assert (await client.get(f"/api/v1/components/{comp['id']}")).json()["slot_count"] == 1


async def test_undo_field_edit_and_empty_stack(client):
    comp = await _create(client, slot=0, name="原名", value="10k")
    await client.patch(f"/api/v1/components/{comp['id']}",
                       json={"name": "改过的名字", "value": "22k"})
    assert (await client.get(f"/api/v1/components/{comp['id']}")).json()["name"] == "改过的名字"

    peek = (await client.get("/api/v1/system/undo")).json()
    assert "修改" in peek["label"]

    out = await _undo(client)
    assert out["ok"] is True
    row = (await client.get(f"/api/v1/components/{comp['id']}")).json()
    assert row["name"] == "原名" and row["value"] == "10k"

    # 清空后栈是空的
    await client.post("/api/v1/system/reset", json={"confirm": "清空"})
    out = await _undo(client)
    assert out["ok"] is False and "没有可撤销" in out["message"]
    assert (await client.get("/api/v1/system/undo")).json()["label"] == ""


async def test_undo_falls_back_when_original_slot_taken(client):
    """撤销删除时原位已不能用了：落到别的空格并说明。"""
    a = await _create(client, slot=0, name="A", quantity=7)
    assert (await client.delete(f"/api/v1/components/{a['id']}")).status_code == 204
    # 原位被标记不可用（不可用标记不进撤销栈，所以下一条要撤销的仍是"删除"）
    assert (await client.post("/api/v1/layout/blocked",
                              json={"zone": 1, "layer": 1, "slot": 0})).status_code == 200

    out = await _undo(client)
    assert out["ok"] is True and "删除" in out["label"]
    assert "已被占用" in out["message"]
    rows = (await client.get("/api/v1/components")).json()
    assert len(rows) == 1
    assert rows[0]["name"] == "A" and rows[0]["quantity"] == 7
    assert rows[0]["slot"] != 0                     # 原位不可用，换了个空格
