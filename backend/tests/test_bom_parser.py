"""BOM 解析/规划/取料测试矩阵。

覆盖：分隔符与数量形态（x/×/*/个/只/pcs）、无空格粘连行、值换算等价
匹配（0.1uF == 100nF）、同元件多行合并为一步、缺料 shortage、找不到
not_found、纯封装匹配、中文名匹配、pick 原子扣减与审计。
"""

from io import BytesIO
from types import SimpleNamespace

from openpyxl import Workbook
from sqlalchemy import func, select

from app.db import async_session
from app.models import Transaction
from app.services import bom as bom_service


def _fields(line: bom_service.BomLine) -> dict:
    return line.to_dict()


def _comp(cid: int, name: str, value: str | None, package: str | None,
          quantity: int, led: int | None) -> SimpleNamespace:
    return SimpleNamespace(id=cid, name=name, value=value, package=package,
                           quantity=quantity, led_index=led)


# ---------- 纯函数：解析 ----------

def test_parse_separators_and_quantity_forms():
    text = "10k电阻x20，100nF电容×5；22Ω电阻 10 只\nLED指示灯 5pcs，0603电阻*3"
    lines = bom_service.parse_text(text)
    assert [l.quantity for l in lines] == [20, 5, 10, 5, 3]

    assert _fields(lines[0]) == dict(raw="10k电阻x20", name="电阻",
                                     value="10k", package=None, quantity=20)
    assert _fields(lines[1]) == dict(raw="100nF电容×5", name="电容",
                                     value="100nF", package=None, quantity=5)
    assert _fields(lines[2]) == dict(raw="22Ω电阻 10 只", name="电阻",
                                     value="22Ω", package=None, quantity=10)
    assert _fields(lines[3]) == dict(raw="LED指示灯 5pcs", name="LED指示灯",
                                     value=None, package=None, quantity=5)
    assert _fields(lines[4]) == dict(raw="0603电阻*3", name="电阻",
                                     value=None, package="0603", quantity=3)


def test_parse_defaults_quantity_one():
    lines = bom_service.parse_text("LED指示灯")
    assert len(lines) == 1
    assert _fields(lines[0]) == dict(raw="LED指示灯", name="LED指示灯",
                                     value=None, package=None, quantity=1)


def test_parse_separated_tokens_and_no_space_glue():
    row = bom_service.parse_text("0603 10k 电阻 20个")[0]
    assert _fields(row) == dict(raw="0603 10k 电阻 20个", name="电阻",
                                value="10k", package="0603", quantity=20)

    # 无空格粘连行：值 + 中文名 + 数量
    row = bom_service.parse_text("10k电阻x20")[0]
    assert _fields(row) == dict(raw="10k电阻x20", name="电阻",
                                value="10k", package=None, quantity=20)
    row = bom_service.parse_text("0.1uF电容×5")[0]
    assert _fields(row) == dict(raw="0.1uF电容×5", name="电容",
                                value="0.1uF", package=None, quantity=5)


# ---------- 纯函数：值归一化 ----------

def test_normalize_value_and_equality():
    assert bom_service.normalize_value("10k") == (10000.0, "R")
    assert bom_service.normalize_value("10K") == (10000.0, "R")
    assert bom_service.normalize_value("22Ω") == (22.0, "R")
    assert bom_service.normalize_value("22欧") == (22.0, "R")
    assert bom_service.normalize_value("22") == (22.0, "R")

    assert bom_service.norm_values_equal("0.1uF", "100nF")      # 换算等价
    assert bom_service.norm_values_equal("10k", "10000")        # 裸阻值换算
    assert bom_service.norm_values_equal("4.7uH", "4700nH")     # 电感族
    assert not bom_service.norm_values_equal("10k", "100nF")    # 家族不同
    assert bom_service.normalize_value("6.3V") is None          # 电压值不参与换算


# ---------- 纯函数：规划 ----------

def test_plan_pure_merge_shortage_order_and_not_found():
    comps = [
        _comp(1, "10k电阻", "10k", "0603", 10, led=2),
        _comp(2, "100nF电容", "100nF", "0805", 8, led=None),
        _comp(3, "LED指示灯", None, "1206", 6, led=0),
    ]
    lines = bom_service.parse_text(
        "0603 x5，10k电阻 x2，0.1uF电容 x2，LED指示灯 x3，2N2222 x1，10k电阻 x99"
    )
    plan = bom_service.plan_pure(lines, comps)

    assert plan["requested"] == 5 + 2 + 2 + 3 + 1 + 99

    # 同元件多行合并：010k 共需 106 > 库存 10 → 一条 shortage，不再出步骤
    missing = plan["missing"]
    assert missing[0]["reason"] == "shortage"
    assert missing[0]["component_id"] == 1 and missing[0]["available"] == 10
    assert missing[0]["quantity"] == 106
    # 找不到：2N2222 没有匹配槽位
    assert missing[1]["reason"] == "not_found"
    assert missing[1]["name"] == "2N2222" and missing[1]["quantity"] == 1

    # 步骤按 led_index 升序（None 排最后）；足料者才入列
    steps = plan["steps"]
    assert [(s["component"].id, s["quantity"]) for s in steps] == [(3, 3), (2, 2)]
    assert [s["line_indexes"] for s in steps] == [[3], [2]]


def test_plan_pure_package_and_chinese_name_match():
    comps = [
        _comp(1, "10k电阻", "10k", "0603", 15, led=0),
        _comp(2, "100nF电容", "100nF", "0805", 30, led=1),
    ]
    lines = bom_service.parse_text("0603 x5\n贴片电阻 x2")
    plan = bom_service.plan_pure(lines, comps)
    assert len(plan["steps"]) == 1  # 0603 只命中 10k电阻
    assert plan["steps"][0]["component"].id == 1
    assert plan["missing"][0]["reason"] == "not_found"  # 贴片电阻无对应槽位


# ---------- API：plan / pick 全链路 ----------

async def _seed(client, slot: int, *, name: str, value: str | None,
                package: str | None, quantity: int) -> dict:
    resp = await client.post("/api/v1/components", json={
        "name": name, "value": value, "package": package,
        "quantity": quantity, "threshold": 5, "zone": 1, "layer": 1,
        "slot": slot,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_bom_plan_and_pick_api_flow(client):
    a = await _seed(client, 0, name="10k电阻", value="10k",
                    package="0603", quantity=15)
    b = await _seed(client, 1, name="100nF电容", value="100nF",
                    package="0805", quantity=30)

    # 混合文本：同件合并 + 值换算匹配 + 找不到
    resp = await client.post("/api/v1/bom/plan", json={
        "text": "10k电阻 x2，10k电阻 x3，0.1uF电容 x4，11k电阻 x1",
    })
    assert resp.status_code == 200, resp.text
    plan = resp.json()
    assert plan["requested"] == 10 and plan["complete"] is False

    steps = plan["steps"]
    # led_index 升序：10k(led0) 在前，0.1uF→100nF(led1) 在后
    assert [s["component"]["id"] for s in steps] == [a["id"], b["id"]]
    assert [s["quantity"] for s in steps] == [5, 4]

    assert len(plan["missing"]) == 1
    m = plan["missing"][0]
    assert m["reason"] == "not_found" and m["quantity"] == 1
    assert m["name"] == "电阻" and m["value"] == "11k"

    # 引导取料：扣 5 → 余 10
    resp = await client.post("/api/v1/bom/pick",
                             json={"component_id": a["id"], "amount": 5})
    assert resp.status_code == 200 and resp.json()["quantity"] == 10

    # 再规划超出余量 → shortage（available=10，无步骤）
    resp = await client.post("/api/v1/bom/plan", json={"text": "10k电阻 x12"})
    assert resp.status_code == 200
    plan = resp.json()
    assert plan["steps"] == [] and len(plan["missing"]) == 1
    assert plan["missing"][0]["reason"] == "shortage"
    assert plan["missing"][0]["quantity"] == 12
    assert plan["missing"][0]["available"] == 10

    # 超量 pick → 409 + available；不存在元件 → 404；非法数量 → 422
    resp = await client.post("/api/v1/bom/pick",
                             json={"component_id": a["id"], "amount": 11})
    assert resp.status_code == 409
    assert resp.json()["detail"]["available"] == 10
    resp404 = await client.post("/api/v1/bom/pick",
                               json={"component_id": 9999, "amount": 1})
    resp422 = await client.post("/api/v1/bom/pick",
                                json={"component_id": a["id"], "amount": 0})
    assert resp404.status_code == 404
    assert resp422.status_code == 422


async def test_bom_pick_audit_kind_and_source(client):
    comp = await _seed(client, 0, name="10k电阻", value="10k",
                       package="0603", quantity=15)
    resp = await client.post("/api/v1/bom/pick",
                             json={"component_id": comp["id"], "amount": 4})
    assert resp.status_code == 200 and resp.json()["quantity"] == 11

    # 审计：kind=bom_pick、source=guide、同事务落一条
    tx = (await client.get("/api/v1/transactions")).json()
    assert tx[0]["kind"] == "bom_pick" and tx[0]["source"] == "guide"
    assert tx[0]["delta"] == -4 and "出库 4" in tx[0]["detail"]
    assert tx[1]["kind"] == "create"  # 建档流水仍在

    async with async_session() as session:
        pick_rows = await session.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.kind == "bom_pick")
        )
        assert pick_rows == 1  # 失败/并发时绝不重复落流水


def _make_bom_xlsx() -> bytes:
    """构造 EasyEDA/嘉立创风格表头的最小 xlsx。"""
    buf = BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.append(["Name", "Footprint", "Quantity"])
    ws.append(["100nF", "C0402", 11])                 # 电容 ×11
    ws.append(["10kΩ", "R0603", 19])                  # 电阻 ×19（值+欧姆符）
    ws.append(["STM32H750VBT6", "LQFP-100_L14.0-W14.0", 1])
    wb.save(buf)
    return buf.getvalue()


def test_excel_parser_recognizes_jlc_header():
    from app.services.bom import parse_excel_bytes

    lines = parse_excel_bytes(_make_bom_xlsx())
    assert len(lines) == 3
    row0 = lines[0].to_dict()
    assert row0["name"] == "电容" and row0["value"] == "100nF"
    assert row0["package"] == "0402" and row0["quantity"] == 11
    row1 = lines[1].to_dict()
    assert row1["name"] == "电阻" and row1["package"] == "0603"
    assert row1["quantity"] == 19
    # 板级器件名原样保留，LQFP-100 不得被误解析成阻值
    row2 = lines[2].to_dict()
    assert row2["name"] == "STM32H750VBT6" and row2["value"] is None


async def test_bom_import_excel_endpoint(client):
    resp = await client.post(
        "/api/v1/bom/import",
        files={"file": ("bom.xlsx", _make_bom_xlsx(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_quantity"] == 11 + 19 + 1
    assert [l["package"] for l in body["lines"]] == ["0402", "0603", None]
    assert body["lines"][0]["name"] == "电容"

    # 非 xlsx 内容 → 422 中文提示
    resp = await client.post(
        "/api/v1/bom/import",
        files={"file": ("bad.xlsx", b"not an xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 422 and "xlsx" in resp.json()["detail"]
