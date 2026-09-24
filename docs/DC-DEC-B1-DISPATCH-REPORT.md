<!--
  派工完工回报（兜底留档）
  单号: DC-DEC-B1 · REQ-DECISION-CENTER v0.2.0
  回报时间: 2026-09-25
  回报通道: 主通道（群消息唤醒）报错「无完整 Conversation Run 发送身份」，已改走兜底通道
            qoderwake session send --session-id eaf4b142-5230-4284-9f08-d749f5608689 送达成功
-->

# DC-DEC-B1 完工回报

## 状态：R1 / R2 / R4 全部完成，分支已推送，等待产品验收合入（未合 main）

- **分支**: `feat/req-decision-center-b1` @ commit `7e1a328`
- **PR**: https://github.com/et6624611/open-meeting-scribe/pull/7
- **API 契约**: 已登记 `docs/API_CONTRACTS.md` §12（DC-DEC-F1 前端同事 d1b77737cde5 可据此对接）
- **自测证据**: `qa-evidence/dc-dec-b1/self-test-report.md`（新增 `tests/test_decision_center.py` 29 用例全过 + 回归基线证据；2 例 smoke/misc 失败已证明为 worktree 缺 gitignore 本地数据的環境性差异，main 基线通过）

## 工作包摘要

- **R1**: task JSON `decisions` 数组（§4 字段全量）；`core/summarize.py` 提示词「二、主要结论」格式硬约束 + `parse_decisions_from_summary()`；写回时机与 todos 一致（`pipeline_runner` stage2 + `import_tasks`）；解析失败降级为空 + joblog warn 不阻断；notes 注入 type=decision 同步创建 decision 项。
- **R2**: 任务级 CRUD + PATCH supersede + 跨任务 `GET /api/decisions`（since/until/kb_id/status/q/group_by）；pydantic 校验、`_mark_modified`+`save_task_to_disk`；契约登记 §12。
- **R4**: `scripts/backfill_decisions.py`（user_summary 优先、source=backfill、幂等跳过 + `decisions_backfilled_at` 标记、失败可重跑、输出 `_backfill_report.json`）。

## 兼容性硬约束确认

旧 task JSON 无 `decisions` 字段一律按空数组读取（`_get_decisions` 类型兜底 + `TestTaskDecisionCRUD` legacy 用例实证），不报错。

## 实现偏差披露（2 点）

1. 默认角色内置模板 `data/agent/_roles/_builtin/meeting-minutes/summary-template.md` 与 `SYSTEM_PROMPT` **同步**加了「二、主要结论」格式硬约束——模板在运行时覆盖常量，只改一处不生效。
2. 回填报告落盘 `data/_backfill_report.json`（置于 `data/tasks/` 之外），避免任务加载器 `data/tasks/*.json` glob 误读为任务文件。

## 需产品裁决 / 遗留

- 无阻塞项。遗留风险见自测报告「Residual risks」（LLM 真实格式遵循度、回填未跑真实数据、多行折行列表项会被拆分、related_todo_ids 自动关联按 v1 口径未实现）。
