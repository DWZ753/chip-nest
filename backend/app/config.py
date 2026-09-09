"""运行配置：路径与端口均可由环境变量覆盖，便于 Electron 打包后重定向。"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

# PyInstaller 冻结检测：exe 运行时数据目录必须在可执行文件旁边（可写）
IS_FROZEN = bool(getattr(sys, "frozen", False))

ENV = os.getenv("CHIPNEST_ENV", "dev")  # dev | prod（决定是否输出控制台日志）
HOST = "127.0.0.1"
PORT = int(os.getenv("CHIPNEST_PORT", "8765"))

# 开发期 vite dev server 的跨域白名单
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def _runtime_root() -> Path:
    """运行根：开发=backend/；打包后=exe 所在目录（Electron 会用环境变量重定向）。"""
    if IS_FROZEN:
        return Path(sys.executable).resolve().parent
    return BACKEND_DIR


def _db_path() -> Path:
    path = Path(os.getenv("CHIPNEST_DB", _runtime_root() / "data" / "chipnest.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def db_url() -> str:
    """异步 SQLite 连接串（WAL 单文件，目录自动创建）。"""
    return f"sqlite+aiosqlite:///{_db_path().as_posix()}"


def sync_db_url() -> str:
    """同步 SQLite 连接串：仅供 alembic 迁移（可与异步引擎共存）。"""
    return f"sqlite:///{_db_path().as_posix()}"


def db_file() -> Path:
    """数据库文件本身（用于日志展示与外部检查）。"""
    raw = os.getenv("CHIPNEST_DB", _runtime_root() / "data" / "chipnest.db")
    return Path(raw)


def log_dir() -> Path:
    """按日期滚动的日志目录（Loguru）。"""
    path = Path(os.getenv("CHIPNEST_LOG_DIR", _runtime_root() / "logs"))
    path.mkdir(parents=True, exist_ok=True)
    return path