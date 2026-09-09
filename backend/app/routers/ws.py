"""WebSocket 状态通道：/api/v1/ws/status。

连接建立即推送当前 HAL 状态快照；此后适配器状态变化（串口连上/掉线/
降级 Mock）实时广播 {"type":"adapter.status", mode, connected, device, error}。
每个连接挂独立有界队列，慢消费者丢最旧消息也不阻塞广播（UI 只认最新态）。
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.hal.manager import get_manager

router = APIRouter(prefix="/api/v1", tags=["system"])


class _StatusHub:
    """连接注册表：每个 WebSocket 一个发送队列。"""

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue] = set()

    def register(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._queues.add(queue)
        return queue

    def unregister(self, queue: asyncio.Queue) -> None:
        self._queues.discard(queue)

    async def broadcast(self, message: dict) -> None:
        for queue in list(self._queues):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # 慢消费者：丢最旧一条再放最新的
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    pass


_hub = _StatusHub()


async def _broadcast_status(status: dict) -> None:
    """HAL 状态变化 → 打包成 adapter.status 消息推给所有连接。"""
    await _hub.broadcast({"type": "adapter.status", **status})


# 注册订阅：manager 状态变化即广播（同一单例，lifespan 启动后才开始有变化）
get_manager().subscribe(_broadcast_status)


async def _drain(queue: asyncio.Queue, ws: WebSocket) -> None:
    """从队列取消息推给客户端（独立任务，避免与 receive 互相阻塞）。"""
    while True:
        message = await queue.get()
        await ws.send_json(message)


@router.websocket("/ws/status")
async def status_ws(ws: WebSocket) -> None:
    """WebSocket 端点：快照即发 + 增量广播。"""
    await ws.accept()
    queue = _hub.register()
    try:
        queue.put_nowait({"type": "adapter.status", **get_manager().status()})
    except asyncio.QueueFull:
        pass
    sender = asyncio.create_task(_drain(queue, ws))
    try:
        while True:
            await ws.receive_text()  # 只收心跳/关闭，不期待业务消息
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        _hub.unregister(queue)
