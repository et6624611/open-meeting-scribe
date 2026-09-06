# GLOSSARY — 术语表

> 统一口径，避免文档/代码/AI 对话各说各话。

| 术语 | 含义 |
|------|------|
| ASR | 自动语音识别，声音 → 文字 |
| 说话人分离 / diarization | 区分「哪句是谁说的」，输出匿名 `speaker_id`（0/1/2…） |
| 声纹 / voiceprint | 从声音提取的身份向量（CAM++ 192维嵌入），用于把 `speaker_id` 映射成真实姓名（v4 ✅） |
| 热词 / hotword | 企业人名、术语等专有名词，转写时加权纠偏（`vocabulary_id`） |
| 逐字稿 / 口水稿 | ASR 原始输出，含语气词、重复、口语化 |
| 纪要 | LLM 加工后的结构化产物：结论 + 待办 + 议题 |
| 待办 | 行动项，含「谁 / 做什么 / 截止」 |
| DashScope | 阿里云百炼模型服务平台，本项目 ASR 与纪要的统一入口 |
| paraformer-v2 | DashScope 录音文件识别模型，支持分离与热词 |
| 通义千问 / qwen | DashScope 的 LLM，本项目用于纪要生成 |
| 临时 URL / `oss://` | DashScope 免费临时存储换取的音频地址，≤1GB / 48h |
| BlackHole | macOS 虚拟音频设备，用于内录系统声音 |
| 内录 | 采集系统播放的声音（线上会议），区别于麦克风采集 |
| MPS | Apple Silicon 的 PyTorch 加速后端（v2 本地方案才涉及） |
