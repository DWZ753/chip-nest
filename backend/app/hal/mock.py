"""Mock 适配器：脱机演示 / 无 ESP32 时的自动降级目标。

所有动作只打 Loguru 日志，绝不触碰真实串口；state 恒为 FALLBACK，
device 固定 "mock"，服务因此零崩溃地运行完整业务流程。
"""

from loguru import logger

from app.hal.base import AdapterState, BaseAdapter


class MockAdapter(BaseAdapter):
    """模拟灯带：发送即记录，前端圆点显示「黄 = mock」。"""

    async def start(self) -> None:
        await self._set_state(AdapterState.FALLBACK, device="mock",
                              error=None)

    async def stop(self) -> None:
        await self._set_state(AdapterState.CONNECTING, device=None)

    async def send_led(self, index: int, r: int, g: int, b: int) -> bool:
        logger.info("mock LED  idx={} rgb=({},{},{})", index, r, g, b)
        return True
