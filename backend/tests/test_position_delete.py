"""逐格删除：保留同组库存、主格接替、撤销与并发保护。"""

import asyncio

import pytest


async def _group(client):
    """创建主格 0、附加格 1 和 3 的元件。"""
    response = await client.post("/api/v1/components", json={
        "name": "贴片电阻", "value": "10k", "package": "0603",
        "quantity": 100, "zone": 1, "layer": 1, "slot": 0,
        "tags": ["常用"], "threshold": 20,
    })
    assert response.status_code == 201, response.text
    component_id = response.json()["id"]
    for slot in (1, 3):
        response = await client.post(f"/api/v1/components/{component_id}/slots",
                                     json={"zone": 1, "layer": 1, "slot": slot})
        assert response.status_code == 200, response.text
    return response.json()


async def _delete(client, component_id, slot):
    return await client.delete(f"/api/v1/components/{component_id}/position",
                               params={"zone": 1, "layer": 1, "slot": slot})


async def test_delete_shared_position_preserves_group_and_undo(client):
    before = await _group(client)
    response = await _delete(client, before["id"], 1)
    assert response.status_code == 200, response.text
    kept = response.json()
    assert kept["quantity"] == 100 and kept["slot"] == 0
    assert [slot["slot"] for slot in kept["slots"]] == [3]
    assert (await client.post("/api/v1/system/undo")).json()["ok"]
    restored = (await client.get(f'/api/v1/components/{before["id"]}')).json()
    assert restored == before


async def test_delete_main_promotes_remaining_position_and_undo(client):
    before = await _group(client)
    response = await _delete(client, before["id"], 0)
    assert response.status_code == 200, response.text
    kept = response.json()
    assert kept["id"] == before["id"] and kept["quantity"] == 100
    assert kept["slot"] == 1 and kept["slot_count"] == 2
    assert [slot["slot"] for slot in kept["slots"]] == [3]
    assert kept["tags"] == before["tags"]
    assert kept["threshold"] == before["threshold"]
    transactions = (await client.get("/api/v1/transactions")).json()
    assert transactions[0]["delta"] == 0
    assert "主格改为 1区/1层/1格" in transactions[0]["detail"]
    assert (await client.post("/api/v1/system/undo")).json()["ok"]
    restored = (await client.get(f'/api/v1/components/{before["id"]}')).json()
    assert restored == before


@pytest.mark.parametrize("order", [(0, 1, 3), (3, 1, 0), (1, 0, 3)])
async def test_selected_positions_only_and_last_deletion(client, order):
    before = await _group(client)
    first = await _delete(client, before["id"], order[0])
    second = await _delete(client, before["id"], order[1])
    assert first.status_code == second.status_code == 200
    assert second.json()["quantity"] == 100
    assert second.json()["slot_count"] == 1
    assert second.json()["slot"] == order[2]
    last = await _delete(client, before["id"], order[2])
    assert last.status_code == 200 and last.json() is None
    assert (await client.get("/api/v1/components")).json() == []
    for _ in order:
        assert (await client.post("/api/v1/system/undo")).json()["ok"]
    restored = (await client.get("/api/v1/components")).json()
    assert len(restored) == 1 and restored[0]["quantity"] == 100
    assert restored[0]["slot_count"] == 3


async def test_delete_position_cannot_affect_other_component(client):
    component = await _group(client)
    await client.post("/api/v1/components", json={
        "name": "电容", "quantity": 20, "zone": 1, "layer": 1, "slot": 2,
    })
    before = (await client.get("/api/v1/components")).json()
    response = await _delete(client, component["id"], 2)
    assert response.status_code == 409
    assert (await client.get("/api/v1/components")).json() == before
    assert (await _delete(client, 9999, 0)).status_code == 404
    assert (await _delete(client, component["id"], -1)).status_code == 422


async def test_concurrent_main_deletion_only_removes_one_position(client):
    component = await _group(client)
    responses = await asyncio.gather(
        _delete(client, component["id"], 0),
        _delete(client, component["id"], 0),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    current = (await client.get("/api/v1/components")).json()
    assert len(current) == 1 and current[0]["quantity"] == 100
    assert current[0]["slot_count"] == 2
