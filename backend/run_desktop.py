"""桌面版后端入口：PyInstaller 打成免 Python 的 chipnest-backend.exe。

以编程方式启动 uvicorn（不用 -m uvicorn，打包后没有模块参数概念）。
Electron 直接 spawn 本 exe 即可；端口/主机可用 CHIPNEST_PORT/CHIPNEST_HOST
覆盖，数据库与日志默认落在 exe 同级的 data/ logs/（Electron 会用
CHIPNEST_DB / CHIPNEST_LOG_DIR 重定向到 userData）。
"""

import os
import sys

try:  # Windows 控制台可能 GBK，日志输出前先统一 UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import uvicorn

# 触发 app 包完整导入（路由/事件/HAL 订阅注册都在 import 期完成）
from app.main import app  # noqa: E402


def main() -> None:
    host = os.getenv("CHIPNEST_HOST", "127.0.0.1")
    port = int(os.getenv("CHIPNEST_PORT", "8765"))
    # log_config=None：日志交给 app.log 的 Loguru 接管，避免重复配置
    uvicorn.run(app, host=host, port=port, log_config=None)


if __name__ == "__main__":
    main()
