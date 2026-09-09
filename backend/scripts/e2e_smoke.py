"""开发期冒烟脚本：对运行中的服务做一次完整业务链路检查。

用法：python scripts/e2e_smoke.py [base_url]
"""

import json
import sys

try:  # Windows 控制台默认 GBK，强制 UTF-8 保证中文/emoji 可打印
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/api/v1"


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=10) as c:
        def show(label: str, resp: httpx.Response) -> httpx.Response:
            print(f"{label:<22} {resp.status_code}  {resp.text[:160]}")
            return resp

        health = show("health", c.get("/health"))
        assert health.status_code == 200

        # M4: HAL 状态（本机无 ESP32 → mock 模式）
        st = show("system/status", c.get("/system/status"))
        body = st.json()
        assert st.status_code == 200 and body["mode"] in ("serial", "mock")
        assert body["connected"] is True

        # 幂等：清空既有元件再开始
        for comp in c.get("/components").json():
            c.delete(f"/components/{comp['id']}")

        r = show("create 10k电阻", c.post("/components", json={
            "name": "10k电阻", "value": "10k", "package": "0603",
            "quantity": 15, "threshold": 3, "zone": 1, "layer": 1, "slot": 0,
        }))
        cid = r.json()["id"]

        cap = show("create 100nF电容", c.post("/components", json={
            "name": "100nF电容", "value": "100nF", "package": "0805",
            "quantity": 30, "threshold": 10, "zone": 1, "layer": 1, "slot": 1,
        })).json()
        capid = cap["id"]

        dup = show("duplicate slot", c.post("/components", json={
            "name": "重复件", "zone": 1, "layer": 1, "slot": 0,
        }))
        assert dup.status_code == 409

        names_dz = [x["name"] for x in c.get("/components", params={"q": "dz"}).json()]
        names_0603 = [x["name"] for x in c.get("/components", params={"q": "0603"}).json()]
        print(f"search dz    -> {names_dz}")
        print(f"search 0603  -> {names_0603}")
        assert names_dz == names_0603 == ["10k电阻"]

        show("out -12", c.post(f"/components/{cid}/stock", json={"delta": -12, "note": "焊板"}))
        short = show("out -5 (over)", c.post(f"/components/{cid}/stock", json={"delta": -5}))
        assert short.status_code == 409 and short.json()["detail"]["available"] == 3

        qty = c.get(f"/components/{cid}").json()["quantity"]
        print(f"final qty    -> {qty}")
        assert qty == 3

        tx = c.get("/transactions", params={"limit": 10}).json()
        print("transactions ->")
        for t in tx:
            print(f"   {t['kind']:<8} delta={t['delta']:<4} {t['detail']}")
        # 本次业务 = 建档x2 + 出库（失败的 409 不出流水）；更早的是清理时的删除
        assert [t["kind"] for t in tx[:3]] == ["out", "create", "create"]

        # ---- M3: BOM 规划 + 引导取料（复用上面的库存） ----
        plan = show("bom/plan", c.post("/bom/plan", json={
            "text": "10k电阻 x2, 100nF电容 x5, 11k电阻 x2",
        })).json()
        print("plan steps  ->", [(s["component"]["name"], s["quantity"])
                                 for s in plan["steps"]])
        print("plan missing->", [(m["reason"], m["raw"], m.get("available"))
                                 for m in plan["missing"]])
        assert plan["requested"] == 9
        # 足料步骤按灯带顺序：10k(led0) → 100nF(led1)，找不到的 11k 进 missing
        assert [(s["component"]["id"], s["quantity"]) for s in plan["steps"]] == \
            [(cid, 2), (capid, 5)]
        assert len(plan["missing"]) == 1
        assert plan["missing"][0]["reason"] == "not_found"

        show("bom/pick x2", c.post("/bom/pick", json={
            "component_id": cid, "amount": 2}))
        over = show("bom/pick over", c.post("/bom/pick", json={
            "component_id": cid, "amount": 5}))
        assert over.status_code == 409 and over.json()["detail"]["available"] == 1

        short = show("bom/plan short", c.post("/bom/plan", json={
            "text": "0.1uF电容 x999",
        })).json()
        # 0.1uF == 100nF 换算命中电容槽，999 > 余量 30 → shortage
        assert short["steps"] == [] and len(short["missing"]) == 1
        assert short["missing"][0]["reason"] == "shortage"
        assert short["missing"][0]["component_id"] == capid
        assert short["missing"][0]["available"] == 30

    print("\nE2E 冒烟通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())