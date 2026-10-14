"""联网识别：解析规则、字段映射、缓存与降级（网络用 MockTransport 假造）。"""

import json

import httpx
import pytest

from app.services.lookup import (
    Candidate, LookupService, detect_intent, extract_lcsc,
    get_lookup_service, looks_like_partno, matches_keyword, parse_value,
    split_query, value_matches,
)

RESISTOR_ROW = {
    "lcsc": 25804, "mfr": "0603WAF1002T5E", "description": "", "stock": 37165617,
    "price1": 0.000842857, "resistance": 10000, "package": "0603",
    "attributes": json.dumps({"Resistance": "10kΩ", "Tolerance": "±1%",
                              "Power(Watts)": "100mW"}, ensure_ascii=False),
}
CAP_ROW = {
    "lcsc": 14663, "mfr": "CC0603KRX7R9BB104",
    "description": "100nF 50V X7R ±10% 0603 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
    "stock": 12618106, "price1": 0.0022, "capacitance_farads": 1e-7, "package": "0603",
}
DETAIL = {
    "code": 200,
    "result": {
        "productCode": "C14663", "productModel": "CC0603KRX7R9BB104",
        "productNameEn": "CAP CER 100nF 50V X7R 0603", "brandNameEn": "YAGEO",
        "encapStandard": "0603", "stockNumber": 5782950,
        "pdfUrl": "https://datasheet.lcsc.com/datasheet/pdf/x.pdf?productCode=C14663",
        "catalogName": "Ceramic Capacitors", "parentCatalogName": "Capacitors",
        "paramVOList": [
            {"paramName": "容值", "paramNameEn": "Capacitance", "paramValue": "100nF"},
            {"paramName": "精度", "paramNameEn": "Tolerance", "paramValue": "±10%"},
        ],
    },
}


def make_service(handler, calls: list[str]) -> LookupService:
    """把假网络包成 httpx 客户端塞进服务；calls 记录被打的路径。"""

    def wrapped(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return handler(request)

    return LookupService(client=httpx.AsyncClient(transport=httpx.MockTransport(wrapped)))


RESISTOR_DETAIL = {
    "code": 200,
    "result": {
        "productCode": "C25804", "productModel": "0603WAF1002T5E",
        "productNameEn": "RES 10kΩ ±1% 100mW 0603", "brandNameEn": "UNI-ROYAL",
        "encapStandard": "0603", "stockNumber": 37165617,
        "pdfUrl": "https://datasheet.lcsc.com/datasheet/pdf/r.pdf?productCode=C25804",
        "catalogName": "Chip Resistor - Surface Mount", "parentCatalogName": "Resistors",
        "paramVOList": [
            {"paramName": "阻值", "paramNameEn": "Resistance", "paramValue": "10kΩ"},
            {"paramName": "精度", "paramNameEn": "Tolerance", "paramValue": "±1%"},
        ],
    },
}


STM32_ROW = {
    "lcsc": 404010, "mfr": "STM32H750VBT6", "package": "LQFP-100(14x14)",
    "stock": 1776, "price": 6.623,
    "description": "-40℃~+85℃ 1.62V~3.6V 128KB 1MB 32 Bit 480MHz ARM Cortex-M7 "
                   "Built-in FLASH LQFP-100(14x14) Microcontrollers (MCU/MPU/SOC) ROHS",
}
JUNK_MCU_ROW = {
    "lcsc": 8734, "mfr": "STM32F103C8T6", "package": "LQFP-48(7x7)", "stock": 214596,
    "description": "ARM Cortex-M3 Microcontrollers (MCU/MPU/SOC) ROHS",
}
STM32_EASYEDA = {
    "number": "C404010", "mpn": "STM32H750VBT6", "package": "LQFP-100(14x14)",
    "manufacturer": "ST", "stock": 1776, "description": "ARM Cortex-M7 MCU",
    "price": [[1, "8.22", "8.22"]],
}


def ok_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if "product/search" in path:
        kw = (request.url.params.get("keyword") or "").upper()
        rows = [STM32_EASYEDA] if kw in ("STM32H750VBT6", "C404010") else []
        return httpx.Response(200, json={"code": 0, "result": {"productList": rows}})
    if path.endswith("/resistors/list.json"):
        return httpx.Response(200, json={"resistors": [RESISTOR_ROW]})
    if path.endswith("/capacitors/list.json"):
        return httpx.Response(200, json={"capacitors": [CAP_ROW]})
    if path.endswith("/api/search"):
        q = (request.url.params.get("q") or "").upper()
        if q in ("C14663", "100NF"):
            return httpx.Response(200, json={"components": [CAP_ROW]})
        if q in ("C25804", "10K"):
            return httpx.Response(200, json={"components": [RESISTOR_ROW]})
        if q == "STM32H750VBT6":
            # 模拟真实情况：通用端点对冷门型号会返回不相干的同品类料
            return httpx.Response(200, json={"components": [JUNK_MCU_ROW]})
        return httpx.Response(200, json={"components": []})
    if "product/detail" in path:
        code = request.url.params.get("productCode")
        if code == "C14663":
            return httpx.Response(200, json=DETAIL)
        if code == "C25804":
            return httpx.Response(200, json=RESISTOR_DETAIL)
        return httpx.Response(200, json={"code": 404, "result": None})
    return httpx.Response(404, json={})


@pytest.fixture
def service_with_mock(app_client_override):
    """用假网络替换单例服务（返回 service 与调用记录）。"""
    calls: list[str] = []
    service = make_service(ok_handler, calls)
    app_client_override(get_lookup_service, lambda: service)
    return service, calls


@pytest.fixture
def app_client_override(client):
    """给 app.dependency_overrides 打补丁的小工具。"""
    from app.main import app

    def _override(dep, factory):
        app.dependency_overrides[dep] = factory

    yield _override
    app.dependency_overrides.pop(get_lookup_service, None)


def test_split_query_pulls_package_out():
    assert split_query("10k 0603") == ("10k", "0603")
    assert split_query("100nF 0603") == ("100nF", "0603")
    assert split_query("STM32F103C8T6") == ("STM32F103C8T6", None)
    assert split_query("CC0603KRX7R9BB104 0805") == ("CC0603KRX7R9BB104", "0805")


def test_detect_intent_and_lcsc():
    assert detect_intent("10k") == "resistors"
    assert detect_intent("4.7kΩ") == "resistors"
    assert detect_intent("100nF") == "capacitors"
    assert detect_intent("STM32F103C8T6") == "microcontrollers"
    assert detect_intent("AMS1117-3.3") == "voltage_regulators"
    assert detect_intent("随便写点什么") is None

    assert extract_lcsc("C14663") == "C14663"
    assert extract_lcsc("c14663") == "C14663"
    assert extract_lcsc("14663") == "C14663"
    assert extract_lcsc("10k 0603") is None


def test_partno_and_relevance_helpers():
    assert looks_like_partno("STM32H750VBT6") is True
    assert looks_like_partno("C14663") is True
    assert looks_like_partno("10k 0603") is False
    assert looks_like_partno("100nF") is False

    from app.services.lookup import Candidate
    hit = Candidate(lcsc="C404010", mpn="STM32H750VBT6")
    miss = Candidate(lcsc="C8734", mpn="STM32F103C8T6")
    assert matches_keyword(hit, "STM32H750VBT6") is True
    assert matches_keyword(miss, "STM32H750VBT6") is False
    described = Candidate(lcsc="C25804", mpn="0603WAF1002T5E", description="RES 10kΩ ±1% 0603")
    assert matches_keyword(described, "10kΩ") is True


async def test_autofill_keyword_fills_fields(client, service_with_mock):
    """'10k 0603' → 走电阻分类端点，再用详情补参数/数据手册，字段可直填。"""
    calls: list[str] = []
    service, _calls = service_with_mock
    resp = await client.post("/api/v1/lookup/autofill", json={"text": "10k 0603"})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["kind"] == "keyword" and body["online"] is True
    best = body["best"]
    assert best["lcsc"] == "C25804"
    assert best["value"] == "10kΩ"
    assert best["package"] == "0603"
    assert best["name"] == "10kΩ 0603 贴片电阻"
    assert best["category"] == "贴片电阻"
    assert best["manufacturer"] == "UNI-ROYAL"
    assert best["datasheet"], "详情补全后应带数据手册链接"
    assert best["params"]["阻值"] == "10kΩ"
    assert body["fields"]["name"] == "10kΩ 0603 贴片电阻"
    assert body["fields"]["value"] == "10kΩ"
    assert body["fields"]["package"] == "0603"
    assert body["fields"]["manufacturer_part"] == "0603WAF1002T5E"
    assert body["fields"]["supplier_part"] == "C25804"


async def test_autofill_lcsc_code_uses_detail(client, service_with_mock):
    """'C14663' → 走立创详情，参数/品牌/数据手册都带上。"""
    _service, _calls = service_with_mock
    resp = await client.post("/api/v1/lookup/autofill", json={"text": "C14663"})
    body = resp.json()

    assert body["kind"] == "lcsc"
    best = body["best"]
    assert best["mpn"] == "CC0603KRX7R9BB104"
    assert best["manufacturer"] == "YAGEO"
    assert best["value"] == "100nF"
    assert best["category"] == "陶瓷电容"
    assert best["name"] == "100nF 0603 陶瓷电容"
    assert best["stock"] == 5782950
    assert best["datasheet"].endswith("productCode=C14663")
    assert body["fields"]["supplier_part"] == "C14663"


async def test_search_result_is_cached(client, service_with_mock):
    """同一查询第二次不再打网络（搜索与详情都走缓存）。"""
    _service, calls = service_with_mock
    first = await client.post("/api/v1/lookup/autofill", json={"text": "10k 0603"})
    after_first = len(calls)
    second = await client.post("/api/v1/lookup/autofill", json={"text": "10k 0603"})

    assert first.json()["best"]["lcsc"] == second.json()["best"]["lcsc"]
    assert len(calls) == after_first, "第二次仍打了网络"
    # 首次：按阻值查分类一次，详情补全一次；再次查询全部走缓存。
    assert not any(path.endswith("/api/search") for path in calls)
    assert sum(1 for path in calls if "product/detail" in path) == 1
    assert sum(1 for path in calls if path.endswith("list.json")) == 1


async def test_partno_query_drops_irrelevant_hits(client, service_with_mock):
    """型号查询：通用端点返回同品类的别的料时，不能答非所问（STM32H750VBT6）。"""
    _service, calls = service_with_mock
    resp = await client.post("/api/v1/lookup/autofill", json={"text": "STM32H750VBT6"})
    body = resp.json()

    assert body["best"] is not None
    assert body["best"]["mpn"] == "STM32H750VBT6"
    assert body["best"]["lcsc"] == "C404010"
    assert body["best"]["package"] == "LQFP-100(14x14)"
    assert all(c["mpn"] != "STM32F103C8T6" for c in body["candidates"]), "混进了不相干的料"
    # 通用端点没给出对得上的型号时才去问 EasyEDA
    assert any("product/search" in path for path in calls)


async def test_value_query_falls_back_to_category(client, app_client_override):
    """值类查询直接使用分类端点的结构化参数。"""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/search"):
            return httpx.Response(200, json={"components": []})
        if request.url.path.endswith("/resistors/list.json"):
            return httpx.Response(200, json={"resistors": [RESISTOR_ROW]})
        if "product/detail" in request.url.path:
            return httpx.Response(200, json=RESISTOR_DETAIL)
        return httpx.Response(404, json={})

    app_client_override(get_lookup_service, lambda: make_service(handler, calls))
    resp = await client.post("/api/v1/lookup/autofill", json={"text": "10k 0603"})
    body = resp.json()

    assert body["best"] is not None and body["best"]["lcsc"] == "C25804"
    assert any(path.endswith("list.json") for path in calls)


async def test_offline_reports_clearly(client, app_client_override):
    """全部数据源都连不上：不抛 500，返回 online=false。"""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network", request=request)

    app_client_override(get_lookup_service, lambda: make_service(handler, []))
    resp = await client.post("/api/v1/lookup/autofill", json={"text": "10k 0603"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["best"] is None and body["candidates"] == []
    assert body["online"] is False


async def test_detail_endpoint_404_when_unknown(client, app_client_override):
    """编号查不到 → 404 + 中文提示。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 404, "result": None})

    app_client_override(get_lookup_service, lambda: make_service(handler, []))
    resp = await client.get("/api/v1/lookup/detail", params={"lcsc": "C99999999"})
    assert resp.status_code == 404
    assert "没查到" in resp.json()["detail"]


async def test_search_endpoint_returns_ranked_list(client, service_with_mock):
    """搜索接口：指定封装时，封装相符的排在前面。"""
    resp = await client.get("/api/v1/lookup/search", params={"q": "100nF", "package": "0603"})
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert rows and rows[0]["package"] == "0603"


@pytest.mark.parametrize("query, expected", [
    ("1k", ("R", 1000)),
    ("1K0", ("R", 1000)),
    ("4k7", ("R", 4700)),
    ("4r7", ("R", 4.7)),
    ("1000ohm", ("R", 1000)),
    ("470uf", ("C", 0.00047)),
    ("470μF", ("C", 0.00047)),
    ("25V", None),
    ("0603WAF1001T5E", None),
])
def test_value_parser_rejects_unrelated_units(query, expected):
    assert parse_value(query) == expected


def test_value_matching_rejects_different_component_types():
    assert value_matches("1k", "100nF") is False
    assert value_matches("470uF", "470Ω") is False
    assert value_matches("1k", "1000Ω") is True
    assert value_matches("1k", "10kΩ") is False
    assert value_matches("1k", "") is None
    assert value_matches("0R", "0Ω") is True
    assert value_matches("470uF", "475uF") is False


ONE_K_ROW = {
    **RESISTOR_ROW, "lcsc": 21190, "mfr": "0603WAF1001T5E",
    "resistance": 1000,
    "attributes": json.dumps({"Resistance": "1kΩ"}),
}
SMD_CAP_ROW = {
    **CAP_ROW, "lcsc": 9990001, "mfr": "SMD470UF25V",
    "package": "SMD,D8xL10mm", "capacitance_farads": 0.00047,
    "description": "470uF 25V Aluminum Electrolytic Capacitors - SMD",
}
LEADED_CAP_ROW = {
    **SMD_CAP_ROW, "lcsc": 9990002, "mfr": "LEADED470UF25V",
    "package": "插件,D8xL12mm", "is_surface_mount": True,
    "stock": 99999999, "is_basic": True,
    "description": "470uF 25V Aluminum Electrolytic Capacitors - Leaded",
}


async def test_resistance_query_filters_caps_and_uses_numeric_category(
    client, app_client_override,
):
    """上游通用结果全为电容时仍能找到正确 1kΩ 0603 电阻。"""
    calls = []

    def handler(request):
        if request.url.path.endswith("/resistors/list.json"):
            assert request.url.params.get("resistance") == "1000"
            rows = [RESISTOR_ROW] * 12 + [ONE_K_ROW]
            return httpx.Response(200, json={"resistors": rows})
        if request.url.path.endswith("/api/search"):
            return httpx.Response(200, json={"components": [CAP_ROW]})
        return httpx.Response(200, json={"result": None})

    app_client_override(get_lookup_service, lambda: make_service(handler, calls))
    response = await client.post(
        "/api/v1/lookup/autofill", json={"text": "1k 0603"})
    body = response.json()
    assert body["best"]["lcsc"] == "C21190"
    assert body["best"]["value"] == "1kΩ"
    assert all(row["category"] == "贴片电阻"
               for row in body["candidates"])


@pytest.mark.parametrize("query, expected", [
    ("470uf 25V 贴片", "C9990001"),
    ("贴片 25v 470 μF", "C9990001"),
    ("470UF 25V SMD", "C9990001"),
    ("470uF 25V 直插", "C9990002"),
    ("470uF 25V 插件", "C9990002"),
    ("470uF 25V through-hole", "C9990002"),
    ("电容 470uf 25V 贴片", "C9990001"),
])
async def test_capacitor_query_checks_voltage_and_mounting(
    client, app_client_override, query, expected,
):
    """安装方式和电压优先于基础库与库存热度。"""
    wrong_voltage = {
        **SMD_CAP_ROW, "lcsc": 9990003,
        "description": "470uF 16V Aluminum Electrolytic Capacitors - SMD",
    }

    def handler(request):
        rows = [LEADED_CAP_ROW, wrong_voltage, CAP_ROW, SMD_CAP_ROW]
        if request.url.path.endswith("/capacitors/list.json"):
            assert request.url.params.get("capacitance") == "0.00047"
            return httpx.Response(200, json={"capacitors": rows})
        if request.url.path.endswith("/api/search"):
            return httpx.Response(200, json={"components": rows})
        return httpx.Response(200, json={"result": None})

    app_client_override(get_lookup_service, lambda: make_service(handler, []))
    response = await client.post(
        "/api/v1/lookup/autofill", json={"text": query})
    body = response.json()
    assert [row["lcsc"] for row in body["candidates"]] == [expected]
    assert body["best"]["lcsc"] == expected


async def test_unmatched_constraints_return_no_candidate(
    client, app_client_override,
):
    """只有直插 470uF 电容时，不自动填入贴片查询。"""
    def handler(request):
        return httpx.Response(200, json={
            "components": [LEADED_CAP_ROW],
            "capacitors": [LEADED_CAP_ROW],
            "result": {"productList": []},
        })

    app_client_override(get_lookup_service, lambda: make_service(handler, []))
    response = await client.post(
        "/api/v1/lookup/autofill", json={"text": "470uf 25V 贴片"})
    body = response.json()
    assert body["online"] is True
    assert body["best"] is None
    assert body["fields"] == {}
    assert body["candidates"] == []


async def test_old_search_cache_does_not_preserve_wrong_results(client):
    """算法升级后不再复用旧查询里的电容候选。"""
    from app.db import async_session

    service = make_service(ok_handler, [])
    async with async_session() as session:
        await service._cache_put(session, "search:v2:10k|0603|8", [
            Candidate(lcsc="C14663", value="100nF").to_dict(),
        ])
        result = await service.search(session, "10k", "0603", 8)
        assert result[0].lcsc == "C25804"


@pytest.mark.parametrize("source", ["generic", "easyeda"])
async def test_constraints_are_checked_on_fallback_sources(
    client, app_client_override, source,
):
    """分类源不可用时，后备源同样排除直插和错误电压。"""
    def handler(request):
        rows = [LEADED_CAP_ROW, SMD_CAP_ROW]
        if request.url.path.endswith("/api/search") and source == "generic":
            return httpx.Response(200, json={"components": rows})
        if "product/search" in request.url.path and source == "easyeda":
            products = [{**row, "number": f"C{row['lcsc']}"} for row in rows]
            return httpx.Response(200, json={
                "result": {"productList": products},
            })
        return httpx.Response(200, json={"result": None})

    app_client_override(get_lookup_service, lambda: make_service(handler, []))
    response = await client.post(
        "/api/v1/lookup/autofill", json={"text": "470uf 25V 贴片"})
    body = response.json()
    assert [row["lcsc"] for row in body["candidates"]] == ["C9990001"]


async def test_detail_enrichment_cannot_replace_matching_spec(
    client, app_client_override,
):
    """详情规格冲突时保留搜索核对过的正确候选。"""
    def handler(request):
        if request.url.path.endswith("/capacitors/list.json"):
            return httpx.Response(200, json={"capacitors": [SMD_CAP_ROW]})
        if "product/detail" in request.url.path:
            return httpx.Response(200, json={
                "result": {**DETAIL["result"], "productCode": "C9990001"},
            })
        return httpx.Response(200, json={})

    app_client_override(get_lookup_service, lambda: make_service(handler, []))
    response = await client.post(
        "/api/v1/lookup/autofill", json={"text": "470uf 25V 贴片"})
    assert response.json()["best"]["value"] == "470uF"
    assert response.json()["best"]["package"] == "SMD,D8xL10mm"


def test_capacitor_value_does_not_use_esr():
    """参数表中的等效串联电阻不是容量。"""
    service = LookupService()
    candidate = service._from_lcsc_detail({
        "paramVOList": [
            {"paramNameEn": "Equivalent Series Resistance", "paramValue": "3Ω"},
            {"paramNameEn": "Capacitance", "paramValue": "470uF"},
        ],
    })
    assert candidate.value == "470uF"
