"""HAL 串口适配器测试：假串口 + 可控端口扫描，全程不碰真实硬件。

覆盖：PONG 握手成功 → connected 且能下发 LED 指令；静默端口握手超时
不误报连接；AdapterManager 串口失败自动降级 Mock；串口模式按库存语义
下发红/灭/引导橙指令。
"""

import asyncio
from types import SimpleNamespace

from app.hal.base import AdapterState
from app.hal.manager import AdapterManager
from app.hal.mock import MockAdapter
from app.hal.serial_adapter import SerialAdapter


class FakeSerial:
    """可编程假串口：首读可选回 PONG，之后模拟持续在线或静默。"""

    instances: list["FakeSerial"] = []

    def __init__(self, device, baudrate, timeout=None, *, pong=True,
                 alive=True):
        FakeSerial.instances.append(self)
        self.device = device
        self.baudrate = baudrate
        self.timeout = timeout
        self.written: list[bytes] = []
        self._pong = pong
        self._alive = alive
        self._reads = 0
        self.closed = False

    def write(self, data: bytes) -> None:
        self.written.append(data)

    def readline(self) -> bytes:
        self._reads += 1
        if self._reads == 1 and self._pong:
            return b"PONG\n"
        if self._alive:  # 持续在线：值守循环每次都收到心跳
            return b"PONG\n"
        return b""       # 静默：直到握手超时窗口结束

    def close(self) -> None:
        self.closed = True


def _make_scanner(pong: bool = True, alive: bool = True):
    """返回 (ports, factory)：单个假 COM 口的扫描器与连接工厂。"""
    ports = [SimpleNamespace(device="COM_TEST")]

    def factory(device, baudrate, timeout=None):
        return FakeSerial(device, baudrate, timeout=timeout,
                          pong=pong, alive=alive)

    return ports, factory


async def test_handshake_pong_connects_and_sends_led():
    ports, factory = _make_scanner()
    adapter = SerialAdapter(timeout=0.3, scanner=lambda: ports,
                            factory=factory)
    connected = asyncio.Event()

    async def _on_change(changed):
        if changed.state is AdapterState.CONNECTED:
            connected.set()

    adapter.on_change = _on_change
    try:
        assert await adapter.start(probe=True) is True
        assert adapter.state is AdapterState.CONNECTED
        assert adapter.device == "COM_TEST"
        await asyncio.wait_for(connected.wait(), 1)

        assert await adapter.send_led(3, 255, 165, 0) is True
        assert FakeSerial.instances[-1].written[-1] == b"LED:3,255,165,0\n"
    finally:
        await adapter.stop()
        await adapter.stop()  # stop 幂等


async def test_silent_port_times_out_without_false_connect():
    ports, factory = _make_scanner(pong=False, alive=False)
    adapter = SerialAdapter(timeout=0.15, scanner=lambda: ports,
                            factory=factory)
    ok = await adapter.start(probe=True)
    assert ok is False
    assert adapter.state is not AdapterState.CONNECTED
    assert adapter.error  # “未发现可用串口”类提示
    await adapter.stop()


async def test_manager_falls_back_to_mock_without_hardware():
    ports, factory = _make_scanner(pong=False, alive=False)
    serial_adapter = SerialAdapter(timeout=0.1, scanner=lambda: ports,
                                   factory=factory)
    mgr = AdapterManager(serial_adapter=serial_adapter,
                         mock_adapter=MockAdapter())
    await mgr.start()
    try:
        assert mgr.status() == {"mode": "mock", "connected": True,
                                "device": "mock", "error": None}
    finally:
        await mgr.stop()


async def test_manager_serial_mode_drives_leds_by_stock_rules():
    ports, factory = _make_scanner()
    serial_adapter = SerialAdapter(timeout=0.3, scanner=lambda: ports,
                                   factory=factory)
    mgr = AdapterManager(serial_adapter=serial_adapter,
                         mock_adapter=MockAdapter())
    await mgr.start()
    try:
        assert mgr.status()["mode"] == "serial"
        ser = FakeSerial.instances[-1]

        # 低于阈值 → 常亮红；补足后 → 熄灭；删除 → 熄灭；引导 → 橙
        await mgr._sync_led(SimpleNamespace(led_index=4, quantity=1,
                                            threshold=5))
        assert ser.written[-1] == b"LED:4,255,0,0\n"
        await mgr._sync_led(SimpleNamespace(led_index=4, quantity=9,
                                            threshold=5))
        assert ser.written[-1] == b"LED:4,0,0,0\n"
        await mgr._on_component_removed(SimpleNamespace(led_index=4))
        assert ser.written[-1] == b"LED:4,0,0,0\n"
        await mgr.set_guide_led(4)
        assert ser.written[-1] == b"LED:4,255,165,0\n"

        # 无灯位元件不产生任何串口写
        before = len(ser.written)
        await mgr._sync_led(SimpleNamespace(led_index=None, quantity=0,
                                            threshold=5))
        assert len(ser.written) == before
    finally:
        await mgr.stop()
