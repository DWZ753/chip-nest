"""Pydantic v2 出入参模型（REST API 契约）。"""

import datetime as dt
import json
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_CARD_FIELDS = ("value", "package", "mpn", "supplier")


def _clean_fields(values: list) -> list[str]:
    """卡片显示字段白名单（value/package/mpn/supplier），默认 value+package。"""
    chosen = {str(v).strip() for v in (values or [])}
    kept = [f for f in _CARD_FIELDS if f in chosen]
    return kept or ["value", "package"]


def _clean_card_items(values: list) -> list[str]:
    """统一顺序 token：字段名（value/package/mpn/supplier）或 "#标签"。"""
    kept: list[str] = []
    for raw in values or []:
        token = str(raw).strip()
        if token in _CARD_FIELDS:
            pass
        elif token.startswith("#") and 1 < len(token) <= 21:
            token = "#" + token[1:].strip()[:20]
        else:
            continue
        if token not in kept:
            kept.append(token)
    return kept[:24]


def _clean_tags_list(values: list, cap: int = 8) -> list[str]:
    """标签清洗：去空白、去重、截断，最多 cap 个、每个 ≤20 字符。"""
    seen: list[str] = []
    for raw in values:
        item = (raw or "").strip()[:20]
        if item and item not in seen and len(seen) < cap:
            seen.append(item)
    return seen


class LayoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    zone_count: int
    layer_count: int
    row_count: int
    col_count: int
    zone_names: list[str] = []
    # 每区 [行, 列]；长度与 zone_count 对齐
    zone_sizes: list[list[int]] = []
    # 每区层数；长度与 zone_count 对齐（缺项回落 layer_count）
    zone_layers: list[int] = []
    updated_at: dt.datetime


class LayoutUpdate(BaseModel):
    zone_count: int = Field(ge=1, le=9)
    layer_count: int = Field(ge=1, le=20)
    row_count: int = Field(ge=1, le=20)
    col_count: int = Field(ge=1, le=50)
    # 每区自定义名称（数量与 zone_count 对齐，多余截断/不足留空=第N区）
    zone_names: list[str] = Field(default=[], max_length=9)
    # 每区独立尺寸：[行, 列]，缺项沿用 row_count/col_count
    zone_sizes: list[list[int]] = Field(default=[], max_length=9)
    # 每区独立层数，缺项沿用 layer_count
    zone_layers: list[int] = Field(default=[], max_length=9)

    @field_validator("zone_layers")
    @classmethod
    def _check_zone_layers(cls, values):
        cleaned = []
        for item in values or []:
            layers = int(item)
            if not 1 <= layers <= 20:
                raise ValueError("每区层数 1-20")
            cleaned.append(layers)
        return cleaned

    @field_validator("zone_sizes")
    @classmethod
    def _check_zone_sizes(cls, values):
        cleaned = []
        for item in values or []:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise ValueError("zone_sizes 每项必须是 [行, 列]")
            rows, cols = int(item[0]), int(item[1])
            if not 1 <= rows <= 20 or not 1 <= cols <= 50:
                raise ValueError("每区行数 1-20、列数 1-50")
            cleaned.append([rows, cols])
        return cleaned


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
    # 外部可见标签：≤3 个，通常取 tags 的子集
    display_tags: list[str] = Field(default=[], max_length=3)
    display_fields: list[str] = Field(default=["value", "package"], max_length=4)
    card_items: list[str] = Field(default=[], max_length=24)

    @field_validator("card_items")
    @classmethod
    def _check_card_items(cls, values):
        return _clean_card_items(values)

    @field_validator("display_fields")
    @classmethod
    def _check_display_fields(cls, values):
        return _clean_fields(values)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, values):
        return _clean_tags_list(values, 8)

    @field_validator("display_tags")
    @classmethod
    def _clean_display_tags(cls, values):
        return _clean_tags_list(values, 3)


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
    display_tags: Optional[list[str]] = Field(default=None, max_length=3)
    display_fields: Optional[list[str]] = Field(default=None, max_length=4)
    card_items: Optional[list[str]] = Field(default=None, max_length=24)

    @field_validator("card_items")
    @classmethod
    def _check_card_items(cls, values):
        return None if values is None else _clean_card_items(values)

    @field_validator("display_fields")
    @classmethod
    def _check_display_fields(cls, values):
        return None if values is None else _clean_fields(values)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, values):
        if values is None:
            return None
        return _clean_tags_list(values, 8)

    @field_validator("display_tags")
    @classmethod
    def _clean_display_tags(cls, values):
        if values is None:
            return None
        return _clean_tags_list(values, 3)

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


class SlotOut(BaseModel):
    """一个附加格（附加格不单独记数量，库存算在元件上）。"""

    model_config = ConfigDict(from_attributes=True)

    zone: int
    layer: int
    slot: int


class SlotAdd(BaseModel):
    """给元件追加一个附加格。"""

    zone: int = Field(ge=1)
    layer: int = Field(ge=1)
    slot: int = Field(ge=0)


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
    display_tags: list[str] = []
    display_fields: list[str] = ["value", "package"]
    card_items: list[str] = []
    # 额外占用的格子；slot_count = 1 + len(slots)
    slots: list[SlotOut] = []
    slot_count: int = 1

    @field_validator("tags", "display_tags", "display_fields", "card_items",
                     mode="before")
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


class MergeGroupOut(BaseModel):
    """一组可合并的重复元件（同名同值同封装）。"""

    name: str
    value: str = ""
    package: str = ""
    keep_id: int
    member_ids: list[int] = []
    total_quantity: int = Field(ge=0)
    moved_slots: int = Field(ge=0)   # 变成附加格的格子数


class MergeResultOut(BaseModel):
    dry_run: bool
    groups: list[MergeGroupOut] = []
    merged_groups: int = Field(ge=0)
    merged_components: int = Field(ge=0)


class SwapRequest(BaseModel):
    """两个元件互换槽位（同区/跨区都行）。"""

    a_id: int = Field(ge=1)
    b_id: int = Field(ge=1)


class SwapOut(BaseModel):
    """互换后的两个元件（位置与灯号都已对调）。"""

    a: ComponentOut
    b: ComponentOut


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ts: dt.datetime
    kind: str
    component_id: Optional[int]
    delta: int
    detail: Optional[str]
    source: Optional[str]


# ---------- 联网识别 ----------

class LookupRequest(BaseModel):
    """任意输入：'10k 0603' / 'C14663' / 'STM32F103C8T6'。"""

    text: str = Field(min_length=1, max_length=80)


class LookupCandidateOut(BaseModel):
    """一个候选元件：字段名对齐 Component，另带网络侧信息供界面展示。"""

    lcsc: str = ""
    mpn: str = ""
    name: str = ""          # 建议填进「名称」的短名
    value: str = ""
    package: str = ""
    manufacturer: str = ""
    category: str = ""
    description: str = ""
    stock: int = 0
    price: Optional[float] = None
    datasheet: str = ""
    source: str = ""
    params: dict[str, str] = {}


class LookupResultOut(BaseModel):
    query: str
    kind: Literal["lcsc", "keyword"] = "keyword"
    best: Optional[LookupCandidateOut] = None
    candidates: list[LookupCandidateOut] = []
    # 直接能填进元件表单的字段（name/value/package/mpn/supplier）
    fields: dict[str, str] = {}
    # 至少有一个数据源正常应答（False=网络不通，界面据此提示）
    online: bool = True


# ---------- 数据维护 ----------

class DataSummaryOut(BaseModel):
    """数据概况：清空按钮据此禁用（啥都没有时不给点）。"""

    components: int = Field(ge=0)
    transactions: int = Field(ge=0)
    empty: bool


class ReindexResult(BaseModel):
    """灯带序号重排结果：总元件数 + 序号有变动的数量。"""

    total: int = Field(ge=0)
    changed: int = Field(ge=0)


class ResetRequest(BaseModel):
    """清空所有数据：confirm 必须等于确认词（前端要用户手输），防误触。"""

    confirm: str = Field(min_length=1, max_length=16)
    # True=布局也恢复为初始值；False=保留当前分区/尺寸，只清元件与流水
    reset_layout: bool = True


class ResetResult(BaseModel):
    """清空结果：删除条数 + 自动备份文件位置（可据此手工恢复）。"""

    deleted_components: int = Field(ge=0)
    deleted_transactions: int = Field(ge=0)
    backup_path: str
    layout_reset: bool


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