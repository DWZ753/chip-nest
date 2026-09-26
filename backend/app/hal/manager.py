"""AdapterManager：HAL 门面（单例，串口优先 + Mock 自动降级）。

启动时先给 SerialAdapter 一轮探测：握手成功 → serial 模式；任何失败
立即切 MockAdapter 保证服务零崩溃，串口仍在后台持续重连，硬件随时
插上都可自动接管（状态变化会通知订阅方，如 WS 广播）。

事件→LED 联动（订阅 services 层已发射的总线事件）：
- stock.changed  → 按库存规则：quantity < threshold 常亮红，充足熄灭；
- component.removed → 对应灯熄灭。
BOM 引导由 system 路由设置橙色高亮。
"""

from typing import Awaitable, Callable, Optional

from loguru import logger

from app import events
from app.hal.base import AdapterState, BaseAdapter
from app.hal.mock import MockAdapter
from app.hal.serial_adapter import SerialAdapter
from app.models import Component

# LED 语义色（HANDOFF §5：不足红 / 充足灭 / 引导橙）
RED = (255, 0, 0)
OFF = (0, 0, 0)
ORANGE = (255, 165, 0)

StatusHandler = Callable[[dict], Awaitable[None]]


class AdapterManager:
    """持有 serial + mock 两个适配器，对外只暴露当前激活者。"""

    def __init__(
        self,
        *,
        serial_adapter: Optional[SerialAdapter] = None,
        mock_adapter: Optional[MockAdapter] = None,
    ) -> None:
        self._serial = serial_adapter or SerialAdapter()
        self._mock = mock_adapter or MockAdapter()
        self._active: BaseAdapter = self._mock
        self._started = False
        self._events_bound = False
        self._subscribers: list[StatusHandler] = []
        self._guide_led_index: Optional[int] = None
        self._guide_base_color = OFF
        self._serial.on_change = self._on_serial_changed

    # ---------- 生命周期 ----------
    async def start(self) -> None:
        """启动 mock 与串口后台重连，按探测结果选定激活者。"""
        if self._started:
            return
        self._started = True
        if not self._events_bound:
            events.subscribe("stock.changed", self._on_stock_changed)
            events.subscribe("component.removed", self._on_component_removed)
            self._events_bound = True
        await self._mock.start()
        await self._serial.start(probe=True)  # 内部 _set_state 已回调本管理器
        self._active = (
            self._serial if self._serial.state is AdapterState.CONNECTED
            else self._mock
        )
        await self._notify()

    async def stop(self) -> None:
        """停止两个适配器并广播最终状态（幂等）。"""
        if not self._started:
            return
        self._started = False
        await self._serial.stop()
        await self._mock.stop()
        self._active = self._mock
        await self._notify()

    # ---------- 状态 ----------
    def status(self) -> dict:
        """对外状态快照：{mode, connected, device, error}。"""
        if not self._started:
            return {"mode": "mock", "connected": False, "device": None,
                    "error": "HAL 未启动"}
        if self._active is self._serial:
            return {
                "mode": "serial",
                "connected": self._serial.state is AdapterState.CONNECTED,
                "device": self._serial.device,
                "error": self._serial.error,
            }
        return {
            "mode": "mock",
            "connected": True,
            "device": self._mock.device,
            "error": self._mock.error,
        }

    def subscribe(self, handler: StatusHandler) -> None:
        """注册状态变化订阅（如 WS 广播）；不抛异常地逐个通知。"""
        if handler not in self._subscribers:
            self._subscribers.append(handler)

    async def _notify(self) -> None:
        for handler in list(self._subscribers):
            try:
                await handler(self.status())
            except Exception:
                logger.exception("HAL 状态订阅者处理失败")

    async def _on_serial_changed(self, adapter: BaseAdapter) -> None:
        """串口状态回调：连上即接管，掉线退回 Mock，随后广播。"""
        if adapter.state is AdapterState.CONNECTED:
            self._active = adapter
            logger.info("HAL 切到 serial 模式（{}）", adapter.device)
        elif self._active is adapter:
            self._active = self._mock
            logger.info("HAL 串口掉线，已降级 mock 模式，继续后台重连")
        await self._notify()

    # ---------- LED 下发 ----------
    async def set_guide_led(self, component: Optional[Component]) -> None:
        """高亮 BOM 当前步；切换或结束时恢复库存灯态。"""
        led_index = component.led_index if component is not None else None
        if led_index == self._guide_led_index:
            return

        if self._guide_led_index is not None:
            await self._send(self._guide_led_index, *self._guide_base_color)

        self._guide_led_index = None
        self._guide_base_color = OFF
        if component is None or led_index is None:
            return

        self._guide_led_index = led_index
        self._guide_base_color = self._stock_color(component)
        await self._send(led_index, *ORANGE)

    async def clear_leds(self, indexes) -> None:
        """批量熄灭灯位（清空数据用）：逐个下发 OFF，单个失败不影响其余。"""
        for index in sorted({int(i) for i in indexes if i is not None}):
            try:
                await self._send(index, *OFF)
            except Exception:
                logger.exception("熄灭灯位失败 index={}", index)

    async def _send(self, index: int, r: int, g: int, b: int) -> None:
        adapter = self._active
        if adapter is not None:
            await adapter.send_led(index, r, g, b)

    # ---------- events 总线订阅（勿改 services 层发射点） ----------
    async def _on_stock_changed(self, component) -> None:
        await self.sync_component_led(component)

    async def _on_component_removed(self, component) -> None:
        led_index = component.led_index
        if led_index is None:
            return
        if led_index == self._guide_led_index:
            self._guide_led_index = None
            self._guide_base_color = OFF
        await self._send(led_index, *OFF)

    async def _sync_led(self, component) -> None:
        """按库存规则点亮：低于阈值红，充足灭；无灯位跳过。"""
        if component.led_index is None:
            return
        color = self._stock_color(component)
        if component.led_index == self._guide_led_index:
            self._guide_base_color = color
            await self._send(component.led_index, *ORANGE)
            return
        await self._send(component.led_index, *color)

    async def sync_component_led(self, component) -> None:
        """同步单个元件的库存灯态；硬件错误不影响上层数据操作。"""
        try:
            await self._sync_led(component)
        except Exception:
            logger.exception("同步库存灯态失败 id={}", getattr(component, "id", None))

    @staticmethod
    def _stock_color(component) -> tuple[int, int, int]:
        """返回元件当前库存对应的灯色。"""
        if (component.quantity or 0) < (component.threshold or 0):
            return RED
        return OFF


_manager: Optional[AdapterManager] = None


def get_manager() -> AdapterManager:
    """模块级单例：lifespan / 路由 / WS 都拿同一实例。"""
    global _manager
    if _manager is None:
        _manager = AdapterManager()
    return _manager
