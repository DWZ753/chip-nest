"""异步数据库引擎与会话工厂（SQLite WAL + 外键开启）。"""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import config

engine = create_async_engine(config.db_url(), echo=False)


@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    """WAL 多读单写 + 外键 + 写锁等待，保证库存事务语义正确。"""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
    """FastAPI 依赖：每请求一个会话。"""
    async with async_session() as session:
        yield session

# ---------- 轻量增量迁移（PyInstaller 冻结态使用） ----------
# 冻结版不携带 alembic 脚本，无法用 alembic upgrade；对老版本安装包
# 留下的库做“查缺列 → ALTER ADD COLUMN”的幂等升级（与 alembic 0002 对齐）。
LEGACY_COLUMN_UPGRADES: dict[str, list[tuple[str, str]]] = {
    "components": [
        ("manufacturer_part", "VARCHAR(64)"),
        ("supplier_part", "VARCHAR(40)"),
        ("tags", "TEXT NOT NULL DEFAULT '[]'"),
        ("display_tags", "TEXT NOT NULL DEFAULT '[]'"),
    ],
    "layout_configs": [
        ("zone_names", "TEXT NOT NULL DEFAULT '[]'"),
        ("zone_sizes", "TEXT NOT NULL DEFAULT '[]'"),
    ],
}


def upgrade_legacy_columns(sync_conn) -> None:
    """把老版本库增量补齐新列（幂等，可反复执行）。

    sync_conn：同步连接的 SQLAlchemy Connection（供 run_sync 调用）。
    """
    for table, columns in LEGACY_COLUMN_UPGRADES.items():
        result = sync_conn.exec_driver_sql(f"PRAGMA table_info({table})")
        existing = {row[1] for row in result.fetchall()}
        for name, ddl in columns:
            if name not in existing:
                sync_conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"
                )