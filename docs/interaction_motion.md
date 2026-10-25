# ChipNest 连续交互重构交接

本次改动基于 12c00fb，用户已授权本地提交；不推送、不打标、不发版。
仓库为 E:/esp32/chip-nest，交互提交时版本仍为 1.9.1。
后续版本准备已调整为 1.10.0，见 [发布说明](release-notes-v1.10.0.md)。
用户暂时接受当前版本，后续调整以新的实际体验反馈为准。

## 目标与最终交互

先在灵感工作台验证连续过渡，再落地到现有 Electron 应用，沿用其视觉风格。
重点是界面连续、可中断，区分共享元素运动与不同正文的交接。
不同正文采用相邻裁切推移，避免同位置叠字及先清空再闪现。

1. 设置五页、库存六页及入库内层视图采用连续内容推移与动态高度。
   标签指示器与窗口尺寸使用可中断弹簧，快速反向或第三目标保留当前位置。
   当前正文立即可操作，离开的正文使用 inert 与 aria-hidden。
2. 设置、库存、仓库布局统一挂载入场；首屏先参与正常布局再测量，
   避免零高度撑开窗口。仓库布局新增区有行入场与高度过渡。
3. 移动、合并格、停用格、多选使用唯一 active_mode，切换时统一清理
   拿起的主格、共用格、合并源、多选项与删除确认；业务提交期间暂缓切换。
4. 四种工具只使用搜索栏下方的一条顶部 sticky 工具栏。
   默认四个入口；激活后整排原位变为操作控件；退出或 Esc 返回入口。
   拿着卡片或合并源时，Esc 先释放当前选择，再次按下退出模式。
   选格流程优先交接到同一工具栏，并清理当前工具的临时状态。
5. 工具栏按实际按钮、文字和间距测量宽度，右端固定，宽度平滑变化。
   文字增加时展开，删除时收合，并限制在可用宽度内。
   浏览器空态实测：移动 286px、合并 240px、停用 262px、多选 507px；
   这些数值是测量结果，不能作为固定设计宽度。默认按钮态约 376px。
   本次观察的行高为 46px，模式切换不改变货架起始位置。
6. 卡片移动支持抬起、跟手、有效目标反馈、落位、主格两卡交换、共用格移动，
   以及边缘自动滚动、拖出取消、Esc/失焦/指针取消回弹。
   原有点击和键盘放置共用同一落位路径。
7. 联网识别候选高亮连续移动；五个字段只动画变化的值，未变值保持静止。
   实际输入控件始终只有一份；聚焦或手动输入立即接管。
   候选参数区及编辑窗口高度连续变化。

顶部入口与底部框同时显示、操作态固定 820px 均属于已替换的中间方案。

## 文件与实现要点

| 文件 | 职责 |
| --- | --- |
| frontend/src/utils/motion_state.ts | 相邻内容位置与弹簧积分 |
| frontend/src/utils/motion.ts | RAF、位置/速度、改向、直接跟手与减少动态效果 |
| frontend/src/components/ui/motion_panel.vue | 缓存已访问正文、裁切推移、动态高度 |
| frontend/src/components/ui/motion_tabs.vue | 标签指示器测量与运动 |
| frontend/src/components/ui/motion_field.vue | 保留真实输入控件的文字交接 |
| frontend/src/components/GridView.vue | 互斥工具状态、顶部工具栏及内容宽度测量 |
| frontend/src/composables/use_grid_drag.ts | 指针生命周期、投放事务、滚动及落位 |
| frontend/src/utils/grid_drag_state.ts | 投放目标分类与拒绝规则 |
| frontend/src/components/grid_drag_preview.vue | 独立渲染拖动卡片，避免逐帧重建货架 |
| frontend/src/components/EditDialog.vue | 联网候选高亮、字段与参数区动画 |
| frontend/src/components/AppSettingsDialog.vue | 设置各页接入连续过渡 |
| frontend/src/components/BomDialog.vue | 库存各页及入库内层过渡，保留 BOM 状态 |
| frontend/src/components/LayoutDialog.vue | 统一入场、新增区及窗口高度变化 |
| frontend/src/style.css | 入场、裁切、拖动、sticky 工具栏及减少动态效果 |

缓存仅覆盖当前窗口生命周期内已访问的内容，关闭及选格卸载仍沿用原流程。
盘点草稿、BOM 文本、项目、份数与计划在标签切换时保留；
操作记录和补货清单再次进入时刷新，见对应两个 panel 文件。

toolbar_content_width 排除 flex-grow 留白，按真实控件与文字求和。
MutationObserver 只观察节点与文字变化，ResizeObserver 观察可用宽度；
它们在卸载时清理，避免尺寸动画产生观察反馈循环。
拖动坐标用 jump 直接跟手，保留独立的抬起/落位运动；正确换算 body zoom。

## 共用格原子移动接口

新增 PATCH /api/v1/components/{component_id}/slots：

```json
{
  "from_position": {"zone": 1, "layer": 2, "slot": 0},
  "to_position": {"zone": 1, "layer": 2, "slot": 1}
}
```

返回 ComponentOut。移动已有附加格时，主位置、库存数量、占用格总数保持不变。
在读取元件前 BEGIN IMMEDIATE，再校验源、目标及占用情况，以一个事务移动。
失败不先增后删；成功记录 delta=0 审计与单步撤销；原位投放为无操作。

- schema：backend/app/schemas.py 的 SlotMove。
- 路由：backend/app/routers/components.py 的 move_component_slot。
- 服务：backend/app/services/stock.py 的 move_slot。
- 前端：api/client.ts 的 moveComponentSlot、stores/bins.ts 的 moveSlot。
- 回归：backend/tests/test_slot_move.py，覆盖撤销、无效目标、并发及原位。

交互提交未修改数据库结构、Electron 主进程及版本号。
将来发版需按仓库 AGENTS.md 的接口新增规则选择版本，并走完整发布检查。

## 验证与边界

提交前已用当前最终构建复核：生产构建、15 项前端回归、166 项后端回归、
全新独立库业务冒烟与全新目录 Electron 启动冒烟均通过。

本对话已执行：

- frontend：npm run build，含 vue-tsc；node --test tests/*.test.mjs，共 15 项。
- backend：.venv/Scripts/python.exe -m pytest -q，共 166 项，含新增 7 项。
- 全新独立库业务冒烟：scripts/e2e_smoke.py。
- 独立数据目录 Electron 启动冒烟：三个接口 200、版本 1.9.1、桥接与首屏标记。
- 浏览器实际指针：空位放置、两卡交换、共用格移动、拖出取消、还原。
- 实际验证停用后恢复、添加共用格后解除、选择清空、删除确认复位。
  测试未执行批量删除，没有提交测试新增区、联网表单或手工入库草稿。
- 独立 12 层货架滚动约 1440px 后，工具栏仍在顶部，进入、操作及退出正常。
- 1080×688 内容窗口检查；实际联网查询候选切换、输入接管及选格往返。
- 最终紧凑宽度修正重新通过前端构建与 15 项回归，并逐种浏览器实测。

352ms 收敛检查采用确定性测试时钟；截图调度不作为实际帧率证据。
原生窗口曾确认顶部工具栏原位转换；最终紧凑版本已重新启动，
但最后一次原生输入验证受其他窗口遮挡与输入几何不可用影响，
紧凑宽度及动态展开的视觉验证使用浏览器。完整原生手感继续由用户验收。

预览使用 Codex 工作目录下的独立库和模拟硬件。
截图、预览启动副本、工作记录、数据库、日志及构建产物不属于本次源码提交。
本机临时预览端口为 18881（浏览器）、18882（Electron），服务停止后需重启。
业务冒烟会清理目标库，验证时须使用全新的独立目录与端口。

## 后续接手约定

- 延续顶部单一工具栏、原位转换、按内容收合与唯一 active_mode。
- 延续可中断运动与当前正文即时可操作的时机，保留草稿及真实输入控件。
- 修改后验证快速改向、尺寸/字号变化、拖动取消、选格返回和事务期间切换。
- 本轮范围是上述入口与流程，尚未完成应用所有交互控件的全面动效重构。
- 界面只呈现数据、状态、动作结果；用法和实现说明留在文档。
- 用户目前授权本地 commit；远端推送、发版及后续扩大改造按新指令执行。
