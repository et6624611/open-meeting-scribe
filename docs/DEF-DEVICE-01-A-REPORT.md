---
title: 完工回报 — DEF-DEVICE-01-A 录音设备选择保存死循环（前端修复）
id: DEF-DEVICE-01-A-REPORT
branch: feat/def-device-01a
base: main@819542f（开单时 main）→ rebase 至 origin/main@d755b58（docs-only 前进，无冲突，rebase 后构建复验全绿）
date: 2026-09-25
owner: 前端开发工程师
---

# DEF-DEVICE-01-A 完工回报

## 1. 根因与修复

**根因**（与派工令一致，已按代码复核）：`SettingsView.vue` 旧守卫 `let _deviceInitialized = false` 假定 watch 首次触发必为 `loadDevices` 的回显赋值并跳过 POST；但回显仅在 `result.current_device` 非空时发生（falsy 检查）。后端当前值为空串时，用户第一次真实选择被当作「回显」吞掉，且 `selectedDevice` 已停在目标值不再变化 → 之后永远零 POST（对应审计日志 10:19 后 10+ 次进设置页零 POST）。

**修复**（`frontend/src/views/SettingsView.vue`，+8/−4）：显式标志替换首触发假定——

- 新增模块级 `echoDeviceValue: string | null`；`loadDevices` 回显赋值前置位 `echoDeviceValue = result.current_device`。
- watch 回调仅当 `newVal === echoDeviceValue` 时消费标志并跳过一次 POST；其余任何变更（含选回「自动检测」= 空串）一律 `setRecordDevice` 落 POST。
- 值匹配（而非一次性布尔）设计规避两类的边界：回显未实际改变值时不留悬空标志；连续多次回显各自被吞、不误伤真实选择。

**边界遵守**：后端零改动（DEF-DEVICE-01-BE 持久化问题另归后端）；下拉模板与 i18n 文案未动；diff 仅此一文件。

## 2. 验收自测（AC①-④ 全过；证据 qa-evidence/def-device-01/）

| AC | 断言 | 结果 |
|---|---|---|
| ① | 空值态首次选择即 POST（`["MicA-USB 麦克风"]`）；重进页面回显=所选设备 | ✅ |
| ② | 连续切换每次都落 POST：MicB → 自动检测(空串) → MicC 审计序列完整 | ✅ |
| ③ | 回显赋值零冗余 POST：加载回显、重进回显、手动刷新回显三场景均零 POST | ✅ |
| ④ | `npm run build`（vue-tsc+vite）exit=0；pytest 全量 340 passed | ✅（2 个失败为基线既有/环境性，见 §3） |

- 方法：Playwright 有状态 mock 拦截 `/api/record/devices`（GET，可变电流值）与 `/api/record/device`（POST，落审计序列），`post-audit.json` 记录期望/实际序列。
- **Pre-fix 复现证据**：`selftest-prefix-repro.log`——同脚本回退 buggy 版后 AC①-③ 全 FAIL（首次选择被吞、POST 序列缺失 MicA/MicB），缺陷现场与审计日志吻合；`selftest-after-fix.log` 同脚本 7 断言 ALL PASSED。
- 截图：`dev01_p1_before_first_select.png`（空值态下拉）、`dev01_p2_reload_echo_ok.png`（重进回显=所选设备）、`dev01_p3_multi_switch_posts.png`（连续切换后状态）。

## 3. pytest 两例失败的定性（与本单无关，对照组实证）

- `TestPhilosophyRandom::test_variants_contain_zh_and_en`：干净 origin/main@819542f worktree 全量同样 FAIL → **基线确定性既有失败**。
- `TestInsightAnalyzeEmpty::test_analyze_unknown_type`：测试不封闭——日志实证其真实调用云端 LLM（`云端 LLM 调用成功 user=anon, 5510ms`），`has_finding` 随模型输出漂移，同 commit 不同机器时点有 pass 有 fail → **环境性 flaky**。
- 决定性对照：在本 worktree `git stash` 移除本单修复后全量复跑 = 完全相同的 2 failed / 340 passed。本单 diff 为纯前端文件，不在后端测试路径上。
- 建议：两例可开 QA 卫生小单（philosophy 断言修正 + insights 测试注入 LLM stub），不阻塞本单。

## 4. 浏览器验收包（项目方点验用）

- **页面入口**：设置 → 转写（或地址栏 `/settings?cat=transcription`）→「录音设备」分区。
- **验证脚本（≤5 步，非技术）**：
  1. 打开 F12 网络面板（Filter 输 `device`），进入设置-转写分区。
  2. 首次选择任一麦克风设备 → 网络面板立即出现一条 `POST /api/record/device`（修复前此处什么都不发）。
  3. 刷新页面/退出设置再进 → 下拉框显示刚才选的设备，且**没有**新增 POST（回显不重复保存）。
  4. 连续切换 2-3 个设备（含「自动检测」）→ 每次切换都各有一条 POST。
  5. 全部操作后到「首页」点开始录音，确认使用最后所选设备（行为回归）。
- **通过标准**：2/4 步每切必发 POST、3 步回显零 POST 即通过。
- **前提说明**：若项目方机器上后端持久化链路正常，重进页面回显即验证 ①后半；「重启后端进程后设备是否保留」属 DEF-DEVICE-01-BE 后端子单范围，本单点验不据此判本单不通过。

## 5. 残留风险

- AC③ 的「回显值恰为 echoDeviceValue 的真实选择」理论撞车仅发生在「回显刚写入后未改选、再手动选回同一设备」——此时 DOM 值未变化，watch 本就不触发，无 POST 需求，不构成缺陷。
- 「自动检测」以空串 POST，与既有后端契约一致（auto_detect=true），未新增语义。
- rebase 义务：合入前若 main（现 d755b58+）前进，重 rebase + 复验构建。

**版本记录**
- 1.0.0（2026-09-25）：DEF-DEVICE-01-A 完工首报。
