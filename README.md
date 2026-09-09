# ChipNest · 智能元件管家（桌面版）

数字孪生元件管理工具：用网格卡片模拟 3D 打印元件架的俯视图，管理电阻/电容等
元件库存；支持拼音模糊搜索、BOM 文本导入后按灯带顺序「超市引导取料」；通过
USB 串口连接 ESP32 点亮对应槽位 LED；Electron 打包为双击即用的桌面程序。

## 功能一览

- **货架网格**：分区/层/行/列的抽屉格布局（默认 1 区 × 3 层 × 1 行 4 列 = 12 格），
  空位虚线占位、点击即可新建元件。
- **元件管理**：点卡片入/出/改/删；库存只走带事务审计的出入库接口，绝不直接改数量。
- **模糊检索**：名称 + 值 + 封装 + 汉字拼音首字母（大小写不敏感），命中卡片呼吸光晕上浮。
- **BOM 引导取料**：粘贴 BOM → 解析预览 → 库存匹配规划（同元件合并一步、0.1uF==100nF
  这类值自动换算）→ 按灯带顺序逐格高亮引导，每步自动原子出库并落审计；缺料先弹「请购买」。
- **格子标签**：给任意格子打自己的标签（如“主控”“常用”），与阻值/封装同排直接显示在卡片上，可搜索、可维护；无标称值的芯片类元件也能一眼认出来。
- **入口分工**：顶栏“仓库布局”管网格尺寸/区名/最近操作，内含“手工入库”（先逐行填好名称/料号/标签等物料信息，再选空格批量入库）；“设置”只管外观（深浅色/字号）与硬件状态。
- **控件与规范**：下拉选择用自绘玻璃面板（不再是浏览器原生样式）；项目提交信息一律中文（见 CLAUDE.md）。
- **BOM 文件导入**：直接选 .xlsx（常见 EDA/商城导出格式，自动识别 Name/Footprint/
  Quantity 表头并归一化 C0402→0402），.csv/.txt 按文本读入。
- **采购识别字段**：导入自动保留 **厂商料号**（对应表头 Manufacturer Part）与 **供应商料号**
  （Supplier Part），卡片与编辑框可见、可搜索（搜 W25Q/CL05 等料号即中）；非阻容感元件按
  型号指纹识别族名（芯片/晶振/二极管/MOS/开关/连接器…），原始型号永不改写。
- **区可命名**：设置里给每个区起名（如“LimeRC 遥控器”），网格标题与引导都显示区名；
  适合把仓库按工程临时分区（配合供应商料号对应具体项目）。
- **字号可调**：设置 → UI SCALE，小/默认/大/特大整体缩放；大网格格子保底 118px 宽并横向滚动，
  窄格自动隐藏次要信息防重叠。
- **整表入库（购买清单模式）**：把 BOM 当购买清单逐项入库——每行可改名称/值/封装/数量，
  独立选择空格位（默认顺序填空），一键建档并即时刷新货架。
- **ESP32 LED 联动**：串口 PING/PONG 握手；无硬件自动降级 Mock 模式（黄点），
  连上即切串口模式（绿点）；库存低于阈值常亮红、充足灭。
- **终端科技风 UI**：深色基座 + 霓虹青/紫高光、毛玻璃发光卡片、网格纹理、等宽终端标签
  （// ZONE 01 式），深浅双主题（默认深色，可手动切换并记忆）；参考 HM·S//CORE 视觉语汇。

## 目录结构

```
chip-nest/
├─ backend/                 FastAPI + SQLAlchemy 2 async + SQLite
│  ├─ app/
│  │  ├─ routers/           layout/components/transactions/bom/system/ws
│  │  ├─ services/          stock(防超卖原子扣减)/bom(解析规划)/search
│  │  ├─ hal/               硬件抽象层（serial/mock/wifi占位/manager）
│  │  ├─ main.py            入口：自动 alembic 建表 + 种默认布局 + HAL 启停
│  │  └─ …
│  ├─ alembic/              数据库迁移
│  ├─ scripts/e2e_smoke.py  整链冒烟（幂等）
│  └─ tests/                pytest（18 项，含并发防超卖）
├─ frontend/                Vue3 + Vite + Pinia + Tailwind v4 + Headless UI
├─ electron/                桌面壳：内置拉起后端、单实例、无黑框
├─ hardware/chipnest_led_server/  ESP32 Arduino 灯带固件
└─ HANDOFF.md               交接/决策文档（改接口前先读）
```

## 环境准备

- Python **3.14+**（后端）
- Node **24+**（前端 + Electron）
- 可选：ESP32 开发板 + NeoPixel 灯带（Arduino IDE 装 Adafruit NeoPixel 库）

### 后端

```bash
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8765   # 默认 127.0.0.1:8765
```

验证：

```bash
./.venv/Scripts/python.exe -m pytest            # 18 项全绿
./.venv/Scripts/python.exe scripts/e2e_smoke.py # 对运行中的服务整链冒烟
```

### 前端

```bash
cd frontend
npm install
npm run dev      # http://127.0.0.1:5173（/api 与 WS 自动代理到 8765）
npm run build    # 产物 dist/；后端检测到 dist 后也会直接托管（生产同源）
```

### Electron 桌面壳

```bash
cd electron
# 国内网络请先设置镜像再装（二进制来自 GitHub）
export ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
npm install
npm start        # 自动拉起后端（无黑框）→ 就绪开窗 → 关闭时杀干净后端
CHIPNEST_DEV=1 npm start   # 开发模式：窗口指向 vite dev server
```

> 说明：开发态 Electron 壳自带 Python 后端进程（优先 `backend/.venv/Scripts/python.exe`）；
> 打包态（`app.isPackaged`）自动改为直接运行 `resources/backend/chipnest-backend.exe`
> （免 Python，见下「打包」一节）。

## ESP32 接线与协议

- 固件：`hardware/chipnest_led_server/chipnest_led_server.ino`（改顶部 `LED_PIN`/`NUMPIXELS` 后烧录）
- 接线：NeoPixel DIN → 板子引脚，GND 共地；5V 由外部电源或板载 5V（数量少时）供电
- 协议（115200 8N1，行协议）：

```
PC→ESP  PING                     ESP→PC  PONG        （3 秒窗口握手）
PC→ESP  LED:<idx>,<R>,<G>,<B>    例：LED:25,255,165,0（橙色）
```

- 无 ESP32 时后端自动降级 **Mock 模式**（状态黄点，全部流程照常跑通演示）。

## 常见问题

1. **启动卡在 “Waiting for application startup”**：Windows 蓝牙虚拟串口（如
   “蓝牙链接上的标准串行”）打开可能永久阻塞。默认只探测 USB 类串口；若硬件在
   非 USB 口，用 `CHIPNEST_SERIAL_PORTS=COM3,COM8` 强制指定再启动。
2. **npm install electron 很慢/失败**：GitHub 不通时走国内镜像：
   `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/`（改 npm 配置可永久生效）。
3. **前端 409/报错看不懂**：后端错误统一为中文 message，出库不足还会附
   `available`（剩余量），界面会直接提示补货。
4. **布局缩小后元件不见了**：它们在“游离区”——网格上方横幅会提示，可一键自动搬入空格。

## 打包（2026-09-08 已实跑出包；当前版本 v0.3.7）

> 版本与仓库：代码托管在 https://github.com/DWZ753/chip-nest（main 分支，发版打 tag）；
> 界面左上角与「设置 → 版本」会显示当前版本号，用于确认安装是否生效。

> v0.3.1 修复：老版本安装包数据库升级——冻结版启动时自动 PRAGMA 查缺列并
> ALTER 补齐（manufacturer_part/supplier_part/zone_names），老元件无损保留，无需删库重来。

已产出两个可分发产物：

- `backend/dist/chipnest-backend.exe` —— PyInstaller onefile **免 Python 后端**（约 25MB）
- `electron/release/ChipNest-Setup-0.3.7.exe` —— **NSIS 安装包**（约 137MB，
  已实测：打包版自起后端 exe、页面加载成功、退出后端口清理正常）
- `electron/release/win-unpacked/` —— 免安装绿色版（可选分发）

重建命令：

```bash
# 1) 后端 exe（backend/.venv 先 pip install pyinstaller）
cd backend
./.venv/Scripts/pyinstaller.exe --noconfirm --onefile --name chipnest-backend \
  --collect-all pypinyin --collect-submodules uvicorn \
  --hidden-import aiosqlite --hidden-import greenlet --hidden-import websockets \
  run_desktop.py

# 2) 桌面壳安装包（国内网络务必先设镜像）
export ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
export ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/
cd electron
npx electron-builder --win nsis    # 产出 release/ChipNest-Setup-<version>.exe
```

打包版结构：Electron 壳（resources/frontend_dist 静态前端 +
resources/backend/chipnest-backend.exe）→ 免 Python 后端自起于 127.0.0.1:8765
并托管前端；数据库与日志写到 `%APPDATA%/chipnest-electron/`（打包后 Program Files
不可写，已自动重定向）。
当前安装包**未做代码签名**（本机无证书），SmartScreen 首次运行可能提示
“更多信息 → 仍要运行”。
## 验收目测清单（UI 最终裁判是你）

- [ ] 深浅主题自动跟随系统，右上角按钮可手动切换且刷新后记住
- [ ] 卡片网格毛玻璃质感、hover 上浮、仅 hover 显示库存数字、底部色带随库存变色
- [ ] 搜索 “dz / 0603 / led” 命中卡片呼吸光晕 + 上浮
- [ ] 点卡片可入库/出库/改/删；点空位可新建；填 10k / 100nF / 22Ω 有排版感
- [ ] BOM 粘贴 → 解析预览表 → 规划出步骤与缺料清单 → 引导巨幕 1/N，逐格取料自动扣减
- [ ] 无 ESP32 时右下圆点黄（MOCK）；插上烧录固件的 ESP32 后变绿（SERIAL）
- [ ] 布局改大改小即时重排；缩容后游离元件横幅出现，可一键搬入