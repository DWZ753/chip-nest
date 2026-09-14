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
