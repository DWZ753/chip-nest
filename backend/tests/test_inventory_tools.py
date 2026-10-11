"""本地功能：盘点原子性、合并核对、项目进度与补货需求。"""
from pathlib import Path

from app.db import async_session
from app.services import backup_manager


async def component(client, slot=0, **extra):
    """@brief 在独立测试库创建元件。"""
    response = await client.post("/api/v1/components", json={
        "name": "贴片电阻", "value": "10k", "package": "0603",
        "manufacturer_part": "R10K", "quantity": 20, "threshold": 5,
        "zone": 1, "layer": 1, "slot": slot, **extra,
    })
    assert response.status_code == 201, response.text
    return response.json()


async def project(client, **extra):
    """@brief 保存按料号确定匹配的单行项目。"""
    response = await client.post("/api/v1/bom/projects", json={
        "name": "电源模块", "copies": 2,
        "lines": [{"raw": "R10K x3", "name": "贴片电阻",
                   "value": "10k", "package": "0603", "quantity": 3,
                   "manufacturer_part": "R10K"}], **extra,
    })
    assert response.status_code == 201, response.text
    return response.json()


async def test_merge_conflicts_and_differences(client):
    await component(client)
    await component(client, 1, manufacturer_part="OTHER", tags=["电源"])
    preview = (await client.post(
        "/api/v1/system/merge-duplicates?dry_run=true",
    )).json()
    group = preview["groups"][0]
    assert group["conflicting"]
    assert "manufacturer_part" in group["differences"]
    assert len(group["members"]) == 2
    result = (await client.post("/api/v1/system/merge-duplicates")).json()
    assert result["merged_groups"] == 0 and result["skipped_groups"] == 1
    assert len((await client.get("/api/v1/components")).json()) == 2


async def test_merge_stale_preview_is_rejected(client):
    first = await component(client)
    await component(client, 1)
    group = (await client.post(
        "/api/v1/system/merge-duplicates?dry_run=true",
    )).json()["groups"][0]
    await client.post(f"/api/v1/components/{first['id']}/stock",
                      json={"delta": 1})
    result = await client.post("/api/v1/system/merge-duplicates", json={
        "groups": {str(group["keep_id"]): group["fingerprint"]},
    })
    assert result.status_code == 409
    assert len((await client.get("/api/v1/components")).json()) == 2


async def test_stocktake_batch_and_undo(client):
    first = await component(client)
    second = await component(client, 1, name="电容", manufacturer_part="C100N")
    response = await client.post("/api/v1/inventory/stocktake", json={
        "entries": [{"component_id": first["id"], "expected_quantity": 20,
                     "quantity": 17},
                    {"component_id": second["id"], "expected_quantity": 20,
                     "quantity": 0}], "note": "实物盘点",
    })
    assert response.status_code == 200, response.text
    assert response.json()["changed"] == 2
    result = await client.post("/api/v1/system/undo")
    assert result.status_code == 200 and result.json()["ok"]
    assert [row["quantity"] for row in
            (await client.get("/api/v1/components")).json()] == [20, 20]


async def test_stocktake_stale_is_all_or_nothing(client):
    first = await component(client)
    second = await component(client, 1)
    response = await client.post("/api/v1/inventory/stocktake", json={
        "entries": [{"component_id": first["id"], "expected_quantity": 20,
                     "quantity": 10},
                    {"component_id": second["id"], "expected_quantity": 19,
                     "quantity": 10}],
    })
    assert response.status_code == 409
    assert [row["quantity"] for row in
            (await client.get("/api/v1/components")).json()] == [20, 20]


async def test_project_pick_resume_repeat_and_undo(client):
    comp = await component(client)
    saved = await project(client)
    assert saved["plan"]["steps"][0]["quantity"] == 6
    pick_url = f"/api/v1/bom/projects/{saved['id']}/pick"
    payload = {"cursor": 0, "revision": saved["revision"]}
    response = await client.post(pick_url, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["component"]["quantity"] == 14
    assert response.json()["project"]["cursor"] == 1
    assert (await client.post(pick_url, json=payload)).status_code == 409
    reopened = (await client.get(
        f"/api/v1/bom/projects/{saved['id']}",
    )).json()
    assert reopened["cursor"] == 1
    assert (await client.post("/api/v1/system/undo")).json()["ok"]
    reopened = (await client.get(
        f"/api/v1/bom/projects/{saved['id']}",
    )).json()
    assert reopened["cursor"] == 0 and reopened["revision"] > saved["revision"]
    assert (await client.get(f"/api/v1/components/{comp['id']}")).json()["quantity"] == 20


async def test_project_missing_stock_does_not_advance(client):
    comp = await component(client)
    saved = await project(client)
    await client.post(f"/api/v1/components/{comp['id']}/stock",
                      json={"delta": -19})
    response = await client.post(f"/api/v1/bom/projects/{saved['id']}/pick", json={
        "cursor": 0, "revision": saved["revision"],
    })
    assert response.status_code == 409
    reopened = (await client.get(
        f"/api/v1/bom/projects/{saved['id']}",
    )).json()
    assert reopened["cursor"] == 0


async def test_backup_restores_projects_and_old_backup_is_compatible(client):
    await component(client)
    saved = await project(client)
    snapshot = (await client.post("/api/v1/system/backup")).json()["backup"]
    assert snapshot["projects"][0]["id"] == saved["id"]
    await client.delete(f"/api/v1/bom/projects/{saved['id']}")
    result = await client.post("/api/v1/system/restore", json={
        "confirm": "恢复", "backup": snapshot,
    })
    assert result.status_code == 200, result.text
    assert (await client.get("/api/v1/bom/projects")).json()[0]["name"] == saved["name"]
    del snapshot["projects"]
    result = await client.post("/api/v1/system/restore", json={
        "confirm": "恢复", "backup": snapshot,
    })
    assert result.status_code == 200
    assert (await client.get("/api/v1/bom/projects")).json() == []


async def test_backup_settings_history_and_auto_retention(client, tmp_path):
    response = await client.put("/api/v1/system/backup-settings", json={
        "enabled": True, "interval_hours": 1, "keep_count": 1,
        "directory": str(tmp_path),
    })
    assert response.status_code == 200, response.text
    manual = (await client.post("/api/v1/system/backup")).json()
    from app.routers.system import create_snapshot
    async with async_session() as session:
        await create_snapshot(session, "auto")
        await create_snapshot(session, "auto")
    backup_manager.prune_automatic(tmp_path, 1)
    files = (await client.get("/api/v1/system/backups")).json()
    assert len(files) == 2
    assert Path(manual["backup_path"]).exists()
    assert sum(item["reason"] == "auto" for item in files) == 1
    async with async_session() as session:
        assert not await backup_manager.run_due(session)
    download = await client.get(f"/api/v1/system/backups/{files[0]['name']}")
    assert download.status_code == 200 and download.json()["app"] == "ChipNest"


async def test_replenishment_aggregates_projects_without_double_count(client):
    await component(client, quantity=2)
    first = await project(client, copies=1)
    second = await project(client, copies=2)
    response = await client.post("/api/v1/inventory/replenishment", json={
        "project_ids": [first["id"], second["id"], second["id"]],
    })
    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["demand"] == 9 and item["purchase"] == 12
    assert item["available"] == 2 and item["threshold"] == 5


async def test_partial_project_replans_remaining_without_repeat(client):
    resistor = await component(client)
    capacitor = await component(
        client, 1, name="电容", manufacturer_part="C100N", quantity=0,
    )
    lines = [{"raw": "R10K", "manufacturer_part": "R10K", "quantity": 3},
             {"raw": "C100N", "manufacturer_part": "C100N", "quantity": 2}]
    saved = await project(client, copies=1, lines=lines)
    assert not saved["plan"]["complete"]
    url = f"/api/v1/bom/projects/{saved['id']}"
    picked = await client.post(url + "/pick", json={
        "cursor": 0, "revision": saved["revision"],
    })
    assert picked.status_code == 200, picked.text
    saved = picked.json()["project"]
    need = (await client.post("/api/v1/inventory/replenishment", json={
        "project_ids": [saved["id"]], "include_thresholds": False,
    })).json()["items"]
    assert len(need) == 1 and need[0]["component_id"] == capacitor["id"]
    assert need[0]["demand"] == 2
    await client.post(f"/api/v1/components/{capacitor['id']}/stock",
                      json={"delta": 5})
    body = {"name": saved["name"], "copies": 1, "lines": lines,
            "revision": saved["revision"]}
    response = await client.put(url, json=body)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["cursor"] == 1 and saved["plan"]["complete"]
    assert saved["plan"]["steps"][1]["line_indexes"] == [1]
    picked = await client.post(url + "/pick", json={
        "cursor": 1, "revision": saved["revision"],
    })
    assert picked.status_code == 200, picked.text
    assert (await client.get(
        f"/api/v1/components/{resistor['id']}",
    )).json()["quantity"] == 17
    saved = picked.json()["project"]
    body["revision"] = saved["revision"]
    assert (await client.put(url, json=body)).status_code == 200
    body["copies"] = 2
    body["revision"] += 1
    assert (await client.put(url, json=body)).status_code == 409


async def test_backup_due_and_invalid_files(client, tmp_path):
    await client.put("/api/v1/system/backup-settings", json={
        "enabled": True, "interval_hours": 1, "keep_count": 1,
        "directory": str(tmp_path),
    })
    async with async_session() as session:
        assert await backup_manager.run_due(session)
        assert not await backup_manager.run_due(session)
    (tmp_path / "chipnest-backup-000.json").write_text("{}", encoding="utf-8")
    (tmp_path / "unrelated.json").write_text("{}", encoding="utf-8")
    files = (await client.get("/api/v1/system/backups")).json()
    assert len(files) == 1 and files[0]["reason"] == "auto"
    assert (await client.get(
        "/api/v1/system/backups/chipnest-backup-000.json",
    )).status_code == 422
    assert (await client.delete(
        f"/api/v1/system/backups/{files[0]['name']}",
    )).status_code == 200
    assert (tmp_path / "unrelated.json").exists()
    invalid = await client.put("/api/v1/system/backup-settings", json={
        "directory": "relative", "interval_hours": 1, "keep_count": 1,
    })
    assert invalid.status_code == 422
    option = (await client.get("/api/v1/system/backup-settings")).json()
    assert option["directory"] == str(tmp_path.resolve())
