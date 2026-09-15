"""格子互换：位置与灯号对调、审计留痕、异常输入。"""


async def _create(client, slot: int, **overrides) -> dict:
    payload = {
        "name": "贴片电阻", "value": "10k", "package": "0603",
        "quantity": 15, "threshold": 3, "zone": 1, "layer": 1, "slot": slot,
    }
    payload.update(overrides)
    resp = await client.post("/api/v1/components", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_swap_two_components(client):
    a = await _create(client, slot=0, name="电阻A")
    b = await _create(client, slot=2, name="电容B", value="100nF", quantity=7)
    assert (a["slot"], a["led_index"]) == (0, 0)
    assert (b["slot"], b["led_index"]) == (2, 1)

    resp = await client.post("/api/v1/components/swap",
                             json={"a_id": a["id"], "b_id": b["id"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["a"]["slot"] == 2 and body["b"]["slot"] == 0
    # 灯号跟着槽位走（灯带仍对应格子），库存不动
    assert body["a"]["led_index"] == 1 and body["b"]["led_index"] == 0
    assert body["a"]["quantity"] == 15 and body["b"]["quantity"] == 7

    rows = (await client.get("/api/v1/components")).json()
    assert [(r["name"], r["slot"]) for r in rows] == [("电容B", 0), ("电阻A", 2)]

    txs = (await client.get("/api/v1/transactions", params={"limit": 1})).json()
    assert "互换" in (txs[0]["detail"] or "")


async def test_swap_across_zones_and_layers(client):
    """跨区跨层也能换，且不违反槽位唯一约束。"""
    await client.put("/api/v1/layout", json={
        "zone_count": 2, "layer_count": 2, "row_count": 1, "col_count": 4,
        "zone_layers": [2, 2],
    })
    a = await _create(client, slot=1, name="A", zone=1, layer=2)
    b = await _create(client, slot=3, name="B", zone=2, layer=1)

    resp = await client.post("/api/v1/components/swap",
                             json={"a_id": a["id"], "b_id": b["id"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["a"]["zone"], body["a"]["layer"], body["a"]["slot"]) == (2, 1, 3)
    assert (body["b"]["zone"], body["b"]["layer"], body["b"]["slot"]) == (1, 2, 1)

    # 换回来还是好的（幂等来回）
    resp = await client.post("/api/v1/components/swap",
                             json={"a_id": a["id"], "b_id": b["id"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["a"]["slot"] == 1


async def test_swap_rejects_same_or_missing(client):
    a = await _create(client, slot=0)
    resp = await client.post("/api/v1/components/swap",
                             json={"a_id": a["id"], "b_id": a["id"]})
    assert resp.status_code == 400
    assert "相同" in resp.json()["detail"]

    resp = await client.post("/api/v1/components/swap",
                             json={"a_id": a["id"], "b_id": 9999})
    assert resp.status_code == 404
    # 数据没被动过
    rows = (await client.get("/api/v1/components")).json()
    assert [r["slot"] for r in rows] == [0]


async def test_swap_keeps_slots_unique_under_repeat(client):
    """反复互换不会把槽位搞乱，元件数量与槽位集合保持不变。"""
    a = await _create(client, slot=0, name="A")
    b = await _create(client, slot=1, name="B")
    c = await _create(client, slot=2, name="C")
    for _ in range(3):
        assert (await client.post("/api/v1/components/swap",
                                  json={"a_id": a["id"], "b_id": c["id"]})).status_code == 200
    rows = (await client.get("/api/v1/components")).json()
    assert sorted(r["slot"] for r in rows) == [0, 1, 2]
    assert len({r["slot"] for r in rows}) == 3
    assert [r["led_index"] for r in rows] == [0, 1, 2]
