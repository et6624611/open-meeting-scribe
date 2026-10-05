---
title: "ADR-0020 工程化能力收敛：退役自建 Agent 循环，CLI 为唯一智能体引擎"
description: "废弃 core/agent_loop.py 的进程内 ReAct 循环（双轨 function calling/文本回退），内置 AI 对话回归上下文注入+单轮流式问答；会议域工具实现迁移至 core/agent_tools/impl.py 专供 CLI 的 MCP 反向桥消费，洞察板共创等工程化写入仅智能体（CLI）模式具备。"
tags: ["adr", "ai-chat", "agent", "qoder-cli", "architecture", "retirement"]
created_at: "2026-09-29"
updated_at: "2026-09-29"
version: "1.0.0"
author: "wangyongliang"
status: "published"
category: "architecture"
related_docs: ["docs/adr/0019-智能体模式本地CLI引擎与MCP反向桥.md", "docs/ARCHITECTURE.md"]
---

# ADR-0020 工程化能力收敛：退役自建 Agent 循环，CLI 为唯一智能体引擎

- 状态：Implemented（2026-09-29 落地并实测）
- 日期：2026-09-29
- 决策人：Yongliang Wang
- 本决策 **supersede**：《对话 Agent 采用 function calling 为主、文本回退的双轨工具调用模式》（2026-09-16，core/agent_loop.py 的原始 ADR）
- 相关：[ADR-0019](0019-智能体模式本地CLI引擎与MCP反向桥.md)（CLI 引擎与 MCP 反向桥，本决策后其为唯一工程化载体）

## 背景

自建 Agent 循环（`core/agent_loop.py`，ReAct + 双轨工具调用）落地后长期处于"半成品"状态：

1. **实际收益低**：系统提示词已四维注入会议上下文（转写/纪要/待办/洞察台摘要），LLM 绝大多数场景直接作答、几乎不触发工具调用；多轮循环与文本回退双轨维护成本高（同一套工具需 schema + 自然语言两处定义）。
2. **与 CLI 能力重叠且更弱**：ADR-0019 引入的本机 CLI 引擎具备完整无头 Agent 能力（长链路多步规划、真实文件操作、MCP 反向桥），且其读工具执行仍复用 `agent_loop.execute_tool`——自建循环的"循环"部分是冗余的，"工具实现"部分反而是 CLI 的地基。
3. **维护裁决**：聚焦软件优势功能（会议智能），不在通用工程化会话上继续投入。

## 决策

1. **物理删除** `core/agent_loop.py`：`run_agent_loop` ReAct 循环、`AGENT_TOOLS` JSON Schema、文本回退（`TEXT_TOOLS_INJECTION`/`[TOOL_CALL]` 解析）、`_supports_native_tools`/`_call_llm_with_tools`/`_cloud_llm_with_tools` 全部退役。
2. **内置对话回归"上下文注入 + 单轮流式问答"**：`chat_stream` 内置分支就地组装 messages 后直接 `async_chat_completion_stream`；`done` 后处理（`extract_injectable_items`、`model_usage` 回显、Mermaid 意图检测）原样保留；CLI 失败 `__fallback__` 落入同一单流路径。
3. **工具实现迁移而非删除**：`execute_tool` 分发器与 `_tool_*` 实现逐字节迁入 `core/agent_tools/impl.py`（单一来源），供 MCP 反向桥（`app/routers/agent_tools.py`）继续消费——CLI 智能体的读工具执行链路不变。
4. **配套死代码清理**：`core/cloud_client.py` 删除 `cloud_llm_chat_with_tools()`；`app/routers/cloud_api.py` 的 `CloudLLMRequest` 移除 `tools`/`tool_choice` 透传字段（Pydantic 忽略未知字段，旧客户端多发无害）。
5. **前端事件面保留**：stage/tool_call/tool_result/engine_route 解析保留（CLI 引擎仍发射）；洞察板共创（整板/单节落盘）在问答模式起跳时明确 toast 提示需切换智能体模式。

## 否决的备选

- **feature flag 静默保留双轨** — 否决：半成品继续占用心智与回归面，违背聚焦裁决。
- **连工具实现一并删除** — 否决：CLI 的 MCP 读工具执行会断链。
- **继续迭代自建循环至可用** — 否决：维护者明确无力在此投入，且 CLI 已提供更强替代。

## 影响

- 未安装/未启用 CLI 的用户：AI 对话 = 单轮流式问答，无多轮工具调用（常规问答能力基本无损，因上下文已预注入；待办注入卡、关键词动作、划词改写不受影响）。
- 洞察板共创落盘、`update_summary`、`inject_items` 等写入型工具能力仅智能体（CLI）模式具备；前端已给出引导文案。
- 双轨工具定义的维护成本消除：`core/agent_tools/catalog.py` 成为唯一工具定义来源，`impl.py` 为唯一实现来源。
- 验证：pytest 620 passed（1 个失败为环境依赖存量问题）；实测问答 token/done 正常、done 后处理在场；CLI engine_route + MCP `oms-tools connected` + 回环正常；`/api/agent-tools/invoke` 令牌校验在线。
