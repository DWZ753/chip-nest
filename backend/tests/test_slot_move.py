"""Atomic shared-slot placement, rollback and single-step undo."""

import asyncio

import pytest


async def create_shared(client):
    response = await client.post("/api/v1/components", json={
        "name": "拖动测试电阻", "quantity": 100,
        "zone": 1, "layer": 1, "slot": 0,
    })
    component = response.json()
    response = await client.post(
        f"/api/v1/components/{component['id']}/slots",
        json={"zone": 1, "layer": 1, "slot": 1},
    )
    assert response.status_code == 200
    return component["id"]


def move_payload(destination):
    return {
        "from_position": {"zone": 1, "layer": 1, "slot": 1},
        "to_position": {"zone": 1, "layer": 1, "slot": destination},
    }


async def test_shared_slot_move_and_single_undo(client):
    identifier = await create_shared(client)
    response = await client.patch(
        f"/api/v1/components/{identifier}/slots", json=move_payload(2),
    )
    assert response.status_code == 200, response.text
    component = response.json()
    assert component["quantity"] == 100
    assert component["slot_count"] == 2
    assert component["slot"] == 0
    assert [item["slot"] for item in component["slots"]] == [2]
    rows = (await client.get("/api/v1/transactions")).json()
    assert rows[0]["delta"] == 0
    assert "移动占用格" in rows[0]["detail"]
    result = await client.post("/api/v1/system/undo")
    assert result.status_code == 200 and result.json()["ok"]
    component = (await client.get(
        f"/api/v1/components/{identifier}",
    )).json()
    assert [item["slot"] for item in component["slots"]] == [1]
    assert component["quantity"] == 100


@pytest.mark.parametrize("invalid", ["occupied", "blocked", "outside", "own"])
async def test_invalid_shared_drop_retains_source_and_count(client, invalid):
    identifier = await create_shared(client)
    destination = 2
    if invalid == "occupied":
        await client.post("/api/v1/components", json={
            "name": "其他元件", "zone": 1, "layer": 1, "slot": 2,
        })
    elif invalid == "blocked":
        await client.post("/api/v1/layout/blocked", json={
            "zone": 1, "layer": 1, "slot": 2,
        })
    elif invalid == "outside":
        destination = 99
    else:
        destination = 0
    response = await client.patch(
        f"/api/v1/components/{identifier}/slots",
        json=move_payload(destination),
    )
    assert response.status_code in (400, 409), response.text
    component = (await client.get(
        f"/api/v1/components/{identifier}",
    )).json()
    assert component["quantity"] == 100
    assert component["slot_count"] == 2
    assert [item["slot"] for item in component["slots"]] == [1]


async def test_shared_source_can_only_be_moved_once_concurrently(client):
    identifier = await create_shared(client)
    path = f"/api/v1/components/{identifier}/slots"
    results = await asyncio.gather(
        client.patch(path, json=move_payload(2)),
        client.patch(path, json=move_payload(3)),
    )
    assert sorted(item.status_code for item in results) == [200, 409]
    component = (await client.get(
        f"/api/v1/components/{identifier}",
    )).json()
    assert component["quantity"] == 100
    assert component["slot_count"] == 2
    assert len(component["slots"]) == 1


async def test_same_shared_slot_is_a_noop(client):
    identifier = await create_shared(client)
    before = (await client.get("/api/v1/transactions")).json()
    response = await client.patch(
        f"/api/v1/components/{identifier}/slots", json=move_payload(1),
    )
    assert response.status_code == 200
    assert response.json()["slot_count"] == 2
    after = (await client.get("/api/v1/transactions")).json()
    assert len(after) == len(before)
