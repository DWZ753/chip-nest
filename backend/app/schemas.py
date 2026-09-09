"""Pydantic v2 出入参模型（REST API 契约）。"""

import datetime as dt
import json
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _clean_tags_list(values: list) -> list[str]:
    """标签清洗：去空白、去重、截断，最多 8 个、每个 ≤20 字符。"""
    seen: list[str] = []
    for raw in values:
        item = (raw or "").strip()[:20]
        if item and item not in seen and len(seen) < 8:
            seen.append(item)
    return seen


class LayoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    zone_count: int
    layer_count: int
    row_count: int
    col_count: int
    zone_names: list[str] = []
    updated_at: dt.datetime


class LayoutUpdate(BaseModel):
    zone_count: int = Field(ge=1, le=9)
    layer_count: int = Field(ge=1, le=20)
    row_count: int = Field(ge=1, le=20)
    col_count: int = Field(ge=1, le=50)
    # 每区自定义名称（数量与 zone_count 对齐，多余截断/不足留空=第N区）
    zone_names: list[str] = Field(default=[], max_length=9)


# ---------- 元件 ----------

class ComponentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    value: Optional[str] = Field(default=None, max_length=32)
    package: Optional[str] = Field(default=None, max_length=32)
    quantity: int = Field(default=0, ge=0)
    threshold: int = Field(default=5, ge=0)
    zone: int = Field(ge=1)
    layer: int = Field(ge=1)
    slot: int = Field(ge=0)
    # 缺省自动分配；显式给值需避开已占用序号
    led_index: Optional[int] = Field(default=None, ge=0)
    manufacturer_part: Optional[str] = Field(default=None, max_length=64)
    supplier_part: Optional[str] = Field(default=None, max_length=40)
    # 用户自定义标签：最多 8 个、每个不超过 20 字符，空白剔除
    tags: list[str] = Field(default=[], max_length=8)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, values):
        return _clean_tags_list(values)


class ComponentUpdate(BaseModel):
    """注意：quantity 不允许出现在本模型中（走 /stock 接口入出库）。"""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    value: Optional[str] = Field(default=None, max_length=32)
    package: Optional[str] = Field(default=None, max_length=32)
    threshold: Optional[int] = Field(default=None, ge=0)
    manufacturer_part: Optional[str] = Field(default=None, max_length=64)
    supplier_part: Optional[str] = Field(default=None, max_length=40)
    tags: Optional[list[str]] = Field(default=None, max_length=8)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, values):
        if values is None:
            return None
        return _clean_tags_list(values)

    led_index: Optional[int] = Field(default=None, ge=0)
    zone: Optional[int] = Field(default=None, ge=1)
    layer: Optional[int] = Field(default=None, ge=1)
    slot: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _position_must_be_grouped(self):
        """搬家必须三字段成组，避免只改一半导致槽位错乱。"""
        fields = (self.zone, self.layer, self.slot)
        if any(f is None for f in fields) and not all(f is None for f in fields):
            raise ValueError("搬家需同时提供 zone/layer/slot 三个字段")
        return self


class ComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    value: Optional[str]
    package: Optional[str]
    quantity: int
    threshold: int
    zone: int
    layer: int
    slot: int
    led_index: Optional[int]
    manufacturer_part: Optional[str] = None
    supplier_part: Optional[str] = None
    tags: list[str] = []

    @field_validator("tags", mode="before")
    @classmethod
    def _parse_tags(cls, value):
        """ORM 层存的是 JSON 文本，转回列表。"""
        if isinstance(value, str):
            try:
                parsed = json.loads(value) if value else []
            except ValueError:
                return []
            return parsed if isinstance(parsed, list) else []
        return value or []


class StockChange(BaseModel):
    delta: int = Field(..., description="正数入库，负数出库")  # 0 由业务层拒绝
    note: Optional[str] = Field(default=None, max_length=200)
    source: Literal["ui", "guide", "system"] = "ui"


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ts: dt.datetime
    kind: str
    component_id: Optional[int]
    delta: int
    detail: Optional[str]
    source: Optional[str]


# ---------- BOM 导入 / 引导取料 ----------

class BomImport(BaseModel):
    """粘贴的 BOM 原文：解析与规划两个接口共用同一请求体。"""

    text: str = Field(min_length=1, max_length=20000)


class BomLineOut(BaseModel):
    """一行 BOM 的解析结果（raw 保留原文供界面展示）。

    manufacturer_part/supplier_part 仅 Excel 导入行会携带（文本行省略）。
    """

    raw: str
    name: str = ""
    value: Optional[str] = None
    package: Optional[str] = None
    quantity: int = Field(ge=0)
    manufacturer_part: Optional[str] = None
    supplier_part: Optional[str] = None


class BomParseOut(BaseModel):
    """解析预览：行列表 + 合计数量（不查库存）。"""

    lines: list[BomLineOut]
    total_quantity: int = Field(ge=0)


class BomStepOut(BaseModel):
    """引导一步：哪个槽位、取多少个、由 BOM 哪些行合并而来。"""

    component: ComponentOut
    quantity: int = Field(ge=0)
    line_indexes: list[int] = []


class BomMissingOut(BaseModel):
    """缺料条目：not_found 是没找到槽位，shortage 是找到但量不足。"""

    reason: Literal["not_found", "shortage"]
    raw: str
    name: str = ""
    value: Optional[str] = None
    package: Optional[str] = None
    quantity: int = Field(ge=0)
    component_id: Optional[int] = None
    available: Optional[int] = None


class BomPlanOut(BaseModel):
    """规划结果：足料步骤（按灯带顺序）+ 缺料清单。"""

    steps: list[BomStepOut]
    missing: list[BomMissingOut]
    requested: int = Field(ge=0)
    complete: bool = False


class BomPick(BaseModel):
    """引导取料扣减：复用 /stock 的原子语义，source 固定为 guide。"""

    component_id: int = Field(ge=1)
    amount: int = Field(ge=1)