# ADR-0004 实时转写升级 qwen-audio-3.0-asr-flash-streaming

- 状态：Accepted
- 日期：2026-09-03
- 相关：docs/API_CONTRACTS.md、core/realtime_asr.py、core/hotwords.py
- 取代：ADR-0002 中实时模型部分（批处理模型 paraformer-v2 不变）

## 背景

v0.3 实时转写使用 `paraformer-realtime-v2`。DashScope 官方文档已明确：

> Paraformer 是较早一代的 ASR 模型……若您的业务允许，建议迁移到 Fun-ASR 或 Qwen-ASR。

实时场景下官方首推 `qwen-audio-3.0-asr-flash-streaming`，相比 paraformer-realtime-v2 有明确优势。

## 选项

1. **qwen-audio-3.0-asr-flash-streaming**：官方首推实时模型。支持热词 + **Prompt 上下文注入**（无需预配置热词即可提升专业术语识别率）；支持更多音频格式（pcm/wav/opus/speex/aac/amr）；无时长限制；支持句级 + 字级时间戳；支持即时热词（随请求内联传入，无需预创建热词表）。
2. **fun-asr-realtime**：能力接近，支持热词，但不支持 Prompt 上下文注入。
3. **qwen3-asr-flash-realtime**：支持情感识别，但不支持热词和上下文增强。
4. **paraformer-realtime-v2**（当前）：上一代模型，仅支持热词，无上下文增强能力。

## 决定

**实时转写升级为 `qwen-audio-3.0-asr-flash-streaming`**。

核心收益：
1. **上下文增强（context）**：可在请求中传入领域术语/对话历史，无需预配置热词即可提升专业术语识别率。会议场景下可传入参会人名单、议题关键词等。
2. **即时热词（vocabulary）**：随请求内联传入热词键值对，无需预先创建热词表，适合临时性、会话级别的热词优化。
3. **兼容性**：同时支持预编译热词（vocabulary_id），现有热词表可直接复用（需更新 target_model）。
4. **SDK 兼容**：使用相同的 DashScope SDK `Recognition` 类和回调机制，WebSocket 连接逻辑无需改动。

批处理转写（paraformer-v2）保持不变，因其支持说话人分离且异步处理长音频稳定。

## 代码变更

| 文件 | 变更 |
|------|------|
| `core/realtime_asr.py` | 模型名升级；新增 `vocabulary`（即时热词）和 `context`（上下文增强）参数 |
| `core/hotwords.py` | 热词 API 适配新版：`model` → `target_model`，`{"word": ..., "weight": 2}` → `{"text": ..., "weight": 4}`，上限 500 → 2000 |
| `docs/API_CONTRACTS.md` | §9 实时语音识别章节更新模型名与参数 |

## 后果

- 正面：识别质量提升（上下文增强）；热词配置更灵活（即时热词免创建）；官方持续维护的新模型。
- 负面：需确保 SDK 版本 ≥ 1.25.23（支持 context 参数）；现有热词表需以新 target_model 重新创建或确认兼容。
- 后续可探索：① 上下文增强传入参会人名单/议题关键词；② 即时热词替代预编译热词简化流程。
