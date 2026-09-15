"""元件联网识别：输入料号/描述 → 自动匹配立创编号并填好字段。

数据源按可用性逐个降级（任一环失败都不会把错误抛给界面）：
1. jlcsearch 社区 API（免鉴权）：分类端点更准，通用 /api/search 兜底；
2. 立创商城详情接口：拿完整参数（阻值/容值…）、品牌、数据手册链接；
3. EasyEDA Pro 搜索：前两个都拿不到时的备用源。

结果写进 SQLite 缓存表 lookup_cache（搜索 12 小时、详情 7 天），
同一查询短时间内不再打网络；所有网络异常都降级成「查不到」。
"""

import datetime as dt
import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LookupCache, utcnow

JLC_BASE = "https://jlcsearch.tscircuit.com"
EASYEDA_SEARCH = "https://pro.easyeda.com/api/eda/product/search"
LCSC_DETAIL = "https://wmsc.lcsc.com/ftps/wm/product/detail"

TIMEOUT = float(os.getenv("CHIPNEST_LOOKUP_TIMEOUT", "8"))
CACHE_SEARCH_TTL = dt.timedelta(hours=12)
CACHE_DETAIL_TTL = dt.timedelta(days=7)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ChipNest/1.3"

# 品类中文名：命中即用来拼元件名（如「10kΩ 0603 贴片电阻」）
_CATEGORY_CN: tuple[tuple[str, str], ...] = (
    ("chip resistor", "贴片电阻"), ("resistor", "电阻"),
    ("mlcc", "陶瓷电容"), ("ceramic capacitor", "陶瓷电容"),
    ("aluminum electrolytic", "电解电容"), ("capacitor", "电容"),
    ("microcontroller", "单片机"), ("mcu", "单片机"),
    ("voltage regulator", "稳压器"), ("ldo", "稳压器"), ("dc-dc", "电源芯片"),
    ("rectifier", "整流管"), ("schottky", "肖特基二极管"), ("diode", "二极管"),
    ("led", "发光二极管"), ("mosfet", "场效应管"), ("transistor", "三极管"),
    ("inductor", "电感"), ("ferrite bead", "磁珠"), ("crystal", "晶振"),
    ("oscillator", "晶振"), ("connector", "连接器"), ("header", "排针"),
    ("usb", "USB"), ("eeprom", "存储器"), ("flash", "存储器"), ("memory", "存储器"),
    ("operational amplifier", "运放"), ("op amp", "运放"), ("comparator", "比较器"),
    ("adc", "ADC"), ("dac", "DAC"), ("sensor", "传感器"), ("relay", "继电器"),
    ("fuse", "保险丝"), ("switch", "开关"), ("buzzer", "蜂鸣器"), ("socket", "插座"),
    ("terminal", "端子"), ("battery", "电池"), ("module", "模块"),
    ("development board", "开发板"), ("optocoupler", "光耦"),
    ("voltage reference", "基准源"), ("gate driver", "驱动芯片"),
    # 词干兜底放最后：描述里只有英文参数名时也能认出品类
    ("resist", "电阻"), ("capacit", "电容"), ("induct", "电感"),
    ("microcontroller", "单片机"), ("regulator", "稳压器"),
)

# 分类端点本身就说明了品类，直接采用（比从描述里猜更准）
_INTENT_CN = {
    "resistors": "贴片电阻",
    "capacitors": "电容",
    "microcontrollers": "单片机",
    "voltage_regulators": "稳压器",
}

# 只对这几个品类拼「值 + 封装 + 品类」的短名；其余用型号打头
_PASSIVE_CN = {"贴片电阻", "电阻", "陶瓷电容", "电容", "电解电容", "电感", "磁珠"}

# 关键参数名 → 直接当 value 用（详情接口同时给中英文参数名）
_VALUE_KEYS = (
    "阻值", "容值", "电感值", "电容值", "电阻值",
    "resistance", "capacitance", "inductance",
)

_PACKAGE_RE = re.compile(
    r"^(?:0[24]02|0[46]03|0805|1206|1210|2010|2512|"
    r"SOT-?23(?:-\d+)?|SOT-?89|SOT-?223|SOD-?123|SOD-?323|SMA|SMB|SMC|"
    r"TO-?220|TO-?92|TO-?252|DO-?214|DO-?41|"
    r"QFN-?\d*|DFN-?\d*|LQFP-?\d*|TQFP-?\d*|SOP-?\d*|SSOP-?\d*|"
    r"TSSOP-?\d*|MSOP-?\d*|DIP-?\d*|PLCC\d*|BGA-?\d*|HC-?49S?)$",
    re.IGNORECASE,
)
_RESISTANCE_RE = re.compile(
    r"^(?:\d+(?:\.\d+)?)\s*(?:[kKmMrR]\d*|Ω|ohm|R)$|^(?:\d+(?:\.\d+)?)\s*(?:[kKmM])?\s*(?:Ω|ohm)$",
    re.IGNORECASE,
)
_CAPACITANCE_RE = re.compile(r"^\d+(?:\.\d+)?\s*(?:p|n|u|µ|μ|m)?f$", re.IGNORECASE)
_MCU_PREFIX = ("stm32", "gd32", "esp32", "esp8266", "atmega", "attiny", "rp2040",
               "ch32", "nrf5", "n32", "hc32", "apm32", "mm32", "lpc", "pic1",
               "msp430", "stc8", "stc15", "efm32", "bl7")
_REGULATOR_HINT = ("ams1117", "lm317", "lm2596", "mp1584", "mp2307", "lm7805",
                   "78l05", "tps", "rt9013", "xc6206", "spx3819", "ldo",
                   "regulator", "me6211", "sy8089")
_LCSC_RE = re.compile(r"^[Cc]?(\d{4,9})$")
_VALUE_IN_DESC_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:pF|nF|uF|µF|μF|mF|[kKmM]?Ω|[kK]?[rR]\b))"
)


@dataclass
class Candidate:
    """一个候选元件（字段名对齐 ChipNest，另带网络侧信息供界面展示）。"""

    lcsc: str = ""
    mpn: str = ""
    package: str = ""
    description: str = ""
    manufacturer: str = ""
    category: str = ""
    value: str = ""
    stock: int = 0
    price: Optional[float] = None
    datasheet: str = ""
    source: str = ""
    params: dict[str, str] = field(default_factory=dict)
    score: float = 0.0

    @property
    def name(self) -> str:
        """建议的元件名：无源件「值 封装 品类」，其余「型号 品类」。"""
        if self.value and self.category in _PASSIVE_CN:
            parts = [self.value]
            if self.package and self.package != "-":
                parts.append(self.package)
            parts.append(self.category)
            return " ".join(parts)[:64]
        if self.mpn:
            return f"{self.mpn} {self.category}".strip()[:64]
        return (self.description or self.lcsc)[:64]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Candidate":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class LookupResult:
    """识别结果：最好的那条 + 全部候选 + 可直接填表的数据。"""

    query: str
    kind: str
    best: Optional[Candidate] = None
    candidates: list[Candidate] = field(default_factory=list)

    def fields(self) -> dict[str, str]:
        """映射成 Component 表单字段（长度按后端列宽截断）。"""
        c = self.best
        if c is None:
            return {}
        out: dict[str, str] = {"name": c.name}
        if c.value:
            out["value"] = c.value[:32]
        if c.package and c.package != "-":
            out["package"] = c.package[:32]
        if c.mpn:
            out["manufacturer_part"] = c.mpn[:64]
        if c.lcsc:
            out["supplier_part"] = c.lcsc[:40]
        return {k: v for k, v in out.items() if v}


def _category_cn(*texts: str) -> str:
    """从描述/分类里认出中文品类（认不出返回空）。"""
    for pattern, cn in _CATEGORY_CN:
        for text in texts:
            if pattern in (text or "").lower():
                return cn
    return ""


def _pick_value(candidate: dict, description: str = "") -> str:
    """取阻值/容值：参数表优先，其次从描述里抠。"""
    for item in candidate.get("paramVOList") or []:
        name = str(item.get("paramNameEn") or item.get("paramName") or "").lower()
        if any(key in name for key in _VALUE_KEYS):
            value = str(item.get("paramValue") or item.get("paramValueEn") or "").strip()
            if value and value != "-":
                return value[:32]
    raw = candidate.get("resistance") or candidate.get("capacitance_farads")
    if raw:
        return _format_si(float(raw), "Ω" if candidate.get("resistance") else "F")
    match = _VALUE_IN_DESC_RE.search(description or "")
    return match.group(1).strip()[:32] if match else ""


def _format_si(value: float, unit: str) -> str:
    """把 10000Ω / 1e-7F 这类原始值写成 10kΩ / 100nF。"""
    if value <= 0:
        return ""
    steps = ((1e9, "G"), (1e6, "M"), (1e3, "k")) if unit == "Ω" else (
        (1.0, ""), (1e-3, "m"), (1e-6, "u"), (1e-9, "n"), (1e-12, "p"))
    for factor, prefix in steps:
        if value >= factor:
            scaled = value / factor
            text = f"{scaled:.10g}"
            return f"{text}{prefix}{unit}"
    return f"{value:.10g}{unit}"


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_package(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text in ("-", "None") else text[:32]


def split_query(text: str) -> tuple[str, Optional[str]]:
    """把「10k 0603」拆成 (关键词, 封装)：封装单独拎出来喂给接口更准。"""
    tokens = [t for t in re.split(r"[\s,;/]+", (text or "").strip()) if t]
    package: Optional[str] = None
    rest: list[str] = []
    for token in tokens:
        if package is None and _PACKAGE_RE.match(token):
            package = token.upper()
        else:
            rest.append(token)
    return " ".join(rest) or (text or "").strip(), package


def detect_intent(text: str) -> Optional[str]:
    """猜品类，用来优先打更准的分类端点（电阻/电容/单片机/稳压器）。"""
    lowered = (text or "").strip().lower()
    if not lowered:
        return None
    if lowered.startswith(_MCU_PREFIX) or "microcontroller" in lowered:
        return "microcontrollers"
    if any(hint in lowered for hint in _REGULATOR_HINT):
        return "voltage_regulators"
    first = lowered.split()[0] if lowered.split() else lowered
    if _CAPACITANCE_RE.match(first) or _CAPACITANCE_RE.match(lowered):
        return "capacitors"
    if _RESISTANCE_RE.match(first) or _RESISTANCE_RE.match(lowered):
        return "resistors"
    return None


def extract_lcsc(text: str) -> Optional[str]:
    """从输入里认立创编号：C14663 或足够长的纯数字 14663。

    纯数字要小心：'10k 0603' 里的 0603 是封装不是编号，所以既排除封装形状、
    又要求至少 5 位（C8734 这种短号请带上 C 写）。
    """
    for token in re.split(r"[\s,;/]+", (text or "").strip()):
        match = _LCSC_RE.match(token)
        if not match:
            continue
        digits = match.group(1)
        if token[:1].lower() == "c":
            if len(digits) >= 3:
                return "C" + digits
            continue
        if len(digits) >= 5 and not _PACKAGE_RE.match(token):
            return "C" + digits
    return None


def score_of(candidate: Candidate, keyword: str, package: Optional[str]) -> float:
    """排序分：编号/型号精确命中优先，其次封装相符、常见料号、有库存。"""
    score = 0.0
    key = (keyword or "").strip().lower()
    if key:
        if candidate.lcsc.lower() == key or candidate.lcsc.lower().lstrip("c") == key:
            score += 200
        if candidate.mpn.lower() == key:
            score += 120
        elif key and key in candidate.mpn.lower():
            score += 50
        if candidate.value and candidate.value.lower() == key:
            score += 30
    if package:
        score += 60 if candidate.package.upper() == package.upper() else -40
    if candidate.stock > 0:
        score += 10
    if candidate.stock > 1000:
        score += 5
    if candidate.datasheet:
        score += 3
    if candidate.params:
        score += 3
    return score


class LookupService:
    """联网识别服务：外部可注入 AsyncClient（测试用 MockTransport）。"""

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        self._client = client
        # 本轮请求里网络失败的次数：用来区分「没这个料」与「网不通」
        self.failures = 0

    # ---------- 网络 ----------
    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=TIMEOUT, follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    async def _get_json(self, url: str, params: dict | None = None) -> Any:
        """取 JSON：任何异常都记日志并返回 None（上层继续降级）。"""
        try:
            if self._client is not None:
                resp = await self._client.get(url, params=params)
            else:
                async with self._new_client() as client:
                    resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning("联网识别 HTTP {}：{}", resp.status_code, url)
                self.failures += 1
                return None
            return resp.json()
        except Exception as exc:  # 网络不通/超时/返回不是 JSON 都算查不到
            logger.warning("联网识别失败 {}：{}", url, exc)
            self.failures += 1
            return None

    # ---------- 缓存 ----------
    async def _cache_get(self, session: AsyncSession, key: str,
                         ttl: dt.timedelta) -> Any | None:
        row = await session.get(LookupCache, key)
        if row is None:
            return None
        if utcnow() - row.created_at > ttl:
            return None
        row.hits = (row.hits or 0) + 1
        try:
            return json.loads(row.payload)
        except ValueError:
            return None

    async def _cache_put(self, session: AsyncSession, key: str, payload: Any) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        row = await session.get(LookupCache, key)
        if row is None:
            session.add(LookupCache(key=key, payload=text, created_at=utcnow()))
        else:
            row.payload = text
            row.created_at = utcnow()
        await session.commit()

    # ---------- 数据源 ----------
    async def _search_jlc_category(self, intent: str, keyword: str,
                                   package: Optional[str], limit: int) -> list[Candidate]:
        params: dict[str, Any] = {"search": keyword}
        if package:
            params["package"] = package
        data = await self._get_json(f"{JLC_BASE}/{intent}/list.json", params)
        if not isinstance(data, dict):
            return []
        rows = data.get(intent) or data.get("components") or []
        hint = _INTENT_CN.get(intent)
        return [self._from_jlc(row, source=f"jlcsearch/{intent}", hint=hint)
                for row in rows[:limit * 3]]

    async def _search_jlc_generic(self, keyword: str, package: Optional[str],
                                  limit: int) -> list[Candidate]:
        params = {"q": keyword, "limit": max(limit, 10), "full": "true"}
        if package:
            params["package"] = package
        data = await self._get_json(f"{JLC_BASE}/api/search", params)
        if not isinstance(data, dict):
            return []
        return [self._from_jlc(row, source="jlcsearch")
                for row in (data.get("components") or [])[:limit * 3]]

    async def _search_easyeda(self, keyword: str, limit: int) -> list[Candidate]:
        data = await self._get_json(EASYEDA_SEARCH, {
            "keyword": keyword, "type": 3, "page": 1, "pageSize": max(limit, 10),
        })
        if not isinstance(data, dict):
            return []
        products = ((data.get("result") or {}).get("productList")) or []
        out: list[Candidate] = []
        for row in products[:limit * 2]:
            price = None
            for ladder in row.get("price") or []:
                if isinstance(ladder, list) and len(ladder) >= 2:
                    price = _as_float(ladder[1])
                    break
            code = str(row.get("number") or "").strip()
            out.append(Candidate(
                lcsc=code if code.upper().startswith("C") else f"C{code}",
                mpn=str(row.get("mpn") or "")[:64],
                package=_clean_package(row.get("package")),
                description=str(row.get("description") or row.get("title") or "")[:200],
                manufacturer=str(row.get("manufacturer") or "")[:32],
                category=_category_cn(str(row.get("description") or ""),
                                      str(row.get("title") or "")),
                stock=_as_int(row.get("stock")),
                price=price,
                source="easyeda",
            ))
        return out

    def _from_jlc(self, row: dict, source: str, hint: str | None = None) -> Candidate:
        """jlcsearch 一行 → 候选（分类端点带 attributes/阻值，通用端点只有描述）。"""
        description = str(row.get("description") or "")
        attrs: dict[str, str] = {}
        raw_attrs = row.get("attributes")
        if isinstance(raw_attrs, str) and raw_attrs.strip():
            try:
                parsed = json.loads(raw_attrs)
                if isinstance(parsed, dict):
                    attrs = {str(k): str(v) for k, v in parsed.items()}
            except ValueError:
                attrs = {}
        code = row.get("lcsc")
        lcsc = f"C{code}" if str(code or "").isdigit() else str(code or "")
        value = _pick_value({"paramVOList": [
            {"paramNameEn": name, "paramValue": val} for name, val in attrs.items()
        ], "resistance": row.get("resistance"),
            "capacitance_farads": row.get("capacitance_farads")}, description)
        if not value:
            value = _pick_value({}, description)
        return Candidate(
            lcsc=lcsc,
            mpn=str(row.get("mfr") or "")[:64],
            package=_clean_package(row.get("package")),
            description=description[:200],
            category=hint or _category_cn(description, " ".join(attrs.keys())),
            value=value,
            stock=_as_int(row.get("stock")),
            price=_as_float(row.get("price") or row.get("price1")),
            source=source,
            params={k: v for k, v in list(attrs.items())[:8]},
        )

    def _from_lcsc_detail(self, row: dict) -> Candidate:
        params = {}
        for item in row.get("paramVOList") or []:
            name = str(item.get("paramName") or item.get("paramNameEn") or "").strip()
            value = str(item.get("paramValue") or item.get("paramValueEn") or "").strip()
            if name and value and value != "-":
                params[name] = value
        category = _category_cn(str(row.get("catalogName") or ""),
                                str(row.get("parentCatalogName") or ""),
                                str(row.get("productNameEn") or ""))
        return Candidate(
            lcsc=str(row.get("productCode") or ""),
            mpn=str(row.get("productModel") or "")[:64],
            package=_clean_package(row.get("encapStandard")),
            description=str(row.get("productNameEn")
                            or row.get("productKeyAttributes") or "")[:200],
            manufacturer=str(row.get("brandNameEn") or "")[:32],
            category=category,
            value=_pick_value(row, str(row.get("productNameEn") or "")),
            stock=_as_int(row.get("stockNumber")),
            datasheet=str(row.get("pdfUrl") or row.get("pdfLinkUrl") or "")[:200],
            source="lcsc",
            params=dict(list(params.items())[:10]),
        )

    # ---------- 对外方法 ----------
    async def search(self, session: AsyncSession, keyword: str,
                     package: Optional[str] = None, limit: int = 10) -> list[Candidate]:
        """关键词搜索：分类端点优先，通用端点兜底，EasyEDA 垫底。"""
        keyword = (keyword or "").strip()
        if not keyword:
            return []
        self.failures = 0
        package = _clean_package(package) or None
        key = f"search:{keyword.lower()}|{package or ''}|{limit}"
        cached = await self._cache_get(session, key, CACHE_SEARCH_TTL)
        if cached is not None:
            return [Candidate.from_dict(item) for item in cached]

        intent = detect_intent(keyword)
        found: list[Candidate] = []
        if intent:
            found = await self._search_jlc_category(intent, keyword, package, limit)
        if not found:
            found = await self._search_jlc_generic(keyword, package, limit)
        if not found:
            found = await self._search_easyeda(keyword, limit)

        found = self._rank(self._dedupe(found), keyword, package)[:limit]
        await self._cache_put(session, key, [c.to_dict() for c in found])
        return found

    async def detail(self, session: AsyncSession, lcsc_code: str) -> Optional[Candidate]:
        """按立创编号取详情（参数最全：阻值/容值、品牌、数据手册）。"""
        code = extract_lcsc(lcsc_code)
        if code is None:
            return None
        self.failures = 0
        key = f"detail:{code}"
        cached = await self._cache_get(session, key, CACHE_DETAIL_TTL)
        if cached is not None:
            return Candidate.from_dict(cached)

        best: Optional[Candidate] = None
        data = await self._get_json(LCSC_DETAIL, {"productCode": code})
        if isinstance(data, dict) and data.get("result"):
            best = self._from_lcsc_detail(data["result"])
        if best is None:
            rows = await self._search_jlc_generic(code, None, 3)
            exact = [c for c in rows if c.lcsc.upper() == code.upper()]
            best = (exact or rows or [None])[0]
        if best is None:
            rows = await self._search_easyeda(code, 3)
            exact = [c for c in rows if c.lcsc.upper() == code.upper()]
            best = (exact or rows or [None])[0]
        if best is None:
            return None

        best.lcsc = best.lcsc or code
        best.score = score_of(best, code, None)
        await self._cache_put(session, key, best.to_dict())
        return best

    async def autofill(self, session: AsyncSession, raw_input: str,
                       limit: int = 8) -> LookupResult:
        """核心入口：任意输入（10k 0603 / C14663 / STM32F103C8T6）→ 填好的元件信息。"""
        text = (raw_input or "").strip()
        if not text:
            return LookupResult(query=text, kind="keyword")
        self.failures = 0

        code = extract_lcsc(text)
        if code:
            best = await self.detail(session, code)
            return LookupResult(query=text, kind="lcsc", best=best,
                                candidates=[best] if best else [])

        keyword, package = split_query(text)
        candidates = await self.search(session, keyword, package=package, limit=limit)
        best = candidates[0] if candidates else None
        if best is not None and not best.datasheet and best.lcsc:
            # 通用搜索结果没有参数/数据手册：补一次详情（失败就算了，别拖慢识别）
            before = self.failures
            enriched = await self.detail(session, best.lcsc)
            self.failures = before + self.failures
            if enriched is not None:
                candidates = [enriched] + [c for c in candidates if c.lcsc != enriched.lcsc]
                best = enriched
        return LookupResult(query=text, kind="keyword", best=best, candidates=candidates)

    # ---------- 排序 ----------
    @staticmethod
    def _dedupe(items: Iterable[Candidate]) -> list[Candidate]:
        """同一条料（编号相同，或同型号同封装）只留一条，参数更全的优先。"""
        seen: dict[str, Candidate] = {}
        for item in items:
            key = item.lcsc or f"{item.mpn}|{item.package}"
            current = seen.get(key)
            if current is None:
                seen[key] = item
                continue
            if len(item.params) + len(item.description) > len(current.params) + len(current.description):
                seen[key] = item
        return list(seen.values())

    @staticmethod
    def _rank(items: list[Candidate], keyword: str, package: Optional[str]) -> list[Candidate]:
        for item in items:
            item.score = score_of(item, keyword, package)
        # 指定了封装就把其它封装的排到最后（不直接丢，方便用户改主意）
        return sorted(items, key=lambda c: c.score, reverse=True)


_service: Optional[LookupService] = None


def get_lookup_service() -> LookupService:
    """模块级单例（测试可用依赖覆盖替换成 MockTransport 版本）。"""
    global _service
    if _service is None:
        _service = LookupService()
    return _service
