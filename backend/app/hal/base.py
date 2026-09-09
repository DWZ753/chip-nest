"""HAL 适配器抽象层：状态枚举 + 基类。

串口 / 模拟 / 未来 WiFi 适配器都实现同一契约：
- start / stop 管理连接生命周期（可重入、可幂等）；
- send_led(index, r, g, b) 点亮灯带某颗灯（0..255）；
- state / device / error 属性 + on_change 回调，供 AdapterManager 切换。
"""

import abc
import enum
from typing import Awaitable, Callable, Optional


class AdapterState(enum.Enum):
    """适配器运行状态（透传给前端圆点与 WS）。"""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    FALLBACK = "fallback"


class BaseAdapter(abc.ABC):
    """所有硬件适配器的公共基类。

    on_change: 状态变化回调（协程函数），参数为适配器自身；
    由派生类在状态变化点调用（勿在回调里长时间 await）。
    """

    def __init__(self) -> None:
        self._state: AdapterState = AdapterState.CONNECTING
        self._device: Optional[str] = None
        self._error: Optional[str] = None
        # 由 AdapterManager 注入
        self.on_change: Optional[Callable[["BaseAdapter"], Awaitable[None]]] = None

    # ---------- 只读状态 ----------
    @property
    def state(self) -> AdapterState:
        return self._state

    @property
    def device(self) -> Optional[str]:
        return self._device

    @property
    def error(self) -> Optional[str]:
        return self._error

    async def _set_state(
        self,
        state: AdapterState,
        device: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """更新状态；真正变化时触发 on_change（异常不外抛）。"""
        changed = (
            state is not self._state or device != self._device or error != self._error
        )
        self._state = state
        if device is not None:
            self._device = device
        self._error = error
        if changed and self.on_change is not None:
            try:
                await self.on_change(self)
            except Exception:  # 订阅方失败不能拖垮适配器循环
                import logging
                logging.getLogger("chipnest.hal").exception("on_change 处理失败")

    # ---------- 生命周期与命令 ----------
    @abc.abstractmethod
    async def start(self) -> None:
        """启动连接流程（幂等，可多次调用）。"""

    @abc.abstractmethod
    async def stop(self) -> None:
        """停止并释放资源（幂等）。"""

    @abc.abstractmethod
    async def send_led(self, index: int, r: int, g: int, b: int) -> bool:
        """点亮 index 号灯；失败返回 False（不抛异常）。"""
