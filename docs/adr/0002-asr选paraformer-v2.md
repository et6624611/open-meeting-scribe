# ADR-0002 ASR + 说话人分离 选 paraformer-v2

- 状态：Accepted
- 日期：2026-09-03
- 相关：docs/API_CONTRACTS.md、core/transcribe.py

## 背景
云方案下需要一个「音频 → 文字 + 谁说的」的服务。DashScope 非实时语音识别提供多个模型：`paraformer-v2`、`fun-asr`、`qwen-audio-3.0-asr-flash-filetrans`、`qwen3-asr-flash` 等。核心诉求：中文准、**自带说话人分离**、支持热词、异步处理长会议音频。

## 选项
1. **paraformer-v2**：中文成熟；`diarization_enabled` 直接返回 `speaker_id`；支持 `language_hints`、热词 `vocabulary_id`、语气词过滤、时间戳；异步、单文件 ≤12h/≤2GB。
2. fun-asr：能力强，但分离/热词等参数文档以 paraformer-v2 最完整、最贴合会议纪要场景。
3. Flash 系列（同步）：适合 ≤5 分钟短音频、免轮询，但长会议不适用。

## 决定
**主用 `paraformer-v2`**（异步 + 分离 + 热词）。短音频（≤5 分钟）提速可另评估 Flash 同步模型，作为可选优化，不改主链路。

## 后果
- 正面：一个模型覆盖 ASR + 分离，省掉独立分离服务；中文质量与热词满足会议场景。
- 负面：异步需轮询，出结果有数分钟排队；分离仅单声道，须 ffmpeg 下混。
- 后续需注意：① 分离结果为匿名 `speaker_id`，姓名化留 P3；② 开分离时音频建议 ≤2h，超长需分段。
