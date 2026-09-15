# ChipNest 项目规约（给接手 AI / 工具的项目级记忆）

> 本文件是全项目共享的“长期记忆”，所有改动请遵守；HANDOFF.md 是里程碑与契约速查。

## 提交信息（强制：用中文）

- 提交信息一律用中文写，格式：`类型(范围): 中文描述`
- 类型沿用 conventional 小写：`feat` `fix` `chore` `docs` `refactor` `test` `style`
- 范围可选（backend / frontend / electron / hardware / 打包 等）
- 描述必须能让人不看 diff 就明白意图，不写英文摘要

示例：
- `feat(frontend): 元件支持自定义格子标签并在卡片展示`
- `fix(backend): 冻结版启动时给老库增量补列`
- `chore: 忽略构建产物`

历史提交如已按此改写，禁止再制造英文提交信息；重写已推送历史前先确认无他人协作者。

## 界面文案（强制）

- **界面上一律不写说明性/注释性文字**：不解释怎么操作、不写括号注解、不写实现说明。
  反面例子：「点格子可编辑；搬家请先点『移动』」「每个区的层数/行数/列数都可单独设置」
  「（另有默认尺寸供新建区使用）」「清空前会自动留一份备份文件，需要时能找回」。
- 界面只呈现三类文字：**数据**（字段名、数值、位置）、**状态**（共 2 层、模拟模式、缺货）、
  **动作结果**（已把『××』从 1区/1层/0格 搬到 1区/1层/1格、已清空：删除 3 个元件）。
- 校验/失败提示只给结论，不给教程：「未选择格子」「没查到对应元件」「槽位已被占用：××」。
- 用法说明、示例、原理一律写进 README / 发布说明，不占界面。
- 悬停 title 只放名词性短语（「空位」「删除第 2 区」），不放句子。

## 版本号（强制）

- 语义化版本，发版频率要克制：**只有攒够一批内容才升 MINOR**，修 bug 只升 PATCH，
  同一天内的小改动合并成一次发版，禁止一个功能一个版本。
- PATCH：只修 bug / 文案 / 打包细节，接口与数据库结构不变。
- MINOR：新增功能、接口新增字段、数据库新增列/表（老库能自动升级）。
- MAJOR：破坏性改动（接口不兼容、数据结构需手工迁移）。
- 每次发版必须同步改 `backend/app/main.py` 与 `electron/package.json`，并写 `docs/release-notes-vX.Y.Z.md`。
- 已发布的 Release 不做重编号。例外只有一次：2026-09-15 把当天小步发出的 1.1.0 / 1.2.0 / 1.3.0
  合并重编号为一个 **v1.1.0**（用户要求，删掉了那三个 Release 与标签后重新打包发布）。

## 其他铁律（与 HANDOFF §7 一致）

- 每完成里程碑：backend 目录跑 `pytest` 全绿；能起服务时跑 `scripts/e2e_smoke.py`。
- 前端改动必须 `npm run build`（vue-tsc 类型检查）通过再发版。
- 发版号同步改三处：`backend/app/main.py` 的 FastAPI version、`electron/package.json` 的
  version，二者必须一致；前端显示取后端 /api/v1/health 的 version。
- 数据库结构变更：开发走 alembic 新迁移；同时把同款列追加到
  `backend/app/db.py::LEGACY_COLUMN_UPGRADES`（打包冻结版靠它增量升级老库）。
- 界面文案面向普通用户：中文大白话，不写实现说明/代码词；品牌示例词（立创/LimeRC 等）
  只在文档中出现，不进 UI。
- 新增接口必须 Pydantic schema；操作类接口落审计流水。
- 打包/发版流程见 README「打包」与 HANDOFF，发版按下方清单执行。

## 发布流程（发版清单）

1. 改版本号：`backend/app/main.py` 的 FastAPI version 与 `electron/package.json` 的 version 同时改，
   两处必须一致（前端显示取 `/api/v1/health`）。
2. 自检：`backend` 跑 `pytest` 全绿 → `frontend` 跑 `npm run build`（含 vue-tsc 类型检查）。
3. 后端冻结：`backend` 下 PyInstaller 一档命令打包 `run_desktop.py`
   （须带 `--collect-all pypinyin --collect-submodules uvicorn` 与 aiosqlite/greenlet/websockets/python_multipart 隐式导入）。
4. 安装包：`electron` 下 `npx electron-builder --win nsis`；国内网络先设
   `ELECTRON_MIRROR` 与 `ELECTRON_BUILDER_BINARIES_MIRROR`（npmmirror），产物在 `electron/release/`。
5. 冒烟：`CHIPNEST_SMOKE=1` 启动安装版，三项全过才算通过——三个 200 探测、
   版本号与 `app.getVersion()` 相等、界面出现「仓库布局」标记；失败退出码 3。
6. 提交与打标（中文提交信息）：`git commit` → `git tag vX.Y.Z` → `git push origin main --tags`；
   安装包/构建产物不入库（已在 .gitignore）。
7. 建 Release：`gh release create vX.Y.Z electron/release/ChipNest-Setup-X.Y.Z.exe --title ... --notes-file docs/release-notes-vX.Y.Z.md`，
   并在发布说明里写上 size 与 sha256（`sha256sum` 现场取）。
8. 用户先本地验证再发版/打标；重装前提醒关闭 `ChipNest.exe`。禁止重写已推送历史。
