"""桌面版后端入口：PyInstaller 打成免 Python 的 chipnest-backend.exe。

以编程方式启动 uvicorn（不用 -m uvicorn，打包后没有模块参数概念）。
Electron 直接 spawn 本 exe 即可；端口/主机可用 CHIPNEST_PORT/CHIPNEST_HOST
覆盖，数据库与日志默认落在 exe 同级的 data/ logs/（Electron 会用
CHIPNEST_DB / CHIPNEST_LOG_DIR 重定向到 userData）。
"""

import os
import sys
import threading

try:  # Windows 控制台可能 GBK，日志输出前先统一 UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import uvicorn

# 触发 app 包完整导入（路由/事件/HAL 订阅注册都在 import 期完成）
from app.main import app  # noqa: E402


def watch_desktop_parent(server: uvicorn.Server) -> None:
    """@brief 桌面进程结束时停止服务，覆盖安装强制关闭的情况。"""
    parent_pid = os.getenv("CHIPNEST_PARENT_PID")

    if sys.platform != "win32" or not parent_pid:
        return

    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
                                  wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    # SYNCHRONIZE：只等待进程退出，不需要终止桌面进程的权限。
    parent = kernel.OpenProcess(0x00100000, False, int(parent_pid))

    if not parent:
        # 桌面进程可能在 PyInstaller 解包期间已退出。
        if ctypes.get_last_error() == 87:
            sys.exit(0)

        raise ctypes.WinError(ctypes.get_last_error())

    def wait_parent() -> None:
        """@brief 等待桌面进程退出并通知 uvicorn 正常停止。"""
        try:
            if kernel.WaitForSingleObject(parent, 0xFFFFFFFF) == 0:
                server.should_exit = True
        finally:
            kernel.CloseHandle(parent)

    threading.Thread(target=wait_parent, daemon=True).start()


def main() -> None:
    host = os.getenv("CHIPNEST_HOST", "127.0.0.1")
    port = int(os.getenv("CHIPNEST_PORT", "8765"))
    # log_config=None：日志交给 app.log 的 Loguru 接管，避免重复配置
    server = uvicorn.Server(
        uvicorn.Config(app, host=host, port=port, log_config=None),
    )

    watch_desktop_parent(server)

    server.run()


if __name__ == "__main__":
    main()
