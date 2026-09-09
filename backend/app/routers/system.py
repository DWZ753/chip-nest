"""系统状态接口：HAL 模式与连接信息，供前端连接圆点渲染。"""

from fastapi import APIRouter

from app.hal.manager import get_manager

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/system/status")
async def system_status() -> dict:
    """返回 {mode: serial|mock, connected, device, error}。"""
    return get_manager().status()
