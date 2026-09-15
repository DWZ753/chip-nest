"""联网识别：解析规则、字段映射、缓存与降级（网络用 MockTransport 假造）。"""

import json

import httpx
import pytest

from app.services.lookup import (
    LookupService, detect_intent, extract_lcsc, get_lookup_service, looks_like_partno,
    matches_keyword, split_query,
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
    # 首次：通用搜索 1 次 + 详情补全 1 次（分类端点不再参与）
    assert sum(1 for path in calls if path.endswith("/api/search")) == 1
    assert sum(1 for path in calls if "product/detail" in path) == 1
    assert not any(path.endswith("list.json") for path in calls)


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
    """值类查询且通用端点没结果时，才用分类端点按品类兜底。"""
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
