"""BOM 人工字段归一化、歧义候选和人工确认回归。"""

from types import SimpleNamespace

import pytest

from app.services.bom import BomLine, normalize_value, parse_text, plan_pure


def _component(cid=1, **fields):
    """构造纯匹配所需的库存字段。"""
    data = dict(id=cid, name="电阻", value="4.7kΩ", package="0603",
                quantity=10, led_index=cid, tags=[],
                manufacturer_part=None, supplier_part=None)
    data.update(fields)
    return SimpleNamespace(**data)


@pytest.mark.parametrize("text, expected", [
    ("4k7", (4700.0, "R")), ("4R7", (4.7, "R")),
    ("１Ｍ０", (1e6, "R")), ("10000 Ohms", (10000.0, "R")),
    ("0.1µF", (1e-7, "F")), ("22欧姆", (22.0, "R")),
])
def test_handwritten_unit_normalization(text, expected):
    value, family = normalize_value(text)
    assert value == pytest.approx(expected[0])
    assert family == expected[1]


def test_equivalent_value_and_package_match():
    line = BomLine("resistor 4k7 R0603", name="resistor", value="4k7",
                   package="R0603")
    plan = plan_pure([line], [_component(value="4.7kΩ ±1%")])
    assert len(plan["steps"]) == 1
    assert plan["choices"] == []


def test_specs_in_tags_and_name_match():
    component = _component(name="贴片电容", value=None, package=None,
                           tags='["0.1µF", "C0603"]')
    line = BomLine("电容 100nF 0603", name="电容", value="100nF",
                   package="0603")
    assert len(plan_pure([line], [component])["steps"]) == 1


def test_exact_specific_tag_matches():
    line = BomLine("AMS1117-3.3", name="ＡＭＳ１１１７－３.３")
    component = _component(name="稳压器", value=None, package="SOT-223",
                           tags=["ams1117 3.3"])
    assert len(plan_pure([line], [component])["steps"]) == 1


def test_fuzzy_models_require_confirmation():
    lines = parse_text("AMS1117-3.3 x2")
    assert lines[0].name == "AMS1117-3.3"
    assert lines[0].value is None
    component = _component(name="AMS1117-5.0", value=None, package="SOT223")
    plan = plan_pure(lines, [component])
    assert plan["steps"] == []
    assert plan["choices"][0]["candidates"][0]["reasons"] == ["名称相近"]


def test_same_voltage_and_package_do_not_auto_match_other_models():
    line = BomLine("AMS1117", name="AMS1117", value="3.3V",
                   package="SOT223")
    component = _component(name="AP1117", value="3.3V", package="SOT-223")
    assert plan_pure([line], [component])["steps"] == []


def test_decimal_model_suffix_is_preserved():
    line = BomLine("AMS1117-3.3", name="AMS1117-3.3")
    component = _component(name="AMS1117-33", value=None)
    assert plan_pure([line], [component])["steps"] == []


def test_decimal_voltage_is_not_equal_to_integer_voltage():
    line = BomLine("稳压器", name="AMS1117", value="3.3V")
    component = _component(name="AMS1117", value="33V")
    assert plan_pure([line], [component])["choices"] == []
    assert plan_pure([line], [component])["missing"]


def test_distinctive_name_is_not_overridden_by_value_and_package():
    line = BomLine("NTC 4k7", name="NTC", value="4k7", package="0603")
    plan = plan_pure([line], [_component()])
    assert plan["steps"] == []
    assert plan["choices"]


def test_ambiguous_matches_require_selection():
    line = BomLine("电阻 4k7 0603", name="电阻", value="4k7", package="0603")
    plan = plan_pure([line], [_component(1), _component(2)])
    assert plan["steps"] == []
    assert len(plan["choices"][0]["candidates"]) == 2
    selected = plan_pure([line], [_component(1), _component(2)], {0: 2})
    assert selected["steps"][0]["component"].id == 2
    assert selected["choices"] == []


@pytest.mark.parametrize("fields", [
    {"value": "47k"}, {"value": "4.7uF"}, {"package": "0805"},
    {"name": "电容"}, {"manufacturer_part": "OTHER"},
])
def test_conflicting_specs_are_excluded(fields):
    line = BomLine("电阻", name="电阻", value="4k7", package="0603",
                   manufacturer_part="R-4K7")
    plan = plan_pure([line], [_component(**fields)])
    assert plan["steps"] == []
    assert plan["choices"] == []
    assert plan["missing"][0]["reason"] == "not_found"


def test_part_match_with_spec_conflict_requires_confirmation():
    line = BomLine("电容", name="电容", value="100nF", package="0603",
                   supplier_part="C1234")
    component = _component(name="电容", value="10uF", supplier_part="C1234")
    plan = plan_pure([line], [component])
    assert plan["steps"] == []
    reasons = plan["choices"][0]["candidates"][0]["reasons"]
    assert "供应商料号相同" in reasons
    assert "标称值不一致" in reasons
    assert len(plan_pure([line], [component], {0: 1})["steps"]) == 1


def test_selections_preserve_aggregate_shortage():
    lines = [BomLine("贴片电阻", name="电阻", quantity=6)] * 2
    plan = plan_pure(lines, [_component()], {0: 1, 1: 1})
    assert plan["steps"] == []
    assert plan["choices"] == []
    assert plan["missing"][0]["quantity"] == 12
    assert plan["missing"][0]["available"] == 10


@pytest.mark.parametrize("selections", [{-1: 1}, {1: 1}, {0: 99}])
def test_invalid_selection_is_rejected(selections):
    with pytest.raises(ValueError):
        plan_pure([BomLine("电阻", name="电阻")], [_component()], selections)


async def test_candidate_api_selection_validation_and_no_stock_mutation(client):
    component = (await client.post("/api/v1/components", json={
        "name": "4.7k电阻", "value": "4.7k", "package": "0603",
        "quantity": 10, "zone": 1, "layer": 1, "slot": 0,
    })).json()
    body = {"lines": [{"raw": "电阻 x2", "name": "电阻", "quantity": 2}]}
    response = await client.post("/api/v1/bom/plan-rows", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["complete"] is False
    assert response.json()["choices"][0]["candidates"][0]["component"]["id"] \
        == component["id"]
    body["selections"] = {"0": component["id"]}
    response = await client.post("/api/v1/bom/plan-rows", json=body)
    assert response.json()["complete"] is True
    assert response.json()["steps"][0]["quantity"] == 2
    body["selections"] = {"0": 9999}
    assert (await client.post("/api/v1/bom/plan-rows", json=body)).status_code \
        == 422
    current = (await client.get(f'/api/v1/components/{component["id"]}')).json()
    assert current["quantity"] == 10
    assert len((await client.get("/api/v1/transactions")).json()) == 1
