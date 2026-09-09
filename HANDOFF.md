# ChipNest 交接文档（给接手 AI 的完整提示词）

> 本文档写给**另一个 AI 实例**接手续做本桌面应用。请把它当作唯一的背景来源，与
> `e:\esp32\chip-nest\` 下的真实代码互为对照。**先读代码再动手，不要凭本文重写已实现的部分。**
> 状态：M1–M7 + 打包全部完成（2026-09-08），剩余为人工目测/真机联调/签名发布。

---

## 0. 你要接手的项目一句话

**ChipNest（智能元件管家）桌面版**：数字孪生元件管理工具。用网格卡片模拟 3D 打印元件架的俯视图，
管理电阻电容等元件的库存；支持拼音模糊搜索、BOM 文本导入后按灯带顺序「超市引导取料」；
通过 USB 串口连接 ESP32 点亮对应槽位 LED；Electron 打包成双击即用的桌面程序。
用户是电子工程方向学生，要求 UI 像 Figma/Notion 一样精致（毛玻璃卡片、呼吸动画、深浅主题），**绝不能像老旧 MIS 系统**。

## 1. 已拍板的技术决策（用户已确认，不要改）

| 事项 | 决定 |
|---|---|
| 数据库 | **SQLite (aiosqlite)**，WAL + busy_timeout；单文件 `backend/data/chipnest.db`（打包态默认 exe 旁 data/，Electron 重定向到 userData） |
| 防超卖 | **事务内条件原子扣减** `UPDATE ... SET quantity=quantity-n WHERE quantity>=n`；代码保留 `.with_for_update()`（SQLite 静默忽略，未来切 Postgres 自动成真锁） |
| 硬件 | **SerialAdapter 为主**（扫描 COM 口 + PING/PONG 3s 握手，失败自动降级 MockAdapter 持续重连）；`WifiAdapter` 仅抽象占位（NotImplemented） |
| BOM 引导 | 点击「已取走/下一个」时**每步自动出库扣减**（受事务保护 + 审计），绝不只指路不扣库存 |
| 附带 | `hardware/` ESP32 Arduino 固件示例（可真实联调握手与灯） |
| 交付 | 后端 FastAPI + SQLAlchemy 2 async + Pydantic v2 + Loguru；前端 Vue3(Composition+TS) + Vite + Tailwind v4 + Headless UI + Pinia；壳 Electron + PyInstaller 后端 exe |

## 2. 环境（本机 Windows 11，已全部验证可用）

- Python **3.14.5**（`backend/.venv` 已建好并装完 requirements-dev.txt，全部包导入通过）
  - fastapi 0.141 / sqlalchemy 2.0.52 / pydantic 2.13.5 / alembic 1.19.2 / pypinyin / pyserial / pyinstaller 6.22 / openpyxl / python-multipart 等
- Node **v24** + npm 11（frontend 已 npm install、`npm run build` 通过；electron 已装并实跑冒烟）
- 无 uv；git bash 可用；本机 COM3-6 为蓝牙虚拟串口（见 §6.8），COM8 是 USB 串口但未烧固件
- **国内网络装 electron 必须设镜像**：`ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/`；
  electron-builder 再补 `ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/`
- **后端开发服务器启动方式**（默认端口 8765）：
  ```bash
  cd backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8765
  ```
- 后端测试：`cd backend && ./.venv/Scripts/python.exe -m pytest`（当前 18 项全绿）
- 冒烟脚本（对运行中的服务做整链验证，幂等）：`./.venv/Scripts/python.exe scripts/e2e_smoke.py`

## 3. 已完成并验证的部分（M1–M7 ✅ + 打包 ✅ —— 不要重做）

### 目录结构（现存文件）
```
chip-nest/
├─ backend/
│  ├─ alembic.ini, alembic/{env.py, script.py.mako, versions/0001_initial.py}
│  ├─ app/
│  │  ├─ main.py        # 入口；lifespan 迁移/种布局/HAL 启停；frozen 态 create_all；dist 静态托管
│  │  ├─ config.py      # 环境变量 + IS_FROZEN/_runtime_root（PyInstaller 感知）
│  │  ├─ log.py db.py models.py schemas.py events.py
│  │  ├─ routers/       # layout / components / transactions / bom / system / ws
│  │  ├─ hal/           # base mock serial_adapter wifi_adapter(占位) manager
│  │  └─ services/      # search stock bom
│  ├─ run_desktop.py    # PyInstaller 入口（编程式 uvicorn）
│  ├─ scripts/e2e_smoke.py
│  ├─ dist/chipnest-backend.exe   # 打包产物（约 25MB，免 Python）
│  └─ tests/            # 18 项：crud/search/stock 并发/bom/serial
├─ frontend/            # Vite8+Vue3.5(TS)+Pinia4+Tailwind4+HeadlessUI+@lucide/vue
├─ electron/            # main.js(开发=venv python / 打包=resources 后端 exe) + release/ 安装包
├─ hardware/chipnest_led_server/chipnest_led_server.ino
├─ README.md            # 中文：安装/启动/协议/打包/目测清单
└─ HANDOFF.md
```

### M1 验证结果
- lifespan 内程序化迁移建表 + 种默认布局「1 区 x 3 层 x 1 行 4 列」（12 格），health/layout API 通。

### M2 验证结果
- 6 项 pytest 全绿：CRUD 全流程 + 槽位唯一 409 + 越界 400 + 修改不留痕、**并发双扣 10/库存15 → 恰好一个成功且终值 5 不为负**、恰好扣到 0 允许、检索矩阵（0603 / 10k / dz / DZ / led / zsd / 汉字）。
- `scripts/e2e_smoke.py` 对真实服务全链通过。开发库 `backend/data/chipnest.db` 留有两件冒烟元件（10k电阻/100nF电容），可作界面演示或随意删。

### M3 验证结果（BOM 解析/规划/取料 ✅）
- `app/services/bom.py` 纯函数：`parse_text`（[,，;；\n]+ 拆行；先剥数量 x/×/*/个/只/pcs 再认值/封装，
  无空格「10k电阻x20」可解析）、`normalize_value`（前缀 p/n/u/m/k/M/G + 后缀 F/R/欧/Ω/ohm/H，空后缀默认电阻族，
  相对容差 1e-9）、`plan_pure`（封装 10 + 值等价 8 + 名称包含 6；**封装不一致或值可归一化却不相等 → 硬剔除**，11k 不误配 10k）。
- 同元件多行合并为一步取总量；足料进 steps（led_index 升序、None 最后）；不足合并一条 shortage（含 available），找不到每行 not_found。
- `routers/bom.py` 三个接口；`/bom/pick` 复用 `stock.change_stock`（source=guide → kind=bom_pick）。
- `tests/test_bom_parser.py` 8 项；pytest 14 项全绿；e2e 含 bom 链路。契约见 §5「BOM 契约」。

### M4 验证结果（HAL 硬件抽象层 ✅）
- `app/hal/`：base.py(AdapterState connecting/connected/fallback + BaseAdapter state/device/error/on_change)；
  mock.py(state=fallback 全日志)；serial_adapter.py（115200 PING/PONG 3s、LED:<idx>,<R>,<G>,<B>、心跳探活、
  指数退避 1..10s 重连）；wifi_adapter.py 占位 NotImplementedError；manager.py 单例（串口优先、失败降级 Mock 不崩、
  订阅 stock.changed/component.removed → LED 红/灭，set_guide_led 橙预留）。
- `routers/system.py` GET /system/status；`routers/ws.py` WS /api/v1/ws/status（快照+广播，每连接有界队列）。
- 4 项假串口测试；pytest 18 项全绿；e2e 增加 /system/status=mock 通过。踩坑 §6.8。

### M5 验证结果（前端骨架 + 设计系统 ✅）
- frontend/：Vite ^8 + Vue 3.5(TS) + Pinia 4 + Tailwind v4（@tailwindcss/vite）+ @headlessui/vue 1.7 + **@lucide/vue**（lucide-vue-next 已弃用）；无 vue-router（单页对话框式）。
- style.css 承载设计系统：莫兰迪 CSS 变量（明/暗）、.glass 毛玻璃、.dark class（html 内联脚本防闪烁 + localStorage `chipnest-theme`）、呼吸/脉冲/步进等关键帧。
- TopBar（Logo/巨圆搜索/BOM/设置/主题/ConnectionDot），ConnectionDot 走 WS（绿 serial/黄 mock/红断开）；数据层 src/api/{client,ws,types}.ts。
- 验证：`npm run build`（vue-tsc + vite）零错误；后端+vite 起来后 headless Chrome dump-dom 确认真实渲染（品牌/搜索/MOCK 点/元件卡）。

### M6 验证结果（核心视图与动效 ✅）
- GridView 分区为组、层内 row×col 网格、空位虚线卡点击新建；BinCard hover 才显数量、底部 3px 色带（绿/黄/红）、hover 上浮。
- 搜索命中呼吸光晕+上浮 1.6s（store flashKeys 定时摘 class）；guide-now 橙色脉冲描边当前格。
- EditDialog 新建/编辑复用（入/出/改/删/搬家三字段成组/两步删除）；BomDialog（parse 表格 → plan；missing 置顶请购买）；
  GuideOverlay（半透明巨幕步数、每步 pick 原子扣、409 中断补货提示、完成态）；SettingsDialog（布局保存重排/最近流水/硬件状态）；
  游离元件横幅一键搬入空格。WS adapter 状态联动圆点。
- 验证：build 通过；Electron 冒烟日志见 WebSocket /api/v1/ws/status accepted；动画质感最终由用户目测（README 清单）。

### M7 验证结果（Electron 壳 + 固件 + 打包 ✅）
- main.py：FRONTEND_DIST（env CHIPNEST_FRONTEND_DIST / 仓库 frontend/dist）存在即挂载静态，/api 路由先注册保证优先。
- electron/main.js：单实例锁；python 探测（venv→python→py）；windowsHide 无黑框；stdio → logs/electron_backend.*.log；
  health 轮询 30s；CHIPNEST_DB/CHIPNEST_LOG_DIR → userData；before-quit taskkill /T /F；CHIPNEST_SMOKE=1 自检模式。
  打包分支：app.isPackaged → spawn resources/backend/chipnest-backend.exe + CHIPNEST_FRONTEND_DIST=resources/frontend_dist。
- hardware/chipnest_led_server/chipnest_led_server.ino：115200 行协议 PING→PONG、LED:<idx>,<R>,<G>,<B>（越界丢弃、0..255 约束）。
- 验证：node --check 通过；electron 二进制走 npmmirror 下载；CHIPNEST_SMOKE=1 实跑成功（后端自起→页面加载→退出后 8765 释放、userData 生成 chipnest.db+logs）。

### 打包验证结果（2026-09-08 追加完成）
- config：IS_FROZEN/_runtime_root；main.py 冻结态用 metadata create_all（不依赖 alembic 目录）；新增 run_desktop.py 编程式 uvicorn 入口。
- PyInstaller onefile → backend/dist/chipnest-backend.exe（约 25MB；--collect-all pypinyin + --collect-submodules uvicorn +
  --hidden-import aiosqlite/greenlet/websockets）。独立运行实测：health、中文建档、拼音检索 dz、0603、bom/plan、system/status 全通。
- electron-builder：extraResources 收 backend/chipnest-backend.exe 与 frontend_dist（frontend/dist）；--win --dir 的 win-unpacked
  以 CHIPNEST_SMOKE=1 实测通过（免 Python 后端自起、页面加载成功、退出清理）；--win nsis 出 electron/release/ChipNest-Setup-0.3.9.exe（约 130MB）。
- 注意：安装包**未代码签名**（SmartScreen 提示属预期）；nsis 为交互式向导（oneClick:false，无人值守 /S 不适用，需人工下一步）。

### V0.3.0 迭代（专业性与可用性 ✅，同日完成）
- **Manufacturer Part / Supplier Part 落库**：alembic 0002 给 components 加
  manufacturer_part(≤64)/supplier_part(≤40)；Excel 表头新增别名（manufacturer part/mpn/料号、
  supplier part/lcsc/立创编号），导入行随行保留；EditDialog/购买清单行可编辑带出；
  BinCard 显示 MPN 小字；检索文本纳入料号（q=CL05 或 104KB 都能命中）。migration 0002。
- **区可自定义名称**：layout_configs.zone_names（Text JSON）；Layout API 出入都带
  zone_names（≤9 项、每项≤24 字符，空=第N区）；Settings 逐区命名；GridView/GuideOverlay
  显示区名。前端 zoneName(layout, zone) 工具。
- **字号可调 + 大网格防挤压**：设置 UI SCALE（0.9/1/1.15/1.3，body zoom + --ui-zoom 持久化）；
  网格列 minmax(118px,1fr)+横向滚动；BinCard container query 窄格隐藏 MPN/LED/收紧内边距。
- **非阻容感识别增强**：值归一化只认阻容感；新增型号指纹 _KIND_PATTERNS 兜底中文族名
  （芯片/存储/电源模拟/二极管/三极管MOS/晶振/开关/连接器/保险丝/LED/蜂鸣器），
  只用于展示，不改写原始 Name；Footprint 只认四位（防 LQFP-100 污染）。
- 验证：pytest 20 项全绿；e2e 冒烟通过；真机接口实测 PUT zone_names、MPN 建档与
  q=CL05/104KB 检索全通；vue-tsc + vite build 零错误；DOM 冒烟显示区名与 MPN；
  win-unpacked CHIPNEST_SMOKE=1 页面加载成功。产物 v0.3.0。

### V0.3.9 展示标签内联可见 + 文案规范 + 表格同滚 + 多选细节 ✅
- 外部标签不再单独一行：直接跟在元件名后面内联显示（#标签 胶囊，最多 2 个 +N），
  任何格子宽度都压缩显示而不隐藏（此前窄格隐藏规则导致“外部标签不可见”）。
- 编辑文案规范化：字段名“标签 / 展示标签”，去掉“（内部，用于搜索）”“挑 1–3 个”等注释腔。
- 手工入库：表头与数据行放进同一横向滚动容器（统一滚动），列宽常量压缩到不溢出。
- 多选时隐藏悬停数量与灯号胶囊，勾号移到右下角，不再与卡片内容重叠。
- 运行验证：API 打展示标签后 DOM 确认格子上出现 #主控。产物 v0.3.9 冒烟通过。
### V0.3.8 外部可见标签 + 手工入库对齐 + 货架多选 ✅
- components.display_tags（≤3，JSON）：alembic 0004 + 冻结增量列；schemas/stock/路由全链路；
  编辑元件时从内部 tags 里挑 1–3 个“显示在格子上的”，卡片以渐变紫胶囊显示在名称下方。
- 手工入库：表头与输入行共用 GRID_COLS 常量严格对齐。
- 货架批量：网格右上“多选”→ 点卡勾选（发光+对勾角标）→ 删除所选（两步确认）/退出多选。
- 验证：pytest 23 项；打包版冒烟 exit=0 probe=[200,200,200,'0.3.8'] ui-marker=true；
  真实用户库自动补 display_tags 列且 42 件保留。
### V0.3.7 修三处体验问题 ✅
- NiceSelect 双箭头：按钮不再复用带 CSS 背景箭头的 .select 类，只留单个图标（原生背景与自绘图标叠加所致）。
- 标签：窄格（≥15 列）时曾隐藏标签导致看不到 → 仅超窄（≤118px）隐藏；编辑改为 Steam/B站式
  TagEditor（chip 输入、回车/逗号/顿号加、X 删除、基于现有标签的建议列表、上限 12 个），
  EditDialog 与手工入库都接入；格子与值/封装同排显示 #标签（最多 2 个 +N）。
- 手工入库点击会关掉父级仓库布局：嵌套模态外点误触 → 改为打开手工入库时先关闭仓库布局（不再嵌套）。
- 产物 v0.3.7：冒烟 exit=0、probe=[200,200,200,'0.3.7']、ui-marker=true。
### V0.3.6 标签重做 + 手工入库 + 玻璃下拉 + 主题修复 + 中文提交 ✅
- 主题语义修复：theme store 的 dark/light 曾颠倒导致设置里“深/浅”按钮反了；现在 dark=深色主题。
- 格子标签：编辑字段改名“格子标签”，与阻值/封装同排高对比显示在卡片上（#标签，最多 2 个 +N），可搜索。
- 手工入库：仓库布局对话框新增“手工入库”——多行逐项填写名称/值/封装/厂商料号/供应商料号/数量/格子标签，选空格位后批量建档（ManualStockDialog.vue）。
- 玻璃下拉：components/ui/NiceSelect.vue（Headless Listbox）替换编辑/入库等处的原生 select。
- 项目规约：新增根 CLAUDE.md（提交信息一律中文：类型(范围): 中文描述；版本三处同步等）；历史 4 条英文提交已改写为中文并 force push。
- 产物 v0.3.6：冒烟 exit=0、probe=[200,200,200,'0.3.6']、ui-marker=true。
### V0.3.5 版本可视化 + GitHub 托管 + 升级缓存修复 ✅
- 后端 /api/v1/health 返回 version（app.version 唯一版本源，本次校正：0.3.2~0.3.4 期间
  main.py 版本号未随前端升，已统一为 0.3.5）；前端左上角 ChipNest 旁与「设置→版本」显示 vX.Y.Z。
- Electron 每次启动先 clearCache 再加载（旧 index.html 被磁盘缓存命中导致“升级不生效”的元凶）；
  冒烟升级为：三接口 200 + UI 标记（仓库布局按钮）+ 版本号前缀校验，全过才退出 0。
- 仓库：git init + 远程 https://github.com/DWZ753/chip-nest（main）；.gitignore 覆盖构建产物；
  发版打 tag（v0.3.5 起）。安装包/后端 exe 不入库（体积大，按 README 重建）。
- 产物 v0.3.5：冒烟 exit=0、probe=[200,200,200,'0.3.5']、ui-marker=true。
### V0.3.4 标签 + 设置拆分 + 文案去注释化 ✅
- components.tags（JSON 数组，≤8 个/每个 ≤20 字符）：alembic 0003 + 冻结增量补列（db.py 清单同步）；
  检索文本纳入标签；EditDialog 逗号输入维护，BinCard #标签 chips（≤2 +N，窄格隐藏）；
  schemas 出入参含清洗校验；新增 test_tags_roundtrip_and_search。pytest 22 项全绿。
- 设置拆分：顶栏「仓库布局」按钮 → LayoutDialog（网格尺寸/区名/最近操作流水）；
  「设置」→ AppSettingsDialog（深/浅色选择、字号、硬件状态）；旧 SettingsDialog.vue 删除。
- 文案清理：去掉“（重启后仍记住）”等实现注释式括注，占位示例一律只给例子。
- 产物 v0.3.4；真实用户库冒烟 [200,200,200]，tags 列自动补齐、42 元件保留。
### V0.3.3 文案朴素化（不要“故作高深” ✅）
- 主题切换提示改为「切换为深色/浅色」；连接徽标文字改中文（串口/模拟/离线/断开）；
  设置字号、BOM 对话框、网格统计等标题全部改大白话，去掉 // ZONE、// UI SCALE、
  PURCHASE LIST、01 LAYERS 之类代码腔；科技风保留在底色/玻璃/发光等视觉层面。
- 产物 v0.3.3（仅前端资源）；三接口探针冒烟 [200,200,200]。
### V0.3.2 UI 打磨（悬停重叠/文案通用化 ✅）
- BinCard 头行改 flex：名称 min-w-0 flex-1 截断 + 灯号 + 数量胶囊同行（hover 显），
  数量不再绝对定位，长名称（STM32H750VBT6…）不再与 ×N 重叠；窄格规则保留。
- 文案通用化：界面去“立创/LimeRC/LCSC”等品牌示例（供应商料号、遥控器项目等通用说法），
  中文提示不再夹带 bom_pick/MPN/Supplier Part 等代码词（字段本身仍存英文列头映射）。
- 产物 v0.3.2（仅前端资源变化，后端 exe 复用）；三接口探针冒烟 [200,200,200]。
### V0.3.1 热修复（老库升级 500 ✅）
- **问题**：v0.2.0 及更早安装包建的库无新列（manufacturer_part/supplier_part/zone_names），
  冻结版 create_all 只建新表不改老表 → /layout、/components 全 500（前端显示“后端不可用”）。
- **修复**：db.py 新增 upgrade_legacy_columns（PRAGMA table_info 查缺列 → ALTER ADD
  COLUMN，幂等）；main.py 冻结迁移 = create_all + 增量补列；新增 test_legacy_upgrade.py。
- **冒烟增强**：electron CHIPNEST_SMOKE 改为页面加载后真实 fetch layout/components/system
  三接口，必须全 200 才算通过（旧冒烟只看 did-finish-load，会漏过 500 白屏）。
- 验证：pytest 21 项全绿；真实用户库（42 元件，WAL）备份后升级无损、接口 200；产物 v0.3.1。
- 坑：WAL 库备份不能用单纯 cp 主库文件（会丢 WAL 数据），要用 sqlite backup API。
### V0.2.0 迭代（安装反馈修订 ✅，同日完成）
- **UI 换肤为终端科技风**：参考 hms-web-45a（HM·S//CORE）重构 style.css 全部设计令牌——
  纯黑基底 + 青色主光 #4cc3f0 / 紫罗兰 #8b8ef7、玻璃面 #10141a/#161c24、边框 #222c38，
  网格纹理背景、等宽 term-label（// ZONE 01）、卡片 hover 霓虹描边、色带自发光；默认深色
  （html.light 日光终端保留手动切换）。旧「莫兰迪木头感」已被替换，前面 M5/M6 描述里的
  莫兰迪措辞作废。
- **连接状态徽标修复**：ConnectionDot 改为高对比胶囊 —— MOCK=琥珀实心底+深字、
  SERIAL=青底描边、OFFLINE=红，不再与背景同色。
- **BOM .xlsx 直接导入**：新依赖 openpyxl + python-multipart（requirements.txt 已加）；
  services/bom.py 增加 parse_excel_bytes（表头别名识别 Name/Designator/Footprint/Quantity
  等，Footprint C0402/R0603 → 封装 0402/0603，仅认四位，防 LQFP-100 被误解析；纯值行自动
  补中文族名电容/电阻）；POST /api/v1/bom/import 上传接口返回与 /bom/parse 同构结果。
  用真实文件「BOM_LimeRC青柠 数字图传遥控器系统.xlsx」实测 42 行/96 件全部解析正确。
- **整表入库（购买清单）模式**：BomDialog 增加「选择 BOM 文件」+「整表入库（购买清单）」——
  每行名称/值/封装/数量可编辑，空格位下拉（默认顺序填空，空位不足提示扩容），逐项 POST
  /components 建档、成功打勾、失败可改后重试；前端 freeSlots() 由 bins store 提供。
- **串口探测加固（真问题）**：个别 COM 口 open() 可永久阻塞导致 uvicorn lifespan 卡死
  （本机复现一次）→ scan_once 改守护线程 + 总预算 wait_for（默认 ≥6s 放弃本轮）+ 防线程
  堆积；见 §6.11。
- 验证：pytest 20 项全绿；e2e 冒烟通过；真实 xlsx 经 HTTP 与打包后 exe 均解析正确；
  vue-tsc + vite build 零错误；headless DOM 冒烟确认 ZONE 标签/元件卡/MOCK 胶囊渲染；
  新 UI 截图存 `frontend/preview-tech-dark.png`（视觉 API 限流未人工复核，请目测）。
- 产物重建为 **v0.2.0**：backend/dist/chipnest-backend.exe + electron/release/
  ChipNest-Setup-0.3.9.exe（~137MB），win-unpacked CHIPNEST_SMOKE=1 实测页面加载成功。

## 4. 完成状态与收尾清单（M1–M7 + 打包 ✅，2026-09-08）

- M1 ✅ 后端骨架/迁移/布局（§3）
- M2 ✅ 库存域 CRUD + 并发防超卖（§3）
- M3 ✅ BOM 解析/规划/取料（§3 + §5「BOM 契约」）
- M4 ✅ HAL 硬件抽象层（§3 + §5）
- M5 ✅ 前端骨架 + 设计系统（§3）
- M6 ✅ 核心视图与动效（§3）
- M7 ✅ Electron 壳 + ESP32 固件 + 打包配置（§3）
- ✅ 免 Python 打包：backend/dist/chipnest-backend.exe + electron/release/ChipNest-Setup-0.3.9.exe（重建命令见 README「打包」）

### 收尾清单（剩余为可选增强/需人工）
- ⏳ 安装包 UI 走查：NSIS 向导/快捷方式/卸载（无人值守只验证到 win-unpacked 冒烟）。
- ⏳ 真机联调：烧录 .ino 后插 ESP32（本机 COM8 是 USB 口但无固件 → mock 属正常）。
- ⏳ 发布前可补：代码签名证书、应用图标（当前 electron 默认图标）、自动更新。
- ⏳ UI 最终目测：动画/主题/引导全流程按 README「验收目测清单」过一遍（最终裁判是用户）。

## 5. 关键契约速查（改接口前先看这里）

### 数据表
- **components**: id, name(≤64), value(≤32,可空), package(≤32,可空),
  manufacturer_part(≤64,可空), supplier_part(≤40,可空), quantity, threshold,
  zone, layer, slot, led_index(可空), search_text(检索预计算, 含料号), created_at, updated_at
  —— `UNIQUE(zone,layer,slot)`，索引 led_index。
- **transactions**(审计): id, ts(索引), kind(create/delete/in/out/bom_pick/adjust), component_id(FK SET NULL),
  delta(带符号), detail(中文快照), source(ui/guide/system)。**与主操作同事务；失败不出流水。**
- **layout_configs**: 单例 id=1；zone_count, layer_count, row_count, col_count,
  zone_names(Text JSON 数组，每区自定义名，空=第N区), updated_at；默认 1/3/1/4。slot = 0..row*col-1。

### REST API（前缀 /api/v1，127.0.0.1:8765）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /health | 存活探针 |
| GET/PUT | /layout | 布局读写（PUT 校验范围非法 422；body 支持 zone_names: string[] 与区数对齐） |
| GET | /components?q=&zone=&layer=&limit= | q 模糊搜 search_text（预小写 contains+autoescape），按位置排序 |
| POST | /components | 建档 201；槽位占用 409；越界 400；led_index 缺省自动 max+1 |
| GET/PATCH/DELETE | /components/{id} | 修改/搬家（三字段成组否则 422）；**quantity 不在 PATCH 模型** |
| POST | /components/{id}/stock | body {delta, note?, source?}；不足 409 detail={message, available} |
| GET | /transactions?limit= | 审计倒序 |
| POST | /bom/parse | {text} → {lines:[{raw,name,value,package,quantity}], total_quantity} |
| POST | /bom/plan | {text} → {steps:[{component,quantity,line_indexes}], missing, requested, complete} |
| POST | /bom/pick | {component_id, amount} → ComponentOut；409 同 /stock；审计 kind=bom_pick/source=guide |
| GET | /system/status | {mode: serial\|mock, connected, device, error} |
| WS | /api/v1/ws/status | 快照即发；变化广播 {"type":"adapter.status", mode, connected, device, error} |

### BOM 契约（M3 已定，前端已对接）
- 解析顺序铁律：先剥数量（x20/×5/*3/20个/10 只/5pcs，缺省 1）再认值/封装 token；一行多个数量取最靠前。
  四位纯数字=封装，1~3 位裸数字=无后缀阻值。
- 值匹配只认同家族（F/R/H，空后缀=R）；0.1uF==100nF、10k==10000 由归一化+1e-9 判定。
- 硬规则：封装不一致或值可归一化却不相等 → 出局（名称包含救不回），防 11k 误配 10k。
- 前端引导流程：plan → steps（component.led_index 即灯号）→ 每步 pick 扣减；409 即中断提示补货。

### HAL 协议（与固件必须一致）
- 115200 8N1；PC→ESP `PING\n`，ESP→PC `PONG\n`，握手 3s 超时失败。
- 点灯 `LED:<index>,<R>,<G>,<B>\n`（例 `LED:25,255,165,0\n` 橙）。
- 失败自动降级 Mock 永不崩溃；圆点：绿 serial / 黄 mock / 红断开。
- LED 语义：quantity<threshold 常亮红；充足灭；引导步橙（预留 set_guide_led）；无 led_index 跳过。
- 扫描默认仅 USB 描述口（蓝牙虚拟口会卡死 open），CHIPNEST_SERIAL_PORTS 可强制名单。

### events.py 总线
- 事件：`stock.changed` / `component.removed`（payload ORM Component，commit 后发射）。
- 订阅方：hal manager（LED）、ws hub（转发给前端可扩展）。**发射方在服务层，勿改调用点。**

### 防超卖实现（已就位，勿改坏）
- `stock.change_stock` 负数路径：select(for_update) 只用于精确报错 → 单条 UPDATE ... WHERE quantity>=need 判 rowcount；
  0 行时重查真实值抛 StockShortage(available)。
- 坑：UPDATE(MappedClass) 需 execution_options={"synchronize_session": "fetch"}，绝不可再手动 -= （双扣）。

## 6. Windows/本机踩坑记录（接手人必读，省得重踩）
1. **alembic.ini 禁止写非 ASCII 注释**：configparser 按 locale(GBK) 读 ini，中文注释 UnicodeDecodeError。
2. **alembic env.py 不能 asyncio.run()**：FastAPI lifespan 已在事件循环里 → env.py 用同步引擎（CLI/lifespan 两相宜）。
3. **pypinyin errors="ignore" 会吞 ASCII**（「贴片LED」只剩 tp）→ 只对汉字区间算首字母。
4. **Git Bash curl 传中文 JSON 会 GBK 转坏** → 一律用 httpx 脚本或 -d @utf8 文件。
5. Windows 控制台打印中文/emoji 先 sys.stdout.reconfigure(encoding="utf-8")。
6. uvicorn 日志父子 logger 重复 → log.py 已设 propagate=False。
7. 测试用独立临时库：conftest 顶部在 import app **之前**设 CHIPNEST_DB。
8. **蓝牙虚拟串口打开可永久阻塞**（uvicorn 卡在 Waiting for application startup）→ 默认只探 USB 口；
  特殊硬件用 CHIPNEST_SERIAL_PORTS=COM3,COM8 强指。
9. **npm 装 electron 卡死（GitHub fetch failed）**：走 `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/`；
  electron-builder 二进制另设 ELECTRON_BUILDER_BINARIES_MIRROR。
10. **PyInstaller 懒加载依赖**：SQLAlchemy aiosqlite 方言等不会自动收集 → --hidden-import aiosqlite / greenlet / websockets。
11. **个别 COM 口 open() 可永久阻塞**（uvicorn 卡在 lifespan，健康检查一直不通）：
    serial_adapter.scan_once 跑在守护线程并设总预算超时放弃，且 _probe_busy 防线程堆积；
    若再遇到启动卡死，先看 err 日志是否停在 Waiting for application startup。

## 7. 验收铁律（延续项目风格）
- 每完成一个 milestone：跑 `pytest` 全绿 +（能起服务时）`scripts/e2e_smoke.py` 通过，再进下一步。
- 代码规范：Python PEP8、中文注释在代码上方、80 列限宽、docstring 说明用途；新接口必须 Pydantic schema；
  新表同步 alembic 迁移；操作类接口落审计。
- UI 审美的最终裁判是用户本人（目测动画与主题），交付时给目测清单（README 末尾）。