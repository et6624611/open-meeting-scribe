# 任务清单：提问范围 + 明文模式（R2）

R2 变更：范围只保留「本场会议 / 全部会议」，默认本场；范围块只算一次，问答与智能体共用。

## T1 唯一检索器

- [x] 新建 `core/meeting_search.py`：`normalize_scope` / `build_scope_context`（内部 `search_meetings`）。
- [x] `meeting` 返回空块 + `searched=false`；`all` 检索全库，最多 4 场、每场 3 段。
- [x] 新建 `tests/test_meeting_search.py`，覆盖 spec §10 的 5 条。
- 验收：`pytest tests/test_meeting_search.py -q` 全绿。

## T2 请求模型与上下文构建

- [x] `ChatRequest` 增 `scope: Optional[str] = None`。
- [x] `_build_chat_context_blocks` 返回 `(blocks, sources, retrieval)`；维度 3 项目资料保持常驻注入，不随范围变化。
- [x] 新增维度：调用 `build_scope_context` 追加范围块与来源。
- 验收：`pytest tests/test_chat.py -q` 不回归。
- 验证：`scope=meeting` 无跨会议块；`scope=all` 有命中块且项目资料仍在。

## T3 端点回传与智能体共用

- [x] `/api/chat` 回传 `scope` + `retrieval`。
- [x] `/api/chat/stream` 内置 done 回传两字段。
- [x] 智能体路径复用同一范围块（拼入 `page_ctx`），不重算检索；终帧写 `scope/retrieval`。
- 验收：两条链路 done 均有值；同一问题在 qa/agent 下命中内容一致。
- 验证：`pytest tests/test_chat.py -q`；手工对比两模式。

## T4 前端状态与流式落库

- [x] `chat.ts`：`ChatScope='meeting'|'all'`、`RetrievalInfo`；类型与请求 body 补 `scope`。
- [x] `useAiChat.ts`：`chatScope` + localStorage `ai_chat_scope`，默认 `meeting`。
- [x] `useAiChatStreamCore.ts`：`SendOverride`/`Deps` 增 scope；`sendRaw` 落 `sendOptions.scope` 并透传；`onDone` 落 `msg.scope/retrieval`。
- 验收：`npm run build` 通过。

## T5 ComposerBar 控件

- [x] 范围触发器 + 两行弹层（本场会议 / 全部会议）+ 脚注；`all` 高亮。
- [x] 模式改「问答 | 智能体」明文分段，删除旧模式弹层；成本提示挂 `title`。
- [x] 窄栏降级。
- 验收：对齐原型；aria 正确；窄栏不溢出。

## T6 透传链

- [x] `AiChatComposer.vue` / `AiChatPanel.vue` / `AIPanel.vue` 增 `chatScope` prop 与 `update:chatScope` emit。
- [x] `editResend` / `editAndResend` override 增 `scope`。
- 验收：切换范围状态一致且持久化。

## T7 消息回显

- [x] 用户气泡前 `.msg-who`，旧消息回退 `meeting`。
- [x] AI trace 仅在有 scope/retrieval 时渲染。
- [x] 编辑态回填 `editScope`。
- 验收：刷新/切会话仍可见；旧消息无伪造 trace。

## T8 i18n

- [x] zh/en 补齐 spec §8 键；删除 `scope_project*`、`scope_trace_no_project`。
- 验收：英文无中文残留、无缺键。

## T9 全量验证

- [x] `pytest tests/test_meeting_search.py tests/test_chat.py -q`
- [x] `cd frontend && npm run build`
- [x] 浏览器冒烟 spec §10 七条。
- [x] `git diff --stat` 复核未触碰录音/逐字稿/纪要生成。
