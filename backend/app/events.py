"""进程内事件总线：库存变化/取料目标等事件在 commit 后广播。

订阅者（LED 联动、WS 推送）在各自模块导入时注册；
广播一律异步派发且吞掉异常，绝不反向影响请求主流程。
"""

import asyncio
from collections import defaultdict
from typing import Any, Awaitable, Callable

from loguru import logger

Handler = Callable[..., Awaitable[None]]
_handlers: dict[str, list[Handler]] = defaultdict(list)


def subscribe(event: str, handler: Handler) -> None:
    _handlers[event].append(handler)


def emit(event: str, *args: Any) -> None:
    """派发事件（不等待处理器完成）。"""
    for handler in _handlers.get(event, ()):
        asyncio.create_task(_safe_dispatch(event, handler, args))


async def _safe_dispatch(event: str, handler: Handler, args: tuple) -> None:
    try:
        await handler(*args)
    except Exception:  # 广播失败绝不能影响主流程
        logger.exception("事件处理失败 event=%s", event)
