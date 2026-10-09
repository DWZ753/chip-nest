"""手动备份：快照完整、可恢复、创建失败时不修改库存。"""

import json
from pathlib import Path

from app import config
from app.routers import system


async def test_manual_backup_preserves_data_and_can_restore(client):
    response = await client.post("/api/v1/components", json={
        "name": "AMS1117-3.3", "quantity": 12, "threshold": 3,
        "zone": 1, "layer": 1, "slot": 0,
        "manufacturer_part": "AMS1117-3.3", "tags": ["电源"],
    })
    assert response.status_code == 201, response.text
    component_id = response.json()["id"]
    response = await client.post(
        f"/api/v1/components/{component_id}/slots",
        json={"zone": 1, "layer": 1, "slot": 1},
    )
    assert response.status_code == 200, response.text
    response = await client.post(
        "/api/v1/layout/blocked", json={"zone": 1, "layer": 1, "slot": 3},
    )
    assert response.status_code == 200, response.text
    components = (await client.get("/api/v1/components")).json()
    transactions = (await client.get("/api/v1/transactions")).json()
    layout = (await client.get("/api/v1/layout")).json()

    response = await client.post("/api/v1/system/backup")
    assert response.status_code == 200, response.text
    result = response.json()
    path = Path(result["backup_path"])
    snapshot = result["backup"]
    assert path.parent == config.backup_dir()
    assert snapshot == json.loads(path.read_text(encoding="utf-8"))
    assert snapshot["app"] == "ChipNest" and snapshot["reason"] == "manual"
    assert snapshot["components"] == components
    assert len(snapshot["transactions"]) == len(transactions)
    assert snapshot["blocked_slots"] == layout["blocked"]
    assert (await client.get("/api/v1/components")).json() == components
    assert (await client.get("/api/v1/layout")).json() == layout
    audit = (await client.get("/api/v1/transactions")).json()
    assert len(audit) == len(transactions) + 1
    assert audit[0]["kind"] == "backup"

    response = await client.post(
        f"/api/v1/components/{component_id}/stock", json={"delta": -2},
    )
    assert response.status_code == 200, response.text
    response = await client.post("/api/v1/system/restore", json={
        "confirm": "恢复", "backup": snapshot,
    })
    assert response.status_code == 200, response.text
    restored = (await client.get("/api/v1/components")).json()
    assert restored == components
    assert (await client.get("/api/v1/layout")).json() == layout


async def test_manual_backup_empty_database_and_unique_files(client):
    first = await client.post("/api/v1/system/backup")
    second = await client.post("/api/v1/system/backup")
    assert first.status_code == second.status_code == 200
    assert first.json()["backup"]["components"] == []
    assert first.json()["backup"]["transactions"] == []
    assert first.json()["backup"]["layout"]["zone_count"] == 1
    assert first.json()["backup_path"] != second.json()["backup_path"]
    assert Path(first.json()["backup_path"]).is_file()
    assert Path(second.json()["backup_path"]).is_file()


async def test_manual_backup_write_failure_leaves_data_intact(
    client, monkeypatch,
):
    def fail_write(*args, **kwargs):
        raise OSError("disk full")

    before = (await client.get("/api/v1/transactions")).json()
    monkeypatch.setattr(system, "_write_backup", fail_write)
    response = await client.post("/api/v1/system/backup")
    assert response.status_code == 500
    assert response.json()["detail"] == "备份创建失败"
    assert (await client.get("/api/v1/components")).json() == []
    assert (await client.get("/api/v1/transactions")).json() == before
