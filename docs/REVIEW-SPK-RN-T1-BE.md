---
title: "REQ-SPK-RN T1 设计稿与 BE 提案初审意见书（O1-O3 + D6 联裁）"
description: "IDE 承接方管理员对说话人实名化两单交付物的初审结论：T1 设计稿 v0.2.0 与 REQ-SPK-RN-BE 技术提案均通过，O1/O2/O3 与 D6 正则收编一并裁决，含 data/tasks 词形存量取证。"
tags: ["review", "speaker-realname", "dispatch", "decision"]
created_at: "2026-09-25"
updated_at: "2026-09-25"
version: "1.0.0"
author: "wangyongliang"
status: "published"
category: "governance"
related_docs: ["docs/REQUIREMENT-SPEAKER-REALNAME-DISPLAY.md", "docs/design/SPK-RN-DISPLAY-STRATEGY.md", "docs/DISPATCH-TRACKER.md"]
---

# REQ-SPK-RN 初审意见书（T1 设计稿 × BE 提案联裁）

> 初审人：IDE 承接方管理员 · 2026-09-25。输入：`docs/design/SPK-RN-DISPLAY-STRATEGY.md` v0.2.0（branch `docs/req-spk-rn-t1-design@b159b41`）+ `qa-evidence/RT-P0-FIX/REQ-SPK-RN-BE-proposal.md`（已随 AM-B1 合入 main）。

## 一、初审结论

| 交付物 | 结论 | 备注 |
|---|---|---|
| T1 设计稿 v0.2.0 | **通过** | 点位普查（9 处遗漏入 H1）、D5 两形态聚合粒度、Q2 取舍报告、BE-R3 联调基准均闭环；AC-7/AC-8 设计合理 |
| BE 技术提案 | **通过** | 「空字符串=未命名」数据形态论证充分（不选 null 的理由成立）；消费方清单 8 处与代码核查一致；三类新用例+存量零改写 Prove-It 符合门禁要求 |

## 二、裁决

- **D6（BE-R3 正则超集收编）= 批准**。两侧统一采用超集正则（数字形态 + `Speaker One…Ten` 单词形态 + 中文两式），AC-8 双侧同正则断言按设计稿 §8 执行。
- **O1（前端取数口径）= 按 BE 提案口径钉死**。T2 聚合以「值为空/命中占位超集正则」计数，消费 `normalize_speaker_mapping` 输出；BE 未合入窗口前端本地判定器同款超集兜底。联排标注：T2 与 BE 合入顺序不设强制依赖（设计稿 §6.2 成立），关单前跑通 AC-8。
- **O2（正则宽度）= 收编单词形态，附取证留痕**。本次初审完成 `data/tasks` 只读扫描（400 文件）：**数字形态 80 个、单词形态 0 个存量**。单词形态系前端渲染变体（项目方指令点名即此场景），数据层无存量；仍按超集实现——成本一个 alternation 分支，换取指令场景全覆盖 + 备份恢复/异机数据防御。取证脚本口径：`^Speaker\s+(One|…|Ten)\b`（IGNORECASE）全文匹配。
- **O3（prompt 中性措辞）= 归 T1 定稿确认**。BE 实施不等待：按提案保守口径「未识别说话人+序号仅结构定位、不进正文成品」先行，T2 设计稿定稿措辞后如有出入以产品文案为准、BE 侧仅改 prompt 常量不改逻辑。

## 三、后续动作

1. **REQ-SPK-RN T2 实施**可派（设计稿为实施依据；Q2 取舍报告维持「保留『未识别』筛选项」建议，项目方如无异议即随 T2 验收自然确认，不再单独等待）。
2. **REQ-SPK-RN-BE 实施**可派（按提案 §6 四步拆分；worktree 新分支基于 main；pytest 全绿门禁；不动 frontend/、不动存量数据）。
3. 两单联调基准 = 本意见书裁决 D6/O1 口径；AC-8 双侧同正则断言为共同关单条件。
