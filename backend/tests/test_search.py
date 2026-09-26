"""模糊检索矩阵：封装号 / 阻值 / 汉字 / 拼音首字母（大小写不敏感）。"""


async def _seed(client):
    items = [
        {"name": "贴片电阻", "value": "10k", "package": "0603", "slot": 0},
        {"name": "电解电容", "value": "100uF", "package": "6.3V", "slot": 1},
        {"name": "LED指示灯", "value": "", "package": "0805", "slot": 2},
    ]
    for item in items:
        resp = await client.post("/api/v1/components", json={
            "quantity": 20, "threshold": 5, "zone": 1, "layer": 1, **item,
        })
        assert resp.status_code == 201, resp.text


async def _names(client, q: str) -> list[str]:
    resp = await client.get("/api/v1/components", params={"q": q})
    assert resp.status_code == 200
    return [row["name"] for row in resp.json()]


async def test_search_matrix(client):
    await _seed(client)

    assert await _names(client, "0603") == ["贴片电阻"]          # 封装号
    assert await _names(client, "10k") == ["贴片电阻"]           # 阻值
    assert await _names(client, "dz") == ["贴片电阻"]            # 电阻 首字母
    assert await _names(client, "DZ") == ["贴片电阻"]            # 大小写不敏感
    assert set(await _names(client, "电阻")) == {"贴片电阻"}      # 汉字子串
    assert set(await _names(client, "电容")) == {"电解电容"}
    assert await _names(client, "led") == ["LED指示灯"]          # 名称中的 ASCII 子串
    assert await _names(client, "zsd") == ["LED指示灯"]          # 指示灯 = zsd
    assert await _names(client, "不存在的料") == []


async def test_filter_by_zone_and_layer(client):
    await _seed(client)
    rows = (await client.get("/api/v1/components", params={"zone": 1, "layer": 2})).json()
    assert rows == []  # 层 2 没有元件


async def test_component_list_supports_offset(client):
    await _seed(client)

    rows = (await client.get(
        "/api/v1/components", params={"limit": 1, "offset": 1},
    )).json()

    assert len(rows) == 1
    assert rows[0]["slot"] == 1


async def test_search_options_and_filtered_pagination(client):
    items = [
        {"name": "电阻", "value": "47", "slot": 0},
        {"name": "电阻", "value": "470", "slot": 1},
        {"name": "LED", "value": "blue", "slot": 2,
         "supplier_part": "C14663"},
    ]
    for item in items:
        response = await client.post("/api/v1/components", json={
            "quantity": 1, "threshold": 0, "package": "0603",
            "zone": 1, "layer": 1, **item,
        })
        assert response.status_code == 201, response.text

    async def slots(**params):
        response = await client.get("/api/v1/components", params=params)
        assert response.status_code == 200, response.text
        return [row["slot"] for row in response.json()]

    assert await slots(q="47") == [0, 1]
    assert await slots(q="47", whole_word=True) == [0]
    assert await slots(q="47", whole_word=True, offset=1) == []
    assert await slots(q="47", use_regex=True) == [0, 1]
    assert await slots(q="^47$", use_regex=True) == [0]
    assert await slots(q="^47", use_regex=True, limit=1, offset=1) == [1]
    assert await slots(q="led", match_case=True) == []
    assert await slots(q="LED", match_case=True) == [2]
    assert await slots(q="led", match_case=False, whole_word=True) == [2]
    assert await slots(q="C14663") == [2]
    assert await slots(q="C14663", whole_word=True) == [2]

    response = await client.get(
        "/api/v1/components", params={"q": "[", "use_regex": True},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "正则表达式无效"
