"""Alembic 迁移环境：同步 SQLite 引擎，可同时被 CLI 与 FastAPI lifespan 调用。"""

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config

# 允许从任意工作目录启动（桌面端以 uvicorn -m 方式运行时 cwd 不可靠）
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import config  # noqa: E402
from app.models import Base  # noqa: E402

alembic_cfg = context.config
alembic_cfg.set_main_option("sqlalchemy.url", config.sync_db_url())
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL 不连库。"""
    context.configure(
        url=alembic_cfg.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata,
                      render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """同步引擎执行迁移：FastAPI lifespan 在事件循环内也能安全调用。"""
    connectable = engine_from_config(
        alembic_cfg.get_section(alembic_cfg.config_ini_section, {}),
        prefix="sqlalchemy.",
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
