---
title: 完工回报 — DC-R2-a 决策中心 R2 前端迭代（F1/F2/F3/F5）
id: DC-R2-A-REPORT
branch: feat/req-decision-r2a
base: main@2a7b427 → rebase 至 main@7aafcba（docs-only 前进，无冲突，rebase 后构建复验全绿）
date: 2026-09-25
owner: 前端开发工程师
---

# DC-R2-a 完工回报

依据 docs/REQUIREMENT-DECISION-CENTER-R2.md v0.2.0 §3（F1/F2/F3/F5）+ §6 子单 DC-R2-a + 项目方 09-25 裁决 D1。

## 1. 范围落地对照

| 项 | 结论 | 实现位置 |
|---|---|---|
| F1 分组卡片去冗余 | ✅ 组内卡片 meta 行不再显示会议名与日期（均与组头重复）；跳转纪要保留为文档图标按钮（title/aria-label=查看来源会议）；知识库徽标保留 | `DecisionCard.vue`（`.dc-meta` 行重写，`.dc-meta-jump`） |
| F2 删视图切换 | ✅ 「按会议分组/平铺」分段切换器整体移除，固定按会议分组；`view_group/view_flat` i18n 键（双语）与 `viewMode` 死代码全部清理 | `DecisionCenterView.vue` + 两份 `decisions.json` |
| F3 行内编辑/删除 | ✅ 卡片菜单新增「编辑决策文本」「删除决策」；编辑为行内 textarea（预填原文、trim 非空才可保存）；删除带二次确认（不可恢复操作不静默）；走既有 `PUT/DELETE /api/tasks/{task_id}/decisions/{id}`，零新接口；不回写纪要正文 | `DecisionCard.vue` + `DecisionCenterView.vue`（saveDecisionText/removeDecision） |
| F5 知识库可检索 | ✅ 原生 `<select>` 升级为 combobox（新组件 `KbFilterCombobox.vue`）：键入即过滤、ArrowUp/Down+Enter 键盘选中、ESC/点击外部关闭、保留「全部知识库/未关联知识库」特殊项（不参与键入过滤，任何输入下都有出口）；aria 齐备（role=combobox/listbox/option、aria-expanded/activedescendant） | `frontend/src/views/decisions/KbFilterCombobox.vue` |

边界遵守：改动全部限于 `frontend/src/views/`（DecisionCenterView + views/decisions/）与 i18n 键；后端零改动、API 契约零改动、`AddDecisionDialog` 字段结构未动、状态枚举未动。

## 2. 自测证据（qa-evidence/req-decision-r2a/，脚本 `selftest_dcr2a.py` 不入库）

- **构建全绿**：`npm ci && npm run build`（vue-tsc + vite）exit=0 → `build.log`。注：派工单写 pnpm，本仓前端实际为 npm + package-lock.json（无 pnpm lock），按仓库现状执行等价门禁。
- **既有测试不破**：`pytest tests/test_decision_center.py` 33 passed（后端未动）。
- **Playwright 浏览器自测**（VITE_DECISIONS_MOCK=1 mock 通道 + projects/tasks 路由 mock）：21 项断言 0 FAIL → `selftest-run.log`。截图：
  - `AC2_grouped_no_toggle.png` — 无切换器、固定分组
  - `AC1_jump_to_minutes.png` — 组内无重复会议名，跳转 `/meeting/mock-task-1?tab=summary&dq=…` 生效
  - `AC3a_menu_edit_delete.png` / `AC3a_inline_editing.png` / `AC3a_after_save.png` — 菜单两项在位 → 行内编辑预填 → 保存后卡片呈现新文本 + toast「决策已更新」
  - `AC3b_delete_confirm.png` / `AC3b_after_delete.png` — 二次确认面板 → 删除后卡片消失（6→5）+ toast「决策已删除」
  - `AC4_combo_typing_filter.png` — 键入「研发」仅剩特殊项+研发管理；`AC4_kb_filtered_result.png` — 键盘选中后列表仅见研发管理决策

## 3. ⚠️ 卡点披露：AC3「删除的 auto 决策重新生成后不复活」与代码事实不符

派工单断言「merge_decisions_after_regen 已保证不复活」，**核实为误**：

- `core/summarize.py:573-584`：`kept = [d for d in existing if source != "auto"]; return kept + parsed` —— 只保证「非 auto 保留项在前」，**不阻止已删 auto 复活**：删除动作不留下任何痕迹（全仓无 tombstone/decision_deletions 机制），重新生成时若新纪要正文仍含该结论，`parse_decisions_from_summary` 会把它作为新 auto 重新加回。
- 前端在「禁改后端」约束下无任何可靠修复手段（复活发生在后端合并层）。
- **建议**：派后端小单——删除 auto 决策时记录墓碑（如 `decision_deletions` 列表），`merge_decisions_after_regen` 按墓碑过滤 `parsed`。本单其余行为（编辑/删除即时生效、不回写正文）已全部达标。

## 4. 浏览器验收包（项目方点验用）

- **页面入口**：左侧导航「决策中心」（路径 `/decisions`），需有已完成会议纪要任务。
- **验证脚本（≤5 步，非技术）**：
  1. 打开决策中心：确认页面**没有**「平铺/分组」切换按钮，列表按会议分组，组内卡片下方**不再重复会议名称**；点卡片左下小文档图标 → 跳到该会议纪要页定位到决策原文 → 浏览器返回。
  2. 悬停任一决策卡片 → 点右侧 ⋯ 菜单 → 「编辑决策文本」→ 直接在卡片里改字 → 点「保存」→ 提示「决策已更新」且卡片立即显示新文字。
  3. 同菜单点「删除决策」→ 出现「删除后不可恢复」确认 → 点「删除」→ 提示「决策已删除」且该条消失。
  4. 筛选栏「知识库」下拉：点击后**直接键入**关键字（如某知识库名的两个字）→ 选项即时过滤；用 ↑↓ 键移动、回车选中 → 列表只剩该知识库会议的决策；再打开确认「全部知识库/未关联知识库」始终可选。
  5. （可选，对应 §3 卡点）对一条自动决策执行删除后，到该会议点「重新生成纪要」，再回决策中心查看——**当前版本该条可能重新出现**，此为后端合并机制缺口，待后端小单修复，点验时请勿以此判本单不通过。
- **通过标准**：1-4 步全部即符合 AC1/AC2/AC3(前端侧)/AC4；第 5 步为已披露残留项。

## 5. 残留风险与说明

- AC3 复活缺口（§3，已建议后端 follow-up，本单前端部分完整）。
- F1 视觉口径：跳转改为纯图标（12px 文档 icon，静置 70% 透明、悬停全显），日期徽标删除、知识库徽标保留——需求单允许「随实施稿」，如项目方点验觉得图标太隐可一并回调。
- combobox 演示证据基于 mock 通道（VITE_DECISIONS_MOCK=1，dev-only）；真实后端 CRUD 走同两接口（PUT/DELETE 已在 DC-DEC-B1 验收过），无契约变化。
- rebase 状态：本回报时已 rebase 至 main@7aafcba 并复验构建全绿；若合入前 main 再前进，按门禁仍需重 rebase + 复验。

**版本记录**
- 1.0.0（2026-09-25）：DC-R2-a 完工首报。
