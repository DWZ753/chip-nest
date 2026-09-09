"""检索文本构建：写入时预计算，搜索时 LIKE 命中。

检索文本 = 名称+值+封装 小写拼接 + 名称汉字部分的拼音首字母
（如「贴片电阻」→ tpdz，名称里的 ASCII 如 "LED" 已含在原文中），
因此「dz」「led」「0603」「10k」都能命中对应卡片。
"""

import re

from pypinyin import lazy_pinyin

# 汉字区间：首字母只对汉字计算，避免 pypinyin 吞掉/曲解 ASCII 片段
_HANZI = re.compile(r"[一-鿿]+")


def build_search_text(name: str, value: str = "", package: str = "",
                    mpn: str = "", tags: str = "") -> str:
    """预计算某元件槽位的检索文本（厂商料号一并纳入，W25Q 等可直接搜）。"""
    raw = f"{name}{value or ''}{package or ''}{mpn or ''}{tags or ''}".lower()
    hanzi = "".join(_HANZI.findall(name or ""))
    initials = "".join(part[0] for part in lazy_pinyin(hanzi) if part)
    return f"{raw} {initials}".strip()