---
title: 转 Public 前置检查清单 — OpenMeetingScribe
description: GitHub 仓库由 Private 转 Public 之前必须完成的合规/卫生/叙事检查项，含 2026-09-24 实测盘点结论
author: 产品经理（AI 起草）
created_at: 2026-09-24
updated_at: 2026-09-24
version: "1.0.0"
status: active
---

# 转 Public 前置检查清单

> 触发条件：v10 本地引擎 AC-1 断网闭环验收通过、本清单 B 级及以上全部勾选后，由项目方执行转 Public。
> 结论口径：**A = 阻断项（不完成不得转）；B = 强烈建议；C = 可转后补**。

## A. 阻断项

- [ ] **A1 评测数据去隐私化**：`tests/eval_local_engine/refs/`（云端时间轴、人工校对工作表、声纹片段索引）与 `results/`（含 `vp_*.json`、`metrics.json`、LLM 纪要产物）已入库，**包含真实会议全文与真实人名**。处置：迁移至 `.eval_local_engine/`（已 ignore）并从 git 删除，或以合成化名+打码文本替换后保留最小复现集。脚本与 EVAL 报告的方法论部分可留。转 Public 后 git 历史公开，**必须在转之前完成**。
- [ ] **A2 samples/ 音频确认不入库**：实测 `git ls-files samples/` 为 0，维持现状；在 CONTRIBUTING 明示评测素材不得提交。
- [ ] **A3 THIRD_PARTY_NOTICES 增补**：FunASR / ModelScope 四模型（seaco-paraformer、ct-punc、fsmn-vad、cam++）许可条款逐项核查，标注"引导下载、不随包分发"口径（Spike 风险表 + ADR-0018 一致性要求）。
- [ ] **A4 SECRET 扫描**：转之前对全历史跑一次 gitleaks/truffleHog；重点确认 `.env`、`data/settings.json`、体验授权凭据从未入库。

## B. 强烈建议

- [ ] **B1 v10 真机验收**：AC-1（macOS/Windows 断网闭环）、AC-4（失败回退不丢任务）通过——README 已按"开发中"如实标注，验收后可去掉 🚧。
- [ ] **B2 README front-matter/版本一致性**：VERSION、CHANGELOG 头部、git tag、README 标注四者对齐；当前以发版流程顺带解决。
- [ ] **B3 根目录卫生**：约 200 张调试截图（`*.png`）与云盘同步杂项文件（`LICENSE 2`、`VERSION 2` 等，均未入库）留在磁盘会随"直接分享文件夹"路径外泄；转 Public 前清理或移入 `docs/bug-fix-notes-assets/`（择一），并 gitignore 根目录 `/*.png`。
- [x] **B4 `.verify_shots/` 加入 .gitignore**：2026-09-24 已随本清单提交。
- [ ] **B5 双语"offline"叙事**：英文 README 首屏增加 100%-local 关键词行（对标 Meetily 心智），随 v10 发版 changelog 一并执行。

## C. 转后补齐

- [ ] C1 Issue 模板 / label 体系 / GitHub Topics（meeting-minutes, offline, asr, privacy…）
- [ ] C2 度量埋点假设验证：本地引擎激活率、模型下载完成率、Star 增长（需求记录「度量」节）
- [ ] C3 Discussions /  Showcase 渠道运营

## 2026-09-24 盘点事实（本清单依据）

| 检查 | 结果 |
|------|------|
| 根目录 PNG 入库数 | 0（全部未跟踪）✅ |
| `.env` / `data/` 用户数据入库 | 仅 `data/agent/_roles/` 内置角色 md，无用户数据 ✅ |
| 最大入库文件 | `app/static/assets/elk-*.js` 1.4MB（前端构建产物，正常） |
| 评测真实文本/人名入库 | **存在，A1 阻断** ❌ |
| SECURITY/README 三引擎流向矩阵 | 已随 v1.3.0 / 双语 README 落地 ✅ |
