"""Loguru 日志接管：文件按日期滚动，并把 uvicorn 标准日志转发进来。"""

import logging
import sys

from loguru import logger

from app import config


class _InterceptHandler(logging.Handler):
    """把标准 logging 记录转发给 loguru。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        logger.log(level, record.getMessage())


def init_logging() -> None:
    """幂等：文件滚动日志 + （dev）控制台输出。"""
    logger.remove()
    logger.add(
        config.log_dir() / "chipnest_{time:YYYY-MM-DD}.log",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
        enqueue=True,
    )
    if config.ENV == "dev":
        logger.add(sys.stderr, level="INFO")

    # 接管 uvicorn 的日志输出（关闭传播防止父子 logger 各打印一次）
    for name in ("uvicorn", "uvicorn.error"):
        logger_obj = logging.getLogger(name)
        logger_obj.handlers = [_InterceptHandler()]
        logger_obj.propagate = False
    logging.getLogger("uvicorn.access").disabled = True  # access 日志过于嘈杂
