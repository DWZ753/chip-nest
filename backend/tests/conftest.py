"""测试基建：环境变量必须先于任何 app 模块导入设定（引擎绑定临时库）。"""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="chipnest_test_"))
os.environ["CHIPNEST_ENV"] = "test"
os.environ["CHIPNEST_DB"] = str(_TMP / "test.db")
os.environ["CHIPNEST_LOG_DIR"] = str(_TMP / "logs")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db import async_session, engine, get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, LayoutConfig  # noqa: E402

DEFAULT_LAYOUT = dict(zone_count=1, layer_count=3, row_count=1, col_count=4)


@pytest.fixture(autouse=True)
async def db():
    """每个用例重建全部表并种入默认布局。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        session.add(LayoutConfig(id=1, **DEFAULT_LAYOUT))
        await session.commit()
    yield


@pytest.fixture
async def client(db):
    """ASGI 内存客户端（跳过 lifespan，表由 db fixture 自建）。"""

    async def _session():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
