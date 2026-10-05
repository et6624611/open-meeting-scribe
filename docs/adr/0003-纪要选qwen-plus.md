# ADR-0003 纪要生成 选 通义千问 qwen-plus

- 状态：Accepted
- 日期：2026-09-03
- 相关：core/llm.py、core/summarize.py、docs/API_CONTRACTS.md §5

## 背景
语音模型只产出「口语逐句稿」，需 LLM 加工成结构化纪要（结论 / 待办 / 议题归类）。既然 ASR 已用 DashScope，纪要 LLM 若能共用同一 key 与厂商，可简化凭据与计费。

## 选项
1. **通义千问 qwen-plus**：与 ASR 同一 `DASHSCOPE_API_KEY`；中文强；性价比高。
2. 通义千问 qwen-max：质量更高，成本更高。
3. 其他云 LLM（OpenAI/Kimi/智谱）：需额外 key 与账号，v1 增加管理负担。
4. 本地 Ollama：与 ADR-0001 纯云决定冲突，留 v2。

## 决定
**默认 `qwen-plus`**，与 ASR 共用一个 DashScope key。`qwen-max` 作为「质量优先」可选项，通过 `.env` 的 `LLM_MODEL` 切换，不改代码。

## 后果
- 正面：单厂商单 key，凭据与计费统一；模型可配置切换。
- 负面：纪要质量受提示词工程影响，需在 `core/summarize.py` 迭代。
- 后续需注意：~~涉密会议不适合走云纪要，v2 需提供本地 LLM 兜底~~ ——v2 本地方案已取消（2026-09-12），项目无离线版本开发计划，所有计算能力通过云端 API 提供。
