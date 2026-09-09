# ChipNest · 智能元件管家

面向电子工程师的桌面元件仓库工具：用卡片网格管理你的元件库，支持模糊搜索、BOM 导入与引导取料，
可接 ESP32 + NeoPixel 灯带做槽位指示。Windows 安装包即装即用，无需 Python。

![界面预览](frontend/preview-tech-dark.png)

## 功能

- 元件库：卡片网格分区分层管理，空位点击即可新建；出入库、改料号、补货阈值、删除均带审计流水。
- 搜索：支持名称、阻值、封装、料号与拼音首字母模糊匹配，命中卡片呼吸高亮。
- 标签：每格可打标签，内部标签参与搜索；另可挑 1–3 个“展示标签”直接显示在格子上。
- BOM：粘贴文本或导入 .xlsx（常见 EDA/商城导出格式）→ 解析预览 → 匹配库存规划取料路线；
  或按“购买清单”逐行选格入库。
- 引导取料：按灯带顺序逐格高亮，每步自动原子出库并记账，缺料先提示补货。
- 批量操作：多选模式勾选多个格子后批量删除。
- 硬件联动：USB 串口连接 ESP32，槽位库存不足红灯、充足熄灭、引导取料高亮；无硬件时自动模拟模式。
- 界面：深色科技风主题（可切换浅色）、字号可整体缩放、毛玻璃卡片；仓库布局与应用设置分入口管理。

## 安装

### Windows

- 运行 `electron/release/ChipNest-Setup-<版本>.exe`，按向导安装；
  数据保存在 `%APPDATA%/ChipNest/`，升级安装不会丢失。
- 首次运行若提示 SmartScreen，选择“更多信息 → 仍要运行”（安装包暂未签名）。

### 源码运行

```bash
# 后端（Python 3.12+）
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8765

# 前端（另开终端，Node 20+）
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173

# 桌面壳（可选，自动拉起后端）
cd electron
npm install
npm start
```

> 升级界面缓存说明：新版本会自带清理 Web 缓存；如遇“界面没变化”，请先结束任务管理器里的
`ChipNest.exe` 再重新打开。

## ESP32 灯带联动（可选）

- 固件：`hardware/chipnest_led_server/chipnest_led_server.ino`（Arduino IDE + Adafruit NeoPixel 库）。
- 接线：灯带 DIN → 开发板引脚（固件顶部 `LED_PIN` 宏），GND 共地；数量多时独立 5V 供电。
- 协议：115200 8N1 行协议；握手 `PING`→`PONG`；点灯 `LED:<序号>,<R>,<G>,<B>`。
- 无 ESP32 时程序自动进入模拟模式（顶栏显示“模拟”），全部功能可正常体验。

## 使用提示

- 顶栏：搜索框、BOM 导入、仓库布局（网格/区名/手工入库/操作流水）、设置（外观/字号/硬件状态）。
- 点任意格子：编辑元件；点空位：新建。多选模式：右上角“☑ 多选”。
- BOM 弹窗支持 .xlsx / .csv / .txt；整表入库前每行可先改好再选格。

## 常见问题

1. **端口被占用 / 启动慢**：后端默认 127.0.0.1:8765；若同时有多个实例会互抢，先结束其他 ChipNest。
2. **连接不到串口**：只探测 USB 类串口（蓝牙虚拟串口可能阻塞），特殊口可设
   `CHIPNEST_SERIAL_PORTS=COM3,COM8` 指定。
3. **布局缩小后元件不见了**：网格上方会出现提示条，一键搬回空格。
4. **安装 electron 依赖慢**：国内网络设 `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/`。

## 开发与打包

- 后端测试：`backend` 目录执行 `./.venv/Scripts/python.exe -m pytest`。
- 前端构建：`cd frontend && npm run build`。
- 打包安装包：先按上文构建前端，再执行 `backend` 下 PyInstaller 命令（见
  `backend/run_desktop.py` 说明）与 `electron` 下 `npx electron-builder --win nsis`。
- 代码仓库：https://github.com/DWZ753/chip-nest（版本号见左上角与“设置 → 版本”）。

## 开源许可

本项目基于 MIT 许可证开源。
