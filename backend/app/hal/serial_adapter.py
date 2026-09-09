"""SerialAdapter：扫描 COM 口并完成 PING/PONG 握手，点亮 ESP32 灯带。

协议与固件必须一致（见 HANDOFF §5）：
- 115200 8N1；PC→ESP `PING\n`，ESP→PC `PONG\n`，3 秒窗口内未收到即失败；
- 点灯命令 `LED:<index>,<R>,<G>,<B>\n`。

断开/异常自动进入重连循环（指数退避，上限 10s）；本机无硬件时由
AdapterManager 降级到 MockAdapter，本类仍会在后台继续重扫等待硬件上线。

扫描范围：默认只探测 USB 类串口（ESP32 开发板 = USB 转串芯片；蓝牙/其他
虚拟串口打开可能永久阻塞，必须跳过，否则服务启动会卡死）。如硬件出现在
非 USB 口，用环境变量 CHIPNEST_SERIAL_PORTS="COM3,COM8" 强制指定。
"""

import asyncio
import os
import threading
import time
from typing import Callable, Optional

from loguru import logger
from serial import Serial
from serial.tools import list_ports

from app.hal.base import AdapterState, BaseAdapter

# 协议常量（与 hardware/ 固件保持一致，勿单方面改动）
BAUDRATE = 115200
PING = b"PING\n"
PONG = b"PONG"
HEARTBEAT_SECONDS = 5.0      # 无数据多久后主动 PING 探活
RETRY_BASE = 1.0             # 重连退避起点（秒）
RETRY_MAX = 10.0


def _default_scanner():
    """枚举候选串口：默认仅 USB 类，CHIPNEST_SERIAL_PORTS 可强制名单。"""
    ports = list(list_ports.comports())
    forced = os.getenv("CHIPNEST_SERIAL_PORTS", "")
    if forced.strip():
        names = {s.strip().upper() for s in forced.split(",") if s.strip()}
        return [p for p in ports if (p.device or "").upper() in names]
    return [p for p in ports if _is_usb_port(p)]


def _is_usb_port(port) -> bool:
    """蓝牙/其他虚拟串口打开可能卡死，仅把 USB 描述口列为握手候选。"""
    hay = "{} {}".format(
        getattr(port, "hwid", "") or "",
        getattr(port, "description", "") or "",
    ).lower()
    return "usb" in hay
    """枚举系统串口（返回带 device 属性的对象列表）。"""
    return list_ports.comports()


class SerialAdapter(BaseAdapter):
    """真实串口灯带适配器。

    scanner/factory 可注入，便于测试用假串口替代真实硬件；
    默认值分别指向 pyserial 的端口枚举与 Serial 构造器。
    """

    def __init__(
        self,
        timeout: float = 3.0,
        *,
        scanner: Optional[Callable[[], list]] = None,
        factory: Optional[Callable[..., Serial]] = None,
    ) -> None:
        super().__init__()
        self._timeout = max(0.05, float(timeout))
        self._scanner = scanner or _default_scanner
        self._factory = factory or Serial
        self._conn: Optional[Serial] = None
        self._write_lock: Optional[asyncio.Lock] = None
        self._loop_task: Optional[asyncio.Task] = None
        self._stop_flag = threading.Event()   # 供阻塞线程读取
        # 探测线程防重入：某些串口 open() 可能永久阻塞（驱动/占用），
        # 上一轮没返回前不再开新线程，避免线程无限堆积
        self._probe_busy = False
        self._probe_event: Optional[asyncio.Event] = None

    # ---------- 探测 / 握手（同步阻塞，供 to_thread 调用） ----------
    def _probe(self) -> tuple[Optional[str], Optional[Serial]]:
        """扫描全部端口做一次握手，返回 (设备名, 已握手连接) 或 (None, None)。"""
        try:
            ports = list(self._scanner())
        except Exception as exc:
            logger.warning("串口枚举失败：{}", exc)
            return None, None

        slice_timeout = min(0.5, self._timeout)  # 每次 readline 最长阻塞
        deadline_keep = self._timeout
        for port in ports:
            if self._stop_flag.is_set():
                return None, None
            name = getattr(port, "device", None) or str(port)
            try:
                ser = self._factory(name, BAUDRATE, timeout=slice_timeout)
            except Exception:
                logger.debug("打开串口失败 {}（可能是占用/已拔出）", name)
                continue
            try:
                deadline = time.monotonic() + deadline_keep
                ser.write(PING)
                while time.monotonic() < deadline:
                    if self._stop_flag.is_set():
                        return None, None
                    line = ser.readline()
                    if PONG in line:
                        logger.info("串口握手成功：{}", name)
                        return name, ser
                logger.info("握手超时（3s 内无 PONG）：{}", name)
            except Exception as exc:
                logger.warning("与 {} 通信异常：{}", name, exc)
            finally:
                try:
                    ser.close()
                except Exception:
                    pass
        return None, None

    async def scan_once(self) -> bool:
        """跑一轮完整扫描握手；成功置 CONNECTED，失败保持 CONNECTING。

        探测跑在守护线程并设总预算：个别串口 open() 会永久阻塞（占用/
        驱动问题），wait_for 超时即放弃本轮，避免服务启动被卡死；遗留
        线程返回后 _probe_busy 自动复位，后台照常重试。
        """
        if self._probe_busy:
            return False  # 上一轮仍卡在系统调用里，跳过本轮
        self._probe_busy = True
        done = asyncio.Event()
        self._probe_event = done
        result_box: list = []
        loop = asyncio.get_running_loop()

        def worker() -> None:
            try:
                result_box.append(self._probe())
            except Exception:
                result_box.append((None, None))
            finally:
                self._probe_busy = False
                loop.call_soon_threadsafe(done.set)

        threading.Thread(target=worker, daemon=True,
                         name="chipnest-serial-probe").start()
        budget = max(6.0, self._timeout + 4.0)  # 总预算：超时即放弃本轮
        try:
            await asyncio.wait_for(done.wait(), timeout=budget)
        except asyncio.TimeoutError:
            logger.warning("串口探测超时（{}s），放弃本轮，后台继续重试", budget)
            return False

        if not result_box:
            return False
        result = result_box[0]
        name, conn = result
        if conn is None:
            await self._set_state(AdapterState.CONNECTING, error="未发现可用串口")
            return False
        self._conn = conn
        self._write_lock = asyncio.Lock()
        await self._set_state(AdapterState.CONNECTED, device=name, error=None)
        return True

    # ---------- 生命周期 ----------
    async def start(self, probe: bool = True) -> bool:
        """启动适配器。probe=True 先立即尝试一轮连接（供 Manager 决策）。

        无论 probe 结果如何都会进入后台重连循环，硬件随时插上都可接管。
        """
        self._stop_flag.clear()
        connected = False
        if probe:
            connected = await self.scan_once()
        self._loop_task = asyncio.create_task(self._monitor())
        return connected

    async def stop(self) -> None:
        """停止重连循环并关闭当前串口（幂等，可重复调用）。"""
        self._stop_flag.set()
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except (asyncio.CancelledError, Exception):
                pass
            self._loop_task = None
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                await asyncio.to_thread(conn.close)
            except Exception:
                pass
        await self._set_state(AdapterState.CONNECTING, error="适配器已停止")

    async def _monitor(self) -> None:
        """后台重连循环：无连接时扫描（带退避），有连接时值守探活。"""
        retry = RETRY_BASE
        while not self._stop_flag.is_set():
            if self._state is not AdapterState.CONNECTED:
                if not await self.scan_once():
                    await asyncio.sleep(retry)
                    retry = min(retry * 2, RETRY_MAX)
                    continue
            retry = RETRY_BASE
            await self._serve_connected()

    async def _serve_connected(self) -> None:
        """值守已连接串口：读行探测断线 + 周期 PING 探活。"""
        assert self._conn is not None
        ping_deadline: Optional[float] = None
        empty_streak = 0
        try:
            while not self._stop_flag.is_set() and self._state is AdapterState.CONNECTED:
                try:
                    line = await asyncio.to_thread(self._conn.readline)
                except Exception as exc:  # 串口被拔/驱动错误 → 转重连
                    logger.warning("串口值守异常：{}", exc)
                    break
                if not line:
                    empty_streak += 1
                    if empty_streak % 5 == 0:  # 空闲期主动探活（约 0.5s 间隔）
                        if ping_deadline is None:
                            try:
                                await asyncio.to_thread(self._conn.write, PING)
                            except Exception:
                                break
                            ping_deadline = time.monotonic() + self._timeout
                        elif time.monotonic() > ping_deadline:
                            logger.warning("PING 无响应，判定 {} 断线", self._device)
                            break
                    await asyncio.sleep(0.1)
                    continue
                empty_streak = 0
                if PONG in line:
                    ping_deadline = None
                await asyncio.sleep(0.02)  # 有流量也节流，避免空转
        finally:
            if self._state is AdapterState.CONNECTED:
                await self._set_state(AdapterState.CONNECTING,
                                      error="连接中断，等待重连")
            conn, self._conn = self._conn, None
            self._write_lock = None
            if conn is not None:
                try:
                    await asyncio.to_thread(conn.close)
                except Exception:
                    pass

    # ---------- 命令 ----------
    async def send_led(self, index: int, r: int, g: int, b: int) -> bool:
        """点亮 index 号灯；未连接或写失败返回 False。"""
        if self._state is not AdapterState.CONNECTED or self._conn is None:
            logger.debug("串口未连接，丢弃 LED:{} 指令", index)
            return False
        lock = self._write_lock or asyncio.Lock()
        async with lock:
            try:
                payload = f"LED:{index},{r},{g},{b}\n".encode()
                await asyncio.to_thread(self._conn.write, payload)
                return True
            except Exception as exc:
                logger.warning("LED 下发失败 idx={}: {}", index, exc)
                return False