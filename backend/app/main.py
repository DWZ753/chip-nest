"""ChipNest FastAPI 入口：启动即自动跑迁移并种入默认布局。"""

from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app import config, log
from app.hal.manager import get_manager
from app.db import async_session, engine, upgrade_legacy_columns
from app.models import Base, LayoutConfig
from app.routers import bom, components, layout, system, transactions, ws

import os as _os

log.init_logging()

# 默认货架布局：1 区 x 3 层 x 1 行 4 列（12 格）
DEFAULT_LAYOUT = dict(zone_count=1, layer_count=3, row_count=1, col_count=4)


async def _run_migrations() -> None:
    """自动建表：开发走 alembic；PyInstaller 冻结环境不携带迁移脚本，
    用同一套 metadata 直接 create_all（桌面单机库，语义一致）。"""
    if config.IS_FROZEN:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # 老版本安装包的库缺新列：PRAGMA 查缺 → ALTER 幂等补齐
            await conn.run_sync(upgrade_legacy_columns)
        return
    ini = config.BACKEND_DIR / "alembic.ini"
    command.upgrade(AlembicConfig(str(ini)), "head")


async def _ensure_default_layout() -> None:
    """layout 表空时种入默认布局（幂等）。"""
    async with async_session() as session:
        exists = await session.scalar(select(LayoutConfig.id).where(LayoutConfig.id == 1))
        if exists is None:
            session.add(LayoutConfig(id=1, **DEFAULT_LAYOUT))
            await session.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await _run_migrations()
    await _ensure_default_layout()
    await get_manager().start()
    yield
    await get_manager().stop()


app = FastAPI(title="ChipNest", version="0.3.7", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.DEV_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(layout.router)
app.include_router(components.router)
app.include_router(transactions.router)
app.include_router(bom.router)
app.include_router(system.router)
app.include_router(ws.router)


@app.get("/api/v1/health")
async def health() -> dict:
    """存活探针：Electron 主进程轮询此接口等待后端就绪；带版本供前端显示。"""
    return {"status": "ok", "service": "chipnest-backend", "version": app.version}

# M7 生产同源：前端构建产物存在时由 FastAPI 直接托管（SPA 兜底靠路由顺序：
# 所有 /api 与 /api/v1/ws 路由先注册，未命中才落到静态目录的 index.html）。
# Electron 打包态用 CHIPNEST_FRONTEND_DIST 指到 resources/frontend_dist。
def _frontend_dist():
    from pathlib import Path as _Path
    env = _os.getenv("CHIPNEST_FRONTEND_DIST")
    if env:
        cand = _Path(env)
        return cand if cand.is_dir() else None
    if config.IS_FROZEN:
        return None  # 独立 exe 不带前端，由 Electron 显式注入
    cand = config.BACKEND_DIR.parent / "frontend" / "dist"
    return cand if cand.is_dir() else None


_frontend = _frontend_dist()
if _frontend is not None:
    app.mount("/", StaticFiles(directory=str(_frontend), html=True),
              name="frontend")