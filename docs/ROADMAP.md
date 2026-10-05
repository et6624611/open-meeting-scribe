---
title: 版本路线
description: 渐进构建路线图（版本主线），从 v1 云方案到本地数据·云端智能。零散需求与缺陷修复见 BACKLOG.md
author: Yongliang Wang
created_at: 2026-09-03
updated_at: 2026-09-24
version: "1.7.0"
status: published
---

# ROADMAP — 版本路线

> 渐进构建：先跑通最小链路，再叠加能力。呼应 MISSION「本地数据·云端智能」长期方向。
> 零散缺陷修复与体验优化条目见 [BACKLOG.md](BACKLOG.md)。
> 注：需求记录原建议本地引擎登记为 v8，因 v8（移动端消息流）/v9（Agent 角色系统）已先行占用，顺延为 **v10**。

## v1 · 云方案 ✅
**目标**：最快跑通「音频 → 纪要」，验证产品价值。
- ASR + 分离：DashScope `paraformer-v2`（云）
- 纪要：通义千问 `qwen-plus`（云）
- 采集：文件输入 + BlackHole 内录
- 界面：FastAPI 本地 Web UI
- 里程碑：P0 环境 → P1 CLI 链路 → P2 Web UI + 内录
- 依据：[ADR-0001](adr/0001-mvp走云方案.md)

## v2 · 本地兜底
**目标**：离线场景保底录音采集，联网后再完成识别与纪要生成。
- 本地仅负责录音采集与存储（复用 BlackHole 内录 + WAV 落盘）
- 识别、说话人分离、LLM 纪要生成均待联网后调用云端处理

## v3 · 声纹姓名化 ✅
**目标**：把「说话人1」变「张三」。
- 初版用 resemblyzer 提取 256 维声纹嵌入向量（GE2E 编码器，英文语料训练，判别力有限，需 cohort centering 补丁）
- 声纹注册表持久化（`data/voiceprint_registry.json`）
- 转写后自动匹配已注册说话人，无匹配时降级为手动绑定
- 说话人管理页显示声纹状态，支持注册/更新声纹

## v4 · CAM++ 声纹编码器升级 ✅
**目标**：把 GE2E 换成中文语料训练的 CAM++，抬判别力天花板，清掉旧版补丁。
- 编码器：CAM++（FunASR CAMPPlus 实现，ModelScope `iic/speech_campplus_sv_zh-cn_16k-common` 权重，28MB）
- 嵌入维度：256 → 192（L2 归一化）
- 注册表加 `model_version` 字段（当前 `cam++-v1`），旧版本记录匹配时自动忽略
- 移除 cohort centering / RAW_* 双阈值等 GE2E 时代的补丁代码
- **匹配算法升级**：逐人独立匹配 → per-meeting 统筹分配（中心化消除同会议信道公共分量 + 匈牙利算法保证一对一），接受准则改为仅看 margin
- 依赖：`resemblyzer` → `torch` + `torchaudio`
- 迁移脚本：`scripts/backfill_voiceprints.py` 全量重建注册表
- 评测：6 人会议对比测试，0 误识（旧方法虽 sim 高但含信道偏置，新方法更可靠）

## v3+ · 说话人分离精度增强 ✅
**目标**：解决本地 MFCC 聚类精度低、批管线 speaker_count 传递不完整导致的分离质量瓶颈。

### 短期（参数调优 + 链路补全） ✅
- **S1** ✅ `speaker_count` 全链路传递：文件上传路径增加自动估算（归一化→均匀采样→钳制到 1-10），前端可选手动指定
- **S2** ✅ 本地聚类人数下限保护：估算值钳制到 [1, 10]，避免噪声产生过多伪说话人
- **S3** ✅ 放松 `correct_speaker_ids` 后处理修正条件：夹心修正间隔 2000ms→800ms，碎片跟前句间隔 2000ms→500ms
- **S4** ✅ 聚类参数调优：相似度阈值 0.70→0.65（更严格区分），特征窗口 2s→1.5s（提升时间分辨率）

### 中期（特征升级）
- **M1** ✅ 实时聚类特征方案确定：曾升级至 CAM++ 192 维嵌入，后因云端拆分（v5）回退为 MFCC 14 维（实时侧纯本地，无 torch 依赖）
- **M2** 引入上下文连续性先验：相邻句子倾向同一说话人，减少跳变
- **M3** 自适应阈值：基于说话人间相似度分布动态调整聚类阈值

### 长期（混合方案）
- **L1** 批处理结果反向校准实时聚类参数，形成「实时粗估→批处理精修→参数回写」闭环
- **L2** 谱聚类（Spectral Clustering）替代在线贪心聚类，实现全局最优分割
- **L3** 声纹注册表辅助批处理修正：已注册说话人的声纹用于后处理验证/纠正 speaker_id

## v3++ · 说话人绑定体验闭环 ✅
**目标**：打通「实时绑定 → 批处理 → 自动识别」的完整体验，消除用户重复绑定的断裂感。
- **核心洞察**：实时绑定的文本内容是批处理后匹配说话人的最直接证据（确定性匹配），优于声纹的概率性匹配
- **实时转写全量保留**：新增 `realtime_full_transcripts` 字典，录音期间无上限累积所有定稿句子，突破 `REALTIME_BUFFER_MAX=10` 限制，持久化到任务 JSON
- **文本桥接匹配（P0）**：新增 `core/text_bridge.py`，基于 `difflib.SequenceMatcher` 字符级模糊匹配，按命中次数投票确定新 speaker_id
- **分层匹配策略**：P0 文本桥接 → P1 声纹匹配 → P2 手动绑定，在 `app/store.py:run_pipeline_task` 中按优先级依次执行
- **声纹自动更新**：自动匹配成功后立即调用 `register_from_binding` 更新声纹注册表，无需用户手动触发
- **时长加权**：`VoiceprintRecord` 新增 `total_sample_duration` 字段，`register_voiceprint()` 按音频时长加权累积平均
- **声纹采集用户感知**：绑定完成后 toast 提示、设置页显示声纹样本时长、自动匹配成功时说明依据
- 详细设计要求见 [BACKLOG.md](BACKLOG.md)「说话人绑定体验闭环」

## v5 · 声纹云端拆分 ✅
**目标**：将 CAM++ 声纹推理从主项目剥离，部署为独立云端服务，主项目彻底去掉 torch 依赖，为 Windows 打包瘦身。
- **云端服务**：CAM++ 192 维嵌入提取部署至云端（systemd 自启，RESTful API）
- **Provider 抽象层**：`core/embedding_provider.py` 统一接口，云端优先 → MFCC 降级
- **主项目清理**：删除 `LocalCamPlusProvider`、`extract_embedding_local()` 等本地 CAM++ 代码
- **依赖瘦身**：`requirements.txt` 移除 `torch` + `torchaudio`（~2GB → 0）
- **实时侧**：`core/diarization.py` 纯 MFCC 聚类（numpy + scipy），无 torch
- **配置**：`data/settings.json` 新增 `voiceprint` 配置节（provider / base_url / api_key）
- **兼容性**：云端 `cam++-v1-cloud` 与本地 `cam++-v1` 声纹注册表互相兼容
- 依据：[ADR-0009](adr/0009-声纹识别服务云端拆分.md)

## v6 · Windows 打包分发 ✅
**目标**：将 open-meeting-scribe 打包为 Windows 可执行程序，让同事无需安装 Python 即可使用。

### P0（基础打包）✅
- **PyInstaller 打包**：✅ 主项目 + 前端静态文件打包为单文件 .exe
- **ffmpeg 内置**：✅ 通过 CI 自动下载 ffmpeg 二进制
- **启动器**：✅ 双击启动本地 Web 服务 + pywebview 原生窗口（`desktop.py`）
- **配置文件**：✅ 首次运行生成 `.env`，引导用户填入 DashScope API Key

### P1（体验优化）
- **系统托盘**：最小化到托盘，不占任务栏
- **自动更新**：✅ 已完成。版本检查 + 更新提示（`core/version_check.py`）
- **安装向导**：✅ 已完成。Inno Setup 安装包（`build/installer.iss`），自动创建桌面快捷方式，升级时保留用户数据
- **短信代理改造**：✅ 已完成。`core/sms.py` 改为 HTTP 调用云端代理，阿里云 AccessKey 从 .env 移除，密钥不落地

### 约束
- 目标包体 ≤ 300MB（去掉 torch 后依赖约 200MB + ffmpeg 约 80MB）
- 支持 Windows 10/11 x64
- 声纹识别走云端，本地不跑推理

## v7 · 产品介绍页
**目标**：搭建一个对外展示产品的 Web 页面，让潜在用户快速了解会议助手的核心价值与使用方式。
- 单页静态站点，可独立部署（GitHub Pages / 云服务器均可）
- 内容：产品定位、核心功能亮点（实时转写、说话人识别、AI 纪要）、使用流程、截图/动图演示
- 风格：简洁轻量，移动端适配
- 与技术文档站（RepoWiki）分离，面向非技术用户

## v8 · 移动端消息流
**目标**：让用户通过自选消息应用（Telegram / Bark / ntfy 等）远程监控会议状态、随记、接收超时告警，无需独立移动端面板。
- Webhook 消息流：服务通过 HTTP POST 推送通知到用户配置的通道，零运营成本
- 会话锚点模型：`@会议名` 前缀 + `/switch` 指令解决多会议上下文
- 通知事件：录音开始/停止、静默告警、自动关停、转写/纪要完成
- 上行交互：复用 `chat.py` AI 对话逻辑，支持查询状态、随记、切换会议
- 推荐通道：Telegram Bot（天然双向、免费、无需公网）
- 详细设计见 [MOBILE_DESIGN.md](design/MOBILE_DESIGN.md)
- 依据：[ADR-0014](adr/0014-移动端走Webhook消息流.md)

## v9 · Agent 角色系统 ✅
**目标**：将 AI 行为从硬编码提示词迁移到基于 .md 文件的角色工作区，支持预定义角色开箱即用、用户 fork 自定义、全局激活切换。
- **角色文件化**：4 个硬编码 Python 常量 → `data/agent/_roles/_builtin/{name}/AGENT.md` + 附带 `.md` 文件
- **5 个预定义角色**：会议纪要员、会议分析师、会议引导师、学习辅导员、深度阅读者
- **用户自定义**：从预定义角色 fork → 编辑 `.md` 文件 → 实时生效
- **全局持久化**：激活角色写入 `settings.json` 的 `active_agent`，刷新/重启保持
- **核心模块**：`core/agent_workspace.py`（角色加载/fork/save/delete）+ `app/routers/agent.py`（REST API）
- **前端**：`AgentsView.vue`（角色管理 UI）+ `stores/agent.ts`（Pinia store）
- 依据：[ADR-0017](adr/0017-agent角色系统从硬编码提示词到md工作区.md)，设计详情见 [AGENT_ROLE_SYSTEM.md](design/AGENT_ROLE_SYSTEM.md)

## v10 · 本地可选计算引擎（离线模式）🚧
**目标**：让「数据永不出设备」从主张变为可验证事实——新增全本地引擎选项（FunASR ASR + LLM 自接端点 + 声纹本地化），兑现并强化 ADR-0015 本地数据主权原则。
- **立项**：P0 战略级（D3 裁决，2026-09-23），GitHub 转 Public 前最后一个功能里程碑
- **决策链**：[ADR-0018](adr/0018-本地可选计算引擎与声纹离线化.md)、[需求记录](REQUIREMENT_LOCAL_ENGINE.md)、[PRD-LOCAL-ENGINE](PRD-LOCAL-ENGINE.md)（D-R1 全家桶 ≈2.0GB / D-R3 引导下载+外置引擎目录，均已裁决；Spike 报告存内部归档）
- **首轮派工（2026-09-23 已入库 main）**：
  - WP-A（R4 LLM 自接增强）✅ `c2a1272` 等；含 §7.2-4/5 本地引擎自动探测与状态栏三态
  - WP-B R5（模型下载器 + 常驻引擎子进程后端）✅ `c05c198`；WP-B R6（引擎徽章 + 数据流向矩阵 UI，D-R2 管理员级）✅ `d30ddee`
  - WP-C（AC-2 评测体系）✅ `830ddc1..cf6f0e7`——本地 vs 云 WER、多说话人 DER、LLM 规格实验（推荐 qwen3:8b、下限 4b）；发现并修复 AC-6 跨端 CMN 缺陷 ✅ `0788390`（回归 PASS：跨端 cos 1.0、EER 0）
  - WP-D（Windows 冻结 CI + AC-7 云包体积守护）✅ `feed200` ⚠️ 2026-09-24 更正：其 workflow 实际从未跑绿，见下方「已知缺陷」
- **第二轮派工（2026-09-24，经项目方批准推送）**：
  - WP-E（R1/R2 主干接线 + R3 声纹离线化 + AC-4 分类化回退 `LocalEngineError(can_fallback_cloud)`）✅ `20dee6d..74a1281`：27 例契约/回退打桩，HEAD 全量回归 260 passed
  - WP-F（R5 模型管理前端 UI：清单/下载/引导弹窗/降级横幅）✅ `aaaaa958`
- **WP-G 派工（2026-09-24，派工说明内部归档）**：R8 打包首启引导——onedir 冻结代码包 + 外置引擎目录分离（D-R3）、Windows Inno Setup「本地引擎组件」可选安装、冻结应用内首启引导接 WP-F UI、CI 增 local 链路冒烟（替身权重，禁真实下载）。Windows 侧 AC-1 真机验收依赖本包产物
  - ⚠️ **2026-09-24 更正：原登记「依赖：无新决策阻塞」不成立**。盘点打包链路时发现 3 个冻结态必踩缺陷 + 2 个阻塞性决策，**G-1 开工前需项目方拍板**：
    - **D-G1 引擎可执行体形态（阻塞）**：`core/engine_host.py:55` 冻结态按「同主 exe 再入 `<exe> --engine-worker`」拉起（`desktop.py:335` 分派已就绪），但 `build/pyinstaller.spec:103` 显式 `excludes=['torch','torchaudio']` —— 主包内无 funasr/torch，**冻结态本地引擎必然启动失败**；而把 torch 放回主包直接违反 R8/AC-7「否决内置云精简主包」。建议采纳**独立引擎包**（新增 `pyinstaller_engine.spec`，主包 spec 不动），并否决「条件打包」
    - **D-G3 Windows 组件可写锚点（阻塞政企离线路径）**：Inno 默认装 `Program Files`（非管理员不可写），但权重/日志/ModelScope 缓存均需可写；建议引擎运行时数据落 `%LOCALAPPDATA%`。连带 `core/model_registry.py:81-90` 相对路径 `data/models/` 在冻结态会指进只读 bundle（`engine_host.py:137` cwd 取 `__file__` 父级），须改平台锚点（对照 `core/audio.py:44` 的 ffmpeg 写法）
    - **B-3 排障可见性**：`engine_host.py:133` `stderr=DEVNULL` 丢弃引擎侧错误输出，冻结首启（funasr import 最高 86s、spawn 重复引导 5–6 次）失败时用户只看到 `engine_unhealthy`。WP-G 期间必须收进任务日志（对齐 AC-8）
- **WP-H 立项（2026-09-24，本地模式实时链路口径收口）**：范围严格限定三件，与 WP-G 解耦以免拖住打包排期——
  1. **超时天花板**：`core/engine_host.py:31` `ENGINE_REQUEST_TIMEOUT=180s` 为单请求上限，按 Spike RTF≈0.081 反推音频 >~37 分钟必超时；本地模式 `can_fallback_cloud=False` → **整场转写失败、录音白录**。需按承诺的最长会议时长重算（长音频分片续跑或调上限 + 进度可见），并给出「云包不受影响」的验证
  2. **降级语气错位**：`app/routers/record.py:466-477` 把设计内降级当异常兜住，推 `type:"error"` 消息，与同页降级横幅（`RecTranscriptPanel.vue:65`）自相矛盾，读起来像故障。应改为非错误的状态声明
  3. **文案与行为不一致 → 2026-09-24 项目方裁决：取方案 B（真做分段增量上屏），不改文案回退**。现状是「录音期间完全不出稿、结束后一次性全量批处理」（`core/realtime_asr.py:222-233` 抛 `realtime_degraded_to_batch`），而横幅与 PRD 非目标节写的是「分段批处理输出」。落地定义与待裁决点见 [REQ-LOCAL-REALTIME-INCR](REQUIREMENT-LOCAL-REALTIME-INCR.md)（候选新条目 R9 + AC-9）。⚠️ 空窗期口径处理见该记录 §8：**WP-I 验收通过前，用户可见文案须先收敛为如实描述**，不得按 B 提前承诺
  - 判据（WP-H 第 1/2 项）：超时口径与实际支持的最长会议时长一致且失败可恢复不丢录音；`record.py` 降级路径不再推 `type:"error"`，与横幅/状态声明口径统一
- **WP-I 派工（2026-09-24，承接方案 B 裁决）**：本地引擎分段增量上屏（段级近实时，逐字级流式仍为非目标）。范围 = 会中分段推理上屏 + 段间 speaker 一致性 + 逐段热词 + 定稿一致性
  - **强前置**：D-G1（引擎包形态）未拍板前只能在 venv 内开发，无真机交付路径；D-I1（单段失败不得连带重启常驻引擎）、D-I2（建议「增量段拼接即定稿」，选它则 WP-H 第 1 项超时问题自然消解、范围收窄到导入音频路径）、D-I3（段长策略先实测后定）
  - **复用而非新建**：PCM 流与双喂链路现成（`core/audio_recording.py:532`、`record.py:332-334`）；说话人身份唯一事实源建议走既有增量聚类 `core/diarization_cluster.py`，**不可**跨段使用 FunASR 的局部 `spk` 编号（`engine_worker.py:148-156` 每次 generate 独立编号）
  - **优先级建议 P1**（不阻塞 AC-1 断网闭环发布；「数据不出设备」主张现状已成立）——改判 P0 则 v10 里程碑与验收排期需同步重排
  - 已知风险：引擎请求全局锁串行且超时即判 unhealthy（`engine_host.py:174-201`）、ct-punc 可选致段边界粘连文本（与「真机验收标点降级」并项实测）、会中推理与采集的 CPU 争用在 4 核 Windows 上无数据
- **真机断网验收（与 WP-G 并行，macOS 先行）**：Spike venv + 真实权重，AC-1/2/3/6 清单见 WP-E 测试 docstring；重点 = 真实 WER/耗时（AC-2/3）、ct-punc 缺省下标点降级、AC-1 抓包白名单（顺带产出 AC-5 一致性证据）。若 ct-punc 降级不可接受 → 触发「可选转必装 ≈3.0GB 超 AC-3 预算需评审」或「接受降级 + 文档标注」决策，先实测后议。⚠️ 验收用例须含 ≥30 分钟样本（覆盖 WP-H 第 1 项）且**不得用 venv 冒替冻结包**
- **已知缺陷（登记待查，2026-09-24 证据更新）**：`ci-local-engine.yml` 全部 6 次运行 0s 失败、0 jobs（主 CI ubuntu 不受影响）。新增关键症状：**在仅触及 `docs/**` + `frontend/**` 的 push 上仍然触发**，即其 `on.push.paths` 白名单未被执行——与「`gh workflow list` 显示文件路径而非 `name`」同属 **workflow 元数据层未被读取**，问题不在 jobs/steps 层。已排除：YAML 解析通过、无重复键、无 tab、无 CRLF、无 BOM、无非换行控制字符、UTF-8 解码干净。**修正后动作序（低→高成本）**：① 先试强制重注册（改名 `ci-local-engine-v2.yml` 或删除后重加，观察 `name` 是否恢复）；② 仍 0 jobs 再做单 job 最小 workflow 二分（砍 `concurrency` 表达式 `:55-57`、非 dispatch 下引用 `inputs.freeze_smoke` 的 job `if` `:63-66`、job name 改 ASCII）；③ 若确认账号侧 Windows runner/metered 限制 → 走账号处置并把 local 冒烟临时降级 macOS-only，同步更新 AC-7 覆盖说明。详见派工说明 §5（内部归档）。后果与分工不变：AC-7 体积守护与 Windows 冻结冒烟当前无 CI 覆盖，WP-D 验收项「Windows CI 绿灯」复核未通过；**G-6 在根因定位前不占主线排期**，WP-G G-1~G-5 可先推进，真机阶段以人工冒烟兜验证缺口
- **剩余范围**：R8 打包首启引导 + **双平台一键安装**（WP-G，D-G1~D-G5 已裁决、已派工 DevOps；**mac L1 待 Apple 开发者凭据**）、WP-H 本地模式超时与降级口径收口（已派工后端）、WP-I 分段增量上屏（D-I1~D-I4 已裁决、已派工后端，P1 不阻塞发布）、`ci-local-engine.yml` 根因（已派工 DevOps）、AC-1 断网闭环 / AC-4 可回退 / **AC-10 一键安装**真机验收（mac + Win，待项目方给时间窗）
- **新增外部依赖（2026-09-24 D-G4 加码带出）**：macOS 一键安装 L1 层需 **Apple Developer Program 账号（约 $99/年）+ Developer ID `.p12` + notary API key**，由项目方提供并托管为 GitHub Secrets；`build-macos.yml` 现全链无 codesign/notarize（`:116` 裸 ZIP → `:124` 上传）。凭据未到位期间，README / 发布材料只能声明「macOS 支持应用内一键安装本地引擎组件」，不得声明 macOS 一键安装
- **D-R4 让渡清单（2026-09-24 项目方口头授权"听你的/继续"暂定采纳，待正式批准）**：建议让渡——v7 产品介绍页、v8 移动端消息流、BACKLOG 中期/长期分离优化项（M2/M3/L1-L3）；不让渡——进行中的笔记/决策流/知识库 WIP 与在途缺陷修复（与 v10 无资源冲突，可并行）
### v10 第三轮派工单（2026-09-24 · 决策已锁定 · **owner 已指派，工单已下发**）

**决策授权性质（必须先看）**：项目方 2026-09-24 给出 blanket 授权「我没答复的都按你给出的建议执行」，同轮**明确补充「包括指派工程师」**。据此：D-G1~D-G5、D-I1~D-I4 由产品经理按建议值代理裁决采纳，并已点名派工至本数字员工团队的具体工程师（见 owner 列）。代理裁决**不等于项目方逐项亲口拍板**；取值依据与回退方式见 WP-G 派工说明 §3（内部归档）、[R9 需求记录 §6](REQUIREMENT-LOCAL-REALTIME-INCR.md)。实施侧判定建议值技术不可行 → **回报产品，不得静默变通**。

**本轮唯一被项目方亲口推翻的取值：D-G4** —— 原「macOS 走 zip 引导下载、不做 pkg/dmg」作废，改为 **「macOS 与 Windows 均要支持一键安装」**，R8 分发拆为 L1 主应用安装包 / L2 引擎组件落位两层，新增 **AC-10**（详见 PRD v1.5.0 §R8、§10）。

| 工单 | Owner | 锁定决策 | 开工序 | 验收物 | 建议分支 |
|---|---|---|---|---|---|
| **WP-G** R8 打包 + **双平台一键安装** | **DevOps 工程师** `78087de278c8`（proj_dfdc01e7） | D-G1 独立引擎包（否决条件打包）；D-G3 运行时数据锚 `%LOCALAPPDATA%`（Win）/ `~/Library/Application Support/`（mac）；**D-G4 已推翻 → 双平台一键安装，分 L1（Win Inno / mac `.dmg`+Developer ID 签名+公证）与 L2（引擎组件应用内一键落位）两层**；D-G5 首启进度态为产品要求 | G-1 → G-2 → {G-3, **G-4**, **G-4b(mac 组件一键落位)**, G-5 并行} → G-6；**G-7（mac 签名公证链路）**脚本可与 G-2 并行，但**无 Apple 凭据不得声称完成**；G-6 与 CI 缺陷排查并行启动 | 双平台冻结包 AC-1 全流程 + AC-7 三重守护绿灯 + 组件三态截图 + **AC-10 L2 双平台绿灯**（L1 视凭据到位情况） | `task/local-engine-wpg-<date>` |
| **WP-H** 超时与降级口径 | **后端工程师** `a4cdbd0ca795`（proj_282b7189） | 超时项范围收窄至「导入音频 / 非实时长文件路径」（因 D-I2 选增量即定稿，实时链路自然消解）；降级消息不再推 `type:"error"` | 可与 WP-G 并行（不依赖包形态） | 长文件转写不整场失败 + 降级为非错误状态声明；口径与实际支持时长一致 | `fix/local-engine-wph-<date>` |
| **WP-I** R9 分段增量上屏 | **后端工程师** `a4cdbd0ca795`（引擎/定稿链路）；会中上屏 UI 增量改动待引擎侧接口稳定后由产品追加派给**前端开发工程师** `d1b77737cde5` | D-I1 单段失败不重启引擎；D-I2 增量段拼接即定稿；D-I3 段长**不定数值**（实现为可配置，真机 20s/60s 各一场带回延迟分布再定默认）；D-I4 **P1**（不阻塞 AC-1 发布） | **强前置 = WP-G 的 G-2/G-3**（冻结包无引擎可执行体则无真机交付路径）；venv 内开发可提前 | AC-9 全项（P95 ≤20s、说话人整场不跳变、会中=定稿、60 分钟不整场失败、单段失败不刷屏） | `task/local-engine-r9-<date>` |
| **CI 缺陷** | **DevOps 工程师** `78087de278c8`（与 WP-G 同 owner，G-6 共用） | — | 立即 | `ci-local-engine.yml` 首次绿灯，或改判 macOS-only 冒烟并更新 AC-7 覆盖说明 | `fix/ci-local-engine-<date>` |
| **空窗期文案** | 产品经理 `54220bf95076`（已执行·本批） | 已完成 | 已完成 | 横幅中英文收敛为如实描述「录音期间暂不出稿、结束后本机转写」；WP-I 验收同版本再切增量口径。i18n key 未改名 | 本批随派工单一并入库 |

**仍需项目方提供、产品与工程师都无法自行解决的外部前提**：

1. ~~**Apple Developer Program 账号与签名/公证凭据**~~ → **2026-09-24 项目方裁决「暂时不考虑 Apple 开发者账号与凭据」，本条移出 v10**。后果：mac 侧 L1（`.dmg` + 签名 + 公证）与 WP-G 的 G-7 转 DEFERRED；**v10 对外口径固定为「macOS 支持应用内一键安装本地引擎组件」，不得写「macOS 一键安装」**（详见 AC-10 与 PRD §12）。
2. **真机断网验收时间窗**：~~待项目方给时间窗后派 QA~~ → **项目方 2026-09-24 批准派发，已派至 QA 工程师（见下方派工执行记录）**。**仍需项目方指定人补两项 QA 无法替代的动作**：① AC-2 人工听校回填 `refs/SEG-*_human_ref.txt`（53/59/78 句不确定项，工作表已在 WP-C 交付）；② 提供可用于断网测试的 ≥30 分钟真实会议音频样本（现 `samples/` 仅 1 段）。
3. **R9 判级复核**：现按 **P1**（不阻塞 v10 发布）。若改判 P0，会牵动 v10 里程碑与 AC-1 验收排期，且必须让 WP-G 的 D-G1 先落地。

**派工执行记录（2026-09-24）**：已按上表 owner 通过 QoderWake 平台下发工作 Session，两条均已 `running`：

| 工单 | Owner | Session ID | 下发时刻 |
|---|---|---|---|
| WP-G + CI 缺陷 | DevOps 工程师 `78087de278c8` | `553f0b93-cff3-4aec-b096-82e3f33e1cbb` | 2026-09-24 02:03 UTC |
| WP-H + WP-I | 后端工程师 `a4cdbd0ca795` | `c3d2ebf4-9935-4843-ab25-5b00d2a0a780` | 2026-09-24 02:03 UTC |
| **QA-R1 真机断网验收（第一轮·现状形态）** | **QA 工程师** `365d21fa11a0`（proj_80ccedbb） | `b8ce872e-89b6-4dbb-aa22-3a58bcb8beba` | 2026-09-24 02:43 UTC |
| **QA-R1 缺陷修复（后端：DEF-01 P0 / DEF-03 / DEF-04 端点 / DEF-02 生成）** | **后端工程师** `a4cdbd0ca795`（proj_282b7189） | `4bf68bed-cdc4-41e4-9c19-2056c5c0c9ab` | 2026-09-24 07:40 UTC |
| **QA-R1 缺陷修复（前端：DEF-04 回退 UI 与置灰 / DEF-02 导出入口）** | **前端开发工程师** `d1b77737cde5`（proj_f492f6c0） | `df6f3571-6993-4e80-b77a-9074a9de5024` | 2026-09-24 07:40 UTC |

**QA-R1 第一轮结论与派工裁决（2026-09-24，产品确认）**：QA-R1 总判定 **FAIL**（AC-3/AC-6 通过；AC-1/AC-4/AC-5 不达标；AC-2 blocked-on-human），报告已入库（分支 `qa/local-engine-r1-20260924` @ `854be3a`，按项目方指令**修复后再 push**）。缺陷修复任务书内部归档。项目方裁决：①可以派工（已下发上表两条 Session）；②**本轮以 macOS 跑通为准，Windows 真机项顺延下一环节**；③修复完成前不 push。产品裁决：docx 保留在 v10 范围（不收敛 AC-1 口径）；AC-5 承诺口径收敛为「运行期零非 localhost 出网（含加载期），模型首次获取需联网」；**AC-2 人工听校人仍待项目方指定**（移交单：`tests/eval_local_engine/QA-R1-AC2-HUMAN-PROOFREAD-HANDOFF.md`）。

**QA-R1 范围口径**：本轮判 **AC-1（venv 形态）/ AC-2 / AC-3 / AC-4 / AC-5 / AC-6 真机复测**；**AC-7 / AC-9 / AC-10 本轮不判**（依赖 WP-G/WP-I 交付，留第二轮）。所有证据须标注「venv 形态，未经冻结包验证」，两轮结论不得混写；Windows 侧若无可用真机须标 `blocked-on-hardware`，禁止用 macOS 结论顶替。

**CI 缺陷执行进展（2026-09-24 派发后 40 分钟内，DevOps 已推 main 三 commit，根因已定位）**：
- `3ef7ce4` 按动作序①改名 `ci-local-engine.yml` → `ci-local-engine-v2.yml` 强制重注册（观察）
- `fe8e41a` **真实根因（dispatch 422 实证）**：`jobs.windows-freeze-smoke.env` 里的 `${{ runner.temp }}` 在 job 级 env 位置不被表达式解析器接受（`Unrecognized named-value: 'runner'`）→ **整个 workflow 编译失败**。该单因完整解释全部存量症状：`gh workflow list` 显示路径而非 `name`、`on.push.paths` 过滤不生效、运行 0s / 0 jobs / 无 annotations。修复=改由首个 step 从 `RUNNER_TEMP` 写入 `GITHUB_ENV`，job 级 env 只留字面量
- `39ee533` 冒烟首次真实运行（4m+）暴露的两个内容级缺陷：Windows cp1252 控制台中文 print 崩溃 → 三脚本显式 reconfigure UTF-8；AC-7 冻结图扫描误报（PowerShell 文本 grep 把 spec 的 `excludes=['torch',…]` 判为侵入）→ 改 `toc_scan.py` 结构化解析 TOC 条目
- **验证状态（诚实标注）**：`gh workflow list` 已恢复显示 `CI Local Engine`（元数据层已解析），运行时长从 0s 变为 4m+，即**编译层已通**；但 `fe8e41a` 那次运行仍 `failure`，`39ee533` 触发的运行截至本条登记仍 `in_progress`。**AC-7 体积守护与 Windows 冻结冒烟尚无为绿灯证据，本条缺陷保持「已定位、修复待验证」，不提前关单。**
- **§5 原三步排查计划已被实际根因取代**：无需再走最小 workflow 二分，也无需降级 macOS-only；`ci-local-engine.yml` 的旧文件名引用一律以 `ci-local-engine-v2.yml` 为准。

本表与派工说明为唯一口径来源，工程师若判定建议值技术不可行须回报产品，不得静默变通。

**⚠️ 已识别的执行期风险（产品侧登记，处置已下发）**：两条 Session 的 CWD 相同（同一工作副本 `open-meeting-scribe`）。两包各自切分支会互相踩工作区，且工作区已有 6 个他人 WIP 文件未提交。**处置**：已向两条 Session 各补发纪律消息，要求在 `../oms-wt-wpg` / `../oms-wt-wph` 等独立 git worktree 内写代码与提交，禁止在当前工作目录直接切分支；CI 缺陷与 WP-I 各自另开 worktree。


## 待定 / 想法池
- **产品战略：跨平台中立枢纽闭环**：会议软件与转录工具分属两个生态，接缝在会前上下文 / 会中采集 / 会后回流三处。闭环方向**不是**接入平台开放 API 做深度集成（违背「反生态锁定」使命、自降为附庸），而是做中立枢纽——上游靠「项目」机制补上下文、会中靠主动型 AI 基于音频流越界、下游多路回流协作生态。让会议软件始终是「可替换音频源之一」、协作工具是「可分发下游之一」。详见 [PRD.md](PRD.md)「生态闭环：做跨平台的中立枢纽」章节
- **产品战略：从会议助理到主动型 AI**：当前产品是被动式记录工具，未来应向主动型 AI 转变——AI 识别会议中的卡壳、偏题并主动介入提供解决方案，产出以折叠未读卡片形式呈现并与时间轴关联。详见 [PRD.md](PRD.md)「演进方向」章节
- **企业化核心洞察**：更大上下文 → 更有效决策。企业场景下 AI 能基于更丰富的背景资料、历史决策、参与人关系提供价值；用户参与编辑（如摘要编辑）提升对产出的置信度
- 运行时性能监控：关键路径耗时埋点（管线、ASR、LLM、ffmpeg、声纹）+ cProfile 热点分析 + HTTP 中间件请求计时，定位瓶颈
- 短音频走 Flash 同步模型提速
- 多语种会议
- 纪要模板（不同会议类型）
- 导出到企业微信文档 / 邮件（下游回流，属「中立枢纽闭环」的会后一环）
