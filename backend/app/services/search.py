"""检索文本构建：写入时预计算，搜索时 LIKE 命中。

检索文本 = 名称+值+封装 小写拼接 + 名称汉字部分的拼音首字母
（如「贴片电阻」→ tpdz，名称里的 ASCII 如 "LED" 已含在原文中），
因此「dz」「led」「0603」「10k」都能命中对应卡片。
"""

import json
import re

from pypinyin import lazy_pinyin

from app.models import Component

# 汉字区间：首字母只对汉字计算，避免 pypinyin 吞掉/曲解 ASCII 片段
_HANZI = re.compile(r"[一-鿿]+")


def _name_initials(name: str) -> str:
    """只提取名称中汉字的拼音首字母。"""
    hanzi = "".join(_HANZI.findall(name or ""))
    return "".join(part[0] for part in lazy_pinyin(hanzi) if part)


def build_search_text(name: str, value: str = "", package: str = "",
                    mpn: str = "", tags: str = "") -> str:
    """预计算小写检索文本，供默认子串搜索使用。"""
    raw = f"{name}{value or ''}{package or ''}{mpn or ''}{tags or ''}".lower()
    return f"{raw} {_name_initials(name)}".strip()


def component_search_fields(component: Component) -> list[str]:
    """搜索选项启用时，保留每个字段的原始大小写和边界。"""
    try:
        tags = json.loads(component.tags or "[]")
    except (TypeError, ValueError):
        tags = []
    if not isinstance(tags, list):
        tags = []

    fields = [
        component.name, component.value, component.package,
        component.manufacturer_part, component.supplier_part,
        *(str(tag) for tag in tags), _name_initials(component.name),
    ]
    return [field for field in fields if field]


def compile_search_pattern(
    query: str, match_case: bool, whole_word: bool, use_regex: bool,
) -> re.Pattern[str]:
    """组合大小写、全字和正则选项，编译可作用于原始字段的模式。"""
    expression = query if use_regex else re.escape(query)
    if whole_word:
        expression = rf"(?<!\w)(?:{expression})(?!\w)"
    flags = 0 if match_case else re.IGNORECASE
    return re.compile(expression, flags)
