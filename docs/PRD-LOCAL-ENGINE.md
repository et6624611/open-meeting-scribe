---
title: PRD — 本地可选计算引擎（离线模式）
description: 本地 ASR + 声纹离线化 + LLM 自接端点，实现断网全闭环，作为 GitHub 开源前 P0 里程碑
tags: ["prd", "offline", "funasr", "camplus", "ollama"]
author: 产品经理（AI 起草，待项目方评审）
created_at: 2026-09-23
version: "1.5.1"
status: active (D-R1/D-R2/D-R3 已裁决采纳；2026-09-24 方案 B 裁决 → 新增 R9/AC-9；D-G4 项目方推翻 → 双平台一键安装，新增 AC-10；Apple 凭据暂缓 → mac L1 与 G-7 移出 v10；四包 + QA-R1 已派工)
changes_1_5_1: "项目方裁决「暂不考虑 Apple 开发者账号与凭据」→ mac L1/G-7 转 DEFERRED，AC-10 v10 判定范围收敛为 mac L2 + Win L1；登记 QA-R1 真机断网验收第一轮范围与 CI 根因修复进展"
changes_1_5_0: "D-G4 反转：macOS 与 Windows 均须一键安装，R8 拆 L1/L2 两层；新增 AC-10 与 Apple 签名/公证外部成本；§12/§13 记录指派工程师授权与具名 owner"
changes_1_4_0: "R9 分段增量上屏入范围（非目标节 §6 拆分改写）；更正 §12「无阻塞决策点残留」旧结论；登记 WP-G/H/I 前置决策"
requirement: docs/REQUIREMENT_LOCAL_ENGINE.md (v0.3.0, approved-p0)
adr: docs/adr/0018-本地可选计算引擎与声纹离线化.md (Proposed)
spike: 内部归档（不随公开仓库发布）
---

# PRD: 本地可选计算引擎（离线模式）

## 1. Summary

为 Open Meeting Scribe 计算能力层新增**可选本地引擎**：转写/说话人分离由本地 FunASR 承担，声纹注册与匹配回归本地 CAM++，纪要 LLM 由用户自接 OpenAI 兼容端点（Ollama / LM Studio）。默认引擎与云模式行为完全不变。目标：断网环境下完成「录音 → 转写 → 分离 → 声纹姓名化 → 纪要 → 导出」全闭环，使「数据永不出设备」成为可验证事实。P0，开源发布前最后功能里程碑（决策 D1/D2/D3 见需求记录）。

## 2. Background and Evidence

- **合规叙事**：ADR-0015 承诺业务数据永不落地，但现状录音必须上传云端转写与声纹比对；本 PRD 补上"数据不出设备"证据链。
- **市场**：品类第一心智 = 100% 本地（Meetily 31,044★，2026-09-23 实测）；本项目云依赖将全球采用天花板压至 500 星级；补离线能力后预期提升至 5k–10k 级。
- **技术前提**：
  - ASR 已有 `cloud | proxy | direct` 三模式抽象（`core/transcribe.py:_get_asr_mode`），新增 `local` 是自然扩展点；
  - 声纹已有 `EmbeddingProvider` Protocol（`core/embedding_provider.py`：`CloudEmbeddingProvider` / `MfccFallbackProvider`），历史上存在过 `LocalCamPlusProvider`（ADR-0009 时移除），注册表设计为云/本地双向兼容；
  - LLM 通道已是 OpenAI 兼容实现（`core/llm.py:chat_completion`，base_url 可配），设置页已有 `PROVIDER_PRESETS` 与「自定义」入口——**D1 的 LLM 侧主要是预设补齐 + 连通性测试 + 空 Key 容错，而非新建通道**。
- **来源**：[REQUIREMENT_LOCAL_ENGINE.md](REQUIREMENT_LOCAL_ENGINE.md)、[ADR-0018](adr/0018-本地可选计算引擎与声纹离线化.md)、[ADR-0009](adr/0009-声纹识别服务云端拆分.md)、竞品调研记录（2026-09-23）。

## 3. Goal and Success Criteria

**产品目标**：零云端账号、零 API Key 的用户（或完全断网的内网用户）能完成核心价值交付：结构化会议纪要。

| 成功指标 | 目标 |
|---|---|
| 断网全闭环（验收标准 AC-1） | 双平台通过 |
| 本地引擎激活用户占比（发布后 90 天） | ≥15% |
| 本地 vs 云端纪要"重生成/回云率" | ≤30% |
| 模型首次下载完成率 | ≥85% |
| README「offline」进入路径 → Star 转化 | 验证期观察，无硬指标 |

## 4. Users and Scenarios

| 用户段 | 场景 | 关键诉求 |
|---|---|---|
| 涉密行业（法务/财务/政企） | 内网办公机，物理断网或禁出网 | 零出网可证明（抓包/防火墙可验证） |
| 国际开发者/隐私敏感个人 | clone → 装 → 试 | 不注册阿里云；Ollama 自接即出纪要 |
| GitHub 首次访问者 | 下载桌面端评估 | 首启能跑通核心链路，不被配 Key 劝退 |
| 存量云端用户 | 混合工作流 | 默认行为零变化；离线录的会联网后可"云端提质"重转写 |

## 5. Scope

### In Scope（对应 R1–R9，见 §8）

1. ASR 模式扩展 `local`（批处理链路）+ 本地分离。
2. 声纹本地化：`LocalCamPlusProvider`（CAM++ 28MB）回归，注册表双向零迁移。
3. LLM 自接增强：Ollama / LM Studio 预设、连通性测试、空 Key 容错、小模型提示词降级档。
4. 模型资产管理：引导下载（进度/校验/断点续传/可取消）+ 内网离线拷贝路径。
5. 引擎状态透明：全局引擎标识 + 数据流向矩阵（README/SECURITY 同步）。
6. 失败回退 + 云端提质重转写。
7. 分发：云精简包维持现状；本地引擎为可选组件；CI 增本地链路冒烟。
8. 本地模式分段增量上屏（R9，2026-09-24 方案 B 裁决入范围；逐字级流式仍为非目标）。

### 依赖

- ~~D-R1~~ **已采纳（2026-09-23，Spike §2 内部归档）**：全家桶四模型 = seaco-paraformer-zh（944MB）+ fsmn-vad（3.9MB）+ ct-punc（1.0GB，**可选项**，唯一可裁剪大件）+ cam++（28MB，说话人分离与声纹 R3 **共用同一份权重**）；总下载 ≈2.0GB，AC-3 预算内。
- ModelScope 权重许可逐模型核查（引导下载不内置分发）。
- 现有设置面：`app/routers/settings.py`、`data/settings.json`；转写：`core/transcribe.py`、`core/pipeline.py`；声纹：`core/embedding_provider.py`、`core/voiceprint.py`；LLM：`core/llm.py`。

## 6. Non-Goals

- 不做端侧训练/微调；不内置大模型（Ollama 用户自装）。
- ~~本地模式实时流式转写不做云端同级体验：实时链路降级为分段批处理（显性声明），实时聚类维持 MFCC 本地降级，不为实时侧恢复 torch。~~ **2026-09-24 修订（项目方裁决方案 B）**：本条中捆在一起的两件事拆开——① **逐字级流式识别仍为非目标**（不承诺、不排期）；② 「分段增量上屏」**不再是降级、升格为 In Scope**（见 R9 / [REQUIREMENT-LOCAL-REALTIME-INCR.md](REQUIREMENT-LOCAL-REALTIME-INCR.md)）。实时聚类维持 MFCC 本地降级、不为实时侧恢复 torch 两条约束**不变**。
- 云模式声纹架构不动（voiceprint-service 维持 ADR-0009）。
- 不做 CUDA/多硬件加速矩阵（基线：Apple Silicon + CPU；CUDA 为机会性支持不承诺）。
- 不改默认引擎、不改 AGPL 许可证、不做订阅化。

## 7. User Flow

### 7.1 主路径：设置并启用本地引擎

1. 入口：设置 → 计算引擎（新 Tab；现有 ASR/LLM/声纹设置的重组落位）。
2. 选择「本地引擎（离线）」→ 弹出组件依赖检查：本地引擎组件未安装 → 引导安装（可选组件下载，见 R8）；已安装 → 展示模型清单（名称/体积/许可）→「下载全部」或逐个下载（进度条、可暂停/取消、SHA256 校验、断点续传）。
3. 下载完成 → 卡片状态变「就绪」→ 切换生效，全局引擎徽章变「本地」。
4. 返回录音页即可正常开会，全流程不出网。

### 7.2 LLM 自接（云模式用户亦可用）

1. 计算引擎 Tab → LLM 区块 → 预设下拉新增「Ollama（本地）」「LM Studio（本地）」（base_url 预填 `http://localhost:11434/v1` / `http://localhost:1234/v1`，Key 可留空）。
2. 「测试连接」按钮：发一条最小 chat 请求，展示延迟与模型可达性；失败给出可行动排错文案（服务未启动/CORS/模型未拉取）。
3. 测试通过前允许保存但纪要生成按钮侧给出醒目提示。
4. **本地引擎自动探测（辅助配置）**：进入设置页时后台 `GET http://localhost:11434/v1/models`（及 LM Studio `:1234/v1/models`，超时 ≤2s）——探测可达时，对应预设项高亮并附「已检测到」标记，且将返回的已拉取模型列表直接渲染为 model 下拉选项（用户免手打模型名）；不可达时预设项置灰并提示「未检测到本地服务」+ 安装/启动指引链接。探测仅访问 localhost，不计作出网。
5. **本地端点占位 Key**：选中本地预设时前端自动填入占位 Key（如 `ollama`）并标注「本地端点无需真实密钥」。注意：现状 `core/llm.py:_should_use_cloud()` 在本地 Key 为空且云端可用时会**静默回退云端代理**，与「Key 可留空」直接冲突——R4 落地必须实现「base_url 为 localhost 时不回退云端」（与 [BACKLOG 状态栏三态条目](BACKLOG.md) 同批交付，保证状态栏显示的路由与真实路由一致）。

### 7.3 断网开会（空态/加载/错误态）

- 空态：本地引擎未就绪时录音，转写队列挂起并提示「模型未就绪，前往设置」，录音本身不中断（数据落本地不变）。
- 加载：转写任务显示本地推理进度（分段处理，逐段回填）。
- 错误：模型文件损坏/内存不足/单文件超 4 小时支持上限（`audio_too_long`）→ 任务失败态 + 明确错误分类（复用 `core/errors.py`），提供「切回云端重试」出口；音频与任务状态保留（失败可恢复不丢录音）。本地模式录音启动时的实时预览降级为**设计内状态声明**（`type:"status"`，非红色报错），与录音页本地模式横幅口径统一（WP-H）。

### 7.4 回退与提质

- 任一本地环节失败且用户允许上云 → 引导切云模式重跑该任务（任务状态不丢失）。
- 离线完成的会议，联网后会议详情出现「用云端重转写提质」入口（复用既有 paraformer-v2 链路，保留本地结果对比）。

### 7.5 权限与角色

- 无新增角色；本地引擎配置为**设备级**（settings.json），多用户 Web 部署下**管理员配置、普通用户只读可见引擎状态**（依既有 admin/user 划分）。**D-R2 已裁决（2026-09-23）：管理员级**。

### Demo/原型方向

- 设置 → 计算引擎 Tab 静态可交互 mock（现有 SettingsView 扩展，含模型下载进度、连通性测试、引擎徽章三态）。
- 设计需验证：引擎三态（本地/体验代理/自持 Key）标识在顶栏的存在感与干扰平衡；下载失败/磁盘不足文案。
- 工程需验证：torch/funasr 进可选组件后 PyInstaller 双平台构建可行性；FunASR 推理与 FastAPI 事件循环共存（线程池隔离）。

## 8. Functional Requirements

### R1: ASR 引擎模式扩展（local）

- **用户故事**：作为内网用户，我要转写完全在本机完成，以便录音永不出设备。
- **场景**：`ASR_MODE=local` / 设置页切换后生效。
- **功能行为**：`core/transcribe.py` 与 `core/pipeline.py` 新增 local 分支，走 R2 本地管线；输出契约（时间戳、speaker_id、文本）与 proxy 模式逐字段对齐 `docs/API_CONTRACTS.md`。
- **边界**：local 模式下所有云端转写端点必须拒绝调用（防误配）；配置项 `engine.mode ∈ {cloud, proxy, direct, local}`。
- **边界（超时口径，WP-H 2026-09-24 落地）**：本地批转写单请求超时按音频时长动态估算（`core/engine_host.estimate_local_asr_timeout`：RTF 预算 0.5 s/s + 60s 余量，下限 180s），不再以固定 180s 上限整场判死长文件；单文件支持上限 **4 小时**（`LOCAL_ASR_MAX_SUPPORTED_SECONDS`），超限报 `audio_too_long` 分类错误——不发起引擎请求、音频保留、可显式回退云端（AC-4 语义不变）。实时链路的长会议超时问题由 R9 分段增量（D-I2「增量段拼接即定稿」）自然消解，不在本条范围。
- **验收**：切换后发起转写，抓包无出网请求；契约字段一致性单测通过。
- **优先级**：P0

### R2: 本地 ASR 管线（FunASR）

- **用户故事**：同上，需拿到带说话人分离的转写结果。
- **功能行为**：集成 FunASR 离线管线（转写 + VAD + 标点 + 说话人分离）；**热词映射（转写后替换）为必配项而非降级选项**——Spike 实测专名错误「云端科技→其他科技/吉达科技」「交付→提付」（Spike §2.3，内部归档）；复用 `core/hotwords.py` 映射表能力，与云端加权的效果差距在 UI 显性声明。
- **数据**：模型存放于可配置 `data/models/`（gitignore）；任务日志记录引擎与模型版本。
- **边界**：CPU/MPS 基线；超大音频分段处理内存峰值达标（AC-3）；推理不阻塞 Web 服务（线程/子进程隔离由工程定）。
- **验收**：AC-1/AC-2（WER 差距 ≤15% 相对值，`samples/` ≥3 段 2/4/6 人录音）。
- **优先级**：P0

### R3: 声纹本地化（CAM++）

- **用户故事**：作为离线用户，我要「Speaker 1 → 张三」的姓名化在断网下依然工作。
- **功能行为**：`core/embedding_provider.py` 新增 `LocalCamPlusProvider`（`iic/speech_campplus_sv_zh-cn_16k-common`，28MB）；本地模式下 `voiceprint.provider` 自动选择本地实现；注册、批处理匹配全本地。
- **数据**：注册表零迁移——`cam++-v1-cloud` 与 `cam++-v1` 互切可用（ADR-0009 既有承诺）。
- **边界**：云模式路由不变；实时聚类仍走 MFCC 链路（Non-Goal）；embedding 版本字段防混用。
- **验收**：AC-6 注册表兼容 + 匹配一致性抽查（FPR 相对差 ≤5%）。
- **优先级**：P0

### R4: LLM 自接端点增强

- **用户故事**：作为国际开发者，我装好 Ollama 后在设置里点两下就能出纪要，不想注册任何云。
- **功能行为**：`PROVIDER_PRESETS` 增 Ollama/LM Studio；「测试连接」端点（`POST /api/settings/test-llm`）；Key 允许为空（localhost 端点）；小模型防幻觉提示词档（纪要/洞察管线按 `model_tier` 选择提示词模板，默认 auto：≤14B 走保守档）；设置页 localhost `/v1/models` 自动探测 + 已拉取模型下拉回填 + 不可达置灰指引（见 §7.2-4）；localhost 端点不回退云端代理（修复 `_should_use_cloud()` 空 Key 静默回退，见 §7.2-5）。
- **边界**：非 localhost 端点要求 https 或显式警告；测试超时 10s；不影响云默认 qwen-plus。
- **Spike 证据（§4，内部归档）**：Ollama qwen3:8b 对 2500 字本地转写 31s 产出结构正确、未见幻觉的纪要——**8B 即达可用档**，支持 `model_tier` auto（≤14B 保守档）设计；正式最低推荐规格实验随 AC-2 评测脚本一并出。
- **WP-C 正式实验结论（2026-09-23，[EVAL-AC2-LOCAL-ENGINE.md](../tests/eval_local_engine/EVAL-AC2-LOCAL-ENGINE.md) §5）**：5 档 × 2 段（SEG-2P/6P）实测，以 qwen3:14b 为幻觉裁判。**推荐默认 = qwen3:8b**（结构完整度 1.0/1.0、裁判判定幻觉 0/0、时延 42–47s）；**可用下限 = qwen3:4b**（结构 1.0/1.0、幻觉 0/1、时延偏慢 39–55s）；**qwen2.5:3b-instruct 及 1.5b 不达可用档**（各丢一个「议题归类」章节、裁判判定幻觉 2–3 条/段）。据此细化 `model_tier` auto 策略：判定应基于能力档而非纯参数量——推理型 qwen3 ≥8B 走标准档、4–7B 走保守档、非推理型 ≤3B（如 qwen2.5 instruct）触发「降级警示」提示用户纪要可靠性不足。
- **验收**：本地 Ollama 出纪要；无 Key 保存不报错；错误端点有可行动提示；Ollama 在跑时模型名可下拉选择无需手打；Ollama 不在跑时预设置灰并给出安装指引；配置本地端点后抓包验证纪要生成请求仅发往 localhost（不回退云端）。
- **优先级**：P0

### R5: 模型资产管理

- **用户故事**：作为用户，我要清楚地知道要下载什么、多大、许可是什么，下载中断可续。
- **功能行为**：模型清单（R2/R3 所需权重）引导下载：进度/速度/剩余、SHA256 校验、断点续传、可取消、存储位置配置、磁盘空间预检；**内网路径**：导出/导入离线模型包目录结构与校验说明写入文档。
- **边界**：不内置分发权重（许可 + 包体）；校验失败自动重下 ≤1 次后转人工提示。
- **实施约束（Spike 实测 §3，内部归档）**：① 引擎以**常驻子进程**运行（冻结态 funasr 冷 import 最高 86s，禁止每任务冷启动）；② 多进程必须 `__main__` 保护 + 显式 `freeze_support`（Spike 观察到 import 重复引导 5–6 次）；③ 目录布局 = onedir 冻结代码包与模型权重分目录（`MODELSCOPE_CACHE` 指向 `data/models/`）；④ 政企离线路径 = Windows Inno Setup **组件选项**承载同一目录布局（对齐 D2 需求记录未决 1 的离线模型包问题，形态就此落定）。
- **验收**：断网首启无模型 → 全程可恢复；篡改文件被拒载。
- **优先级**：P0

### R6: 引擎状态透明与数据流向

- **用户故事**：作为安全敏感用户，我要一眼看出这场会的数据去了哪里。
- **功能行为**：顶栏引擎徽章（本地/体验代理/自持 Key/未就绪）；设置页数据流向矩阵（音频/转写文本/声纹特征/纪要提示词四类数据 × 三引擎去向）；README + SECURITY.md 同步该矩阵。
- **验收**：AC-5；徽章状态与后端实际路由一致（切模式后立即正确）。
- **优先级**：P1（随 P0 同版发布）

### R7: 失败回退与云端提质

- **用户故事**：离线录完的会，我想联网时用云端再精修一遍。
- **功能行为**：本地任务失败 → 错误分类 + 「切云端重试」引导（显式用户确认，绝不静默上云）；离线完成的任务详情页提供「云端重转写提质」，结果并排对比，替换需确认。
- **数据**：任务记录 `engine_used`、`enriched_from` 字段。
- **边界**：纯内网环境该入口置灰并说明原因；重转写不破坏已编辑笔记。
- **验收**：AC-4；对比视图两版数据完整。
- **优先级**：P1

### R8: 分发与构建

- **用户故事**：云模式老用户升级后包体与构建产物零变化。
- **功能行为**：**D-R3 已采纳**——应用内引导下载 + 外置引擎目录（onedir 冻结代码包 ~975MB + 权重 ≈2.0GB 分离，合计 ≈3GB），**否决内置云精简主包**（保 AC-7）；**分发承诺（2026-09-24 项目方裁决）：macOS 与 Windows 均须支持一键安装**，故 ~~macOS zip 形态、不做 pkg/dmg~~ 原代理裁决作废，拆为两层——**L1 主应用安装包**（mac `.dmg` + Developer ID 签名 + 公证；Win Inno）与 **L2 引擎组件一键落位**（mac 应用内下载解包到 `~/Library/Application Support/OpenMeetingScribe/`；Win Inno `[Components]`），详见 WP-G 派工说明 §3 D-G4（内部归档）。**L1 的唯一硬阻塞是外部成本**：需项目方提供 Apple 开发者账号（约 $99/年）与签名/公证凭据并托管为 GitHub Secrets。**2026-09-24 项目方追加裁决「暂时不考虑 Apple 开发者账号与凭据」→ mac L1 与 G-7 转 DEFERRED，移出 v10**；v10 内保留 mac L2（组件一键落位）与 Windows L1（Inno）。本地引擎组件独立可选安装，CI 增 local 链路冒烟（模型用最小/量化替身，禁真实大模型下载）。**实施首任务 = Windows PyInstaller+funasr 冻结冒烟**（Spike 未覆盖 Windows，为残余风险最高点）。
- **验收**：双平台本地组件安装 → AC-1 全流程；云包体积回归无增长。
- **优先级**：P0

### R9: 本地模式分段增量上屏（2026-09-24 新增，方案 B 裁决）

> 完整问题定义、技术前提与待裁决点见 [REQUIREMENT-LOCAL-REALTIME-INCR.md](REQUIREMENT-LOCAL-REALTIME-INCR.md)（v0.2.0）。此处仅登记契约边界，避免规格双写。

- **用户故事**：作为在断网/内网环境开会的主持人，我要在会中看到已经说过的话落在屏幕上，而不是等散会才有一篇稿。
- **功能行为**：录音进行中按语音段闭合（VAD 静音驱动 + 最长时长兜底，段长待 D-I3 实测）将音频切片送本机 FunASR 推理，段结果经既有 `push_realtime_msg` 以 `sentence` 事件上屏；**不产生 `partial` 事件**（逐字级流式仍非目标）。段间说话人身份以既有增量聚类为唯一事实源（`core/diarization_cluster.py`），**不得**跨段使用 FunASR 每次 `generate` 独立编号的局部 `spk`（`core/engine_worker.py:148-156`）。热词映射（R2 必配项）逐段应用。
- **边界**：感知延迟目标段闭合 → 上屏 P50 ≤ 8s / P95 ≤ 20s（Spike RTF 0.081 外推，需真机证）；单段失败不得连带重启常驻引擎（D-I1，现状 `core/engine_host.py:174-201` 超时即判 unhealthy 须改）；AC-3 内存门槛不因本需求放松；云模式路径零改动（AC-7）。
- **定稿一致性**：建议「增量段拼接即定稿」（D-I2 方案 B）——若采纳，长会议 `ENGINE_REQUEST_TIMEOUT=180s` 整场失败问题在实时链路自然消解，WP-H 第 1 项范围收窄至导入音频路径。
- **验收**：AC-9。
- **落地（WP-I 2026-09-24，引擎侧）**：`core/realtime_local_asr.LocalSegmentTranscriber` 分段转写器（能量 VAD 切段 + 有界队列背压 + 单段失败只丢该段并推非错误 `segment_skipped` 状态声明）；D-I1 落地为 `EngineHost.request` 两级语义（单请求超时=请求级失败、响应按 id 重同步丢弃过期回包、连续 N 次超时才重启子进程，N 默认 3 可经 `ENGINE_UNHEALTHY_CONSECUTIVE_TIMEOUTS` 覆盖；stdout 关闭仍即时判不健康）；D-I2 落地为 `pipeline_runner` 增量定稿路径（`transcript_finalized_incremental` 标记任务跳过 stage1 全量重跑，增量内容为空自动回退批转写兜底）；D-I3 落地为 `engine.local.realtime_segments.{enabled,min_segment_s,min_silence_s,max_segment_s}` 可配置项（**默认 enabled=false、临时默认 5/0.8/30s，待真机 20s/60s 各一场会延迟分布后由产品定默认值**）。会中上屏 UI 增量改动未做（派工单明令，等分段接口定稳后另行派工）；flag 关闭时行为与 WP-H 降级状态声明完全一致。
- **优先级**：**P1（已代理裁决采纳）**，不阻塞 AC-1 断网闭环发布；若项目方改判 P0，需同步重排 v10 里程碑与验收排期，且强依赖 WP-G 的 D-G1 先落地。

## 9. Data and Permission Requirements

- `data/settings.json`（gitignored）新增：`engine.mode`、`engine.local.{model_dir, model_tier}`、`llm.provider_presets 扩展`；全部变更走既有 settings 读写与脱敏逻辑（Key 不回显明文）。
- `data/models/`（gitignore）、声纹注册表新增 embedding 来源版本字段。
- 任务/作业日志：记录 `engine_used`、模型版本、耗时；**不记录音频内容**。
- 观测：本地推理失败率、回退次数、下载完成率（仅本地日志统计；如未来加遥测需另行评审并默认关闭——开源项目信任红线）。

## 10. Acceptance Criteria（版本级）

| # | 标准 | 执行方式 |
|---|---|---|
| AC-1 | 断网闭环：macOS + Windows 各完成「录音→转写→分离→声纹姓名化→纪要（自接端点）→导出 docx/md」；除 localhost 外零出网（代理抓包白名单验证） | QA 手工 + 抓包脚本 |
| AC-2 | 质量：`samples/` ≥3 段真实会议（2/4/6 人），本地 WER 与 paraformer-v2 差距 ≤15% 相对值；纪要结论/行动项可用性内部评审 ≥「可接受」 | 基准评测脚本（新增） |
| AC-3 | 资源：16GB 机型转写 30 分钟会议峰值内存 ≤8GB；模型总下载体积 ≤3GB（超出需评审修订）。Spike 参考：10 分钟会议 CPU 全管线峰值 RSS 3.3GB、RTF 0.081（30 分钟 ≈2.5 分钟转完），双门槛均有裕量 | 性能测试 |
| AC-4 | 回退：本地失败可切云端重跑，任务与笔记状态不丢失；纯内网正确置灰 | QA |
| AC-5 | 合规：数据流向矩阵上线（UI + README + SECURITY.md），与实测抓包一致 | 产品验收 |
| AC-6 | 声纹：云/本地注册表零迁移互用；同组说话人匹配结果一致（FPR 相对差 ≤5%） | 自动化对比测试 |
| AC-7 | 存量无损：云模式默认行为、包体、CI 全绿回归 | CI |
| AC-8 | 可观测：任务日志含引擎与模型版本；敏感信息过滤规则覆盖本地路径（复用 server.py 脱敏） | 代码评审 + 日志抽查 |
| AC-9 | 分段增量上屏（R9）：≥3 段 10/30/60 分钟真机会议会中均出现分段文字，段闭合→上屏 P95 ≤20s；同一说话人整场编号不跳变；会中上屏文本＝会后定稿；30/60 分钟不因单请求超时整场失败；单段失败不刷屏红色报错；AC-3 内存门槛与 AC-7 云侧零变化复测通过 | QA 真机 + 埋点统计（macOS + Windows 各一轮） |
| **AC-10** | **双平台一键安装（2026-09-24 项目方裁决新增；同日追加裁决：Apple 凭据暂缓 → mac L1 移出 v10）**：<br>**L2 引擎组件（v10 内必验）**——Win 与 mac 均须做到"应用内点一次『安装本地引擎』即到权重可下载态"，全程无需用户手找目录或手动解压；<br>**L1 主应用包**——Windows Inno 双击装完（**v10 内验**）；macOS `.dmg` + Developer ID 签名 + 公证（**DEFERRED，本里程碑不判定**，需项目方提供 Apple 账号与凭据后另立窗口）。<br>发布材料与 README **不得**写「macOS 支持一键安装」，只可写组件级一键安装 | QA 全新虚拟机/真机各一轮（mac 侧仅验 L2）+ Win 安装包 CI 绿灯 |

## 11. Rollout and Changelog Notes

1. 开发期 feature flag `local_engine`（默认 off），主分支可合并不发版。
2. 内部验证：AC-1~AC-6 全过 → 转 Accepted 状态更新 ADR-0018。
3. 发布：作为 v8（编号待 ROADMAP 定）主版本特性；CHANGELOG 用户向叙事 = 「全新离线模式：数据永不出设备」；双语 README 首屏增补 offline 说明 + 流向矩阵。
4. 开源节奏联动：本 PRD 验收通过 = GitHub 转 Public 前置条件之一（与既有开源清单：脏工作区、README 版本一致性合并执行）。

## 12. Risks and Open Questions

**风险**（详表见需求记录 §依赖与风险）：
- torch 回归使本地组件包体大增 → 组件隔离，云包无损（AC-7 兜底）。
- 小模型纪要质量不达预期 → 保守提示词档 + 回云提质路径；若 AC-2 不达标**不降级标准，砍范围**（先交付 ASR+声纹离线，LLM 提质后置）——此为本 PRD 唯一预留的范围裁剪点，需项目方认可。
- PyInstaller + FunASR 构建复杂度 → **Spike 已验证 macOS PASS**（975MB onedir 冻结包真实推理出文本，PRD §12 预留失败出口未触发）；残余风险 = **Windows 未实测**，以 WP-D（实施首任务）处置。

**Open Questions（决策点）**：
- ~~D-R1~~ **已采纳（2026-09-23）**：全家桶四模型 ≈2.0GB，标点可选裁剪（Spike §2）。
- ~~D-R2~~ **已裁决（2026-09-23）**：管理员级配置，全员只读引擎状态。~~无阻塞决策点残留，WP-A~D 全部解锁~~ **2026-09-24 更正：该结论仅对 WP-A~D 成立**——盘点 R8/R9 后新增 D-G1/D-G3/D-I1~I4（下条）。
- **2026-09-24 决策解锁（授权性质须留意）**：项目方给出 blanket 授权「我没答复的都按你给出的建议执行」，并于同轮**明确补充「包括指派工程师」**，故 D-G1~D-G5、D-I1~D-I4 **全部由产品经理按建议值代理裁决采纳**，三包 + CI 缺陷已派至具名工程师（见 ROADMAP v10 第三轮派工单 owner 列）。代理裁决**不等于项目方逐项亲口拍板**：取值依据与回退方式见 WP-G 派工说明 §3（内部归档）与 [R9 需求记录 §6](REQUIREMENT-LOCAL-REALTIME-INCR.md)。实施中判定建议值技术不可行 → 回报产品，不得静默变通。**唯一被项目方亲口推翻的取值：D-G4**（原「macOS 不做一键安装」→ 改为双平台一键安装）。
- **macOS 一键安装 L1 层已移出 v10（2026-09-24 项目方裁决：「暂时不考虑 Apple 开发者账号与凭据」）**：mac 侧 L1（`.dmg` + Developer ID 签名 + 公证）**本里程碑不排期、不作为验收项**，转为 v10 之后的独立待启动项；WP-G 的 G-7 同步转 DEFERRED。**保留的交付**：mac L2（引擎组件应用内一键落位）+ Windows L1（Inno）。当前 `build-macos.yml` 仍只产出未签名裸 zip（`:116` 创建 ZIP 包、`:124` 上传产物，全链无 codesign/notarize），这是**已知且被接受**的现状，不是待修缺陷。**对外口径硬约束**：只要 L1 未启动，README / 发布材料 / CHANGELOG 不得出现「macOS 一键安装」，只可写「macOS 支持应用内一键安装本地引擎组件」。
- ~~D-R3~~ **已采纳（2026-09-23）**：应用内引导下载 + 外置引擎目录；Windows Inno 组件承载政企离线路径（Spike §3）。
- D-R4：被 P0 让渡的当前迭代功能清单（项目方圈定；已随 ROADMAP v10 登记给出建议口径——因 v8/v9 被占用，本需求登记为 v10）。
- ~~离线模型包政企 SKU~~：由 D-R3 结论覆盖（Inno 组件即离线路径），需求记录未决 1 就此关闭；~~最低推荐 LLM 规格~~：**WP-C 已产出正式结论**（2026-09-23）——推荐默认 qwen3:8b、可用下限 qwen3:4b、qwen2.5 ≤3B 不达档，详见 [EVAL-AC2-LOCAL-ENGINE.md](../tests/eval_local_engine/EVAL-AC2-LOCAL-ENGINE.md) §5 与 R4。

## 13. 实施任务包（Spike 后移交拆解）

| 包 | 内容 | PRD 契约 | 依赖 | 验收 |
|---|---|---|---|---|
| **WP-A** | R4 LLM 自接增强：Ollama/LM Studio 预设、`POST /api/settings/test-llm`、空 Key 容错（含 localhost 不回退云端修复）、model_tier 保守档提示词、`/v1/models` 自动探测辅助配置、底部状态栏路由三态（[BACKLOG 缺陷条目](BACKLOG.md)并入） | R4 | 无（立即可开工） | R4 验收 + qwen3:8b/14b 双档实测记录 |
| **WP-B** | R5 模型下载器 + R6 引擎徽章/流向矩阵（含 README/SECURITY 文档更新） | R5/R6 | 无（D-R2 已裁决：管理员级）；目录布局按 Spike §3.3 | R5/R6 验收；篡改拒载用例 |
| **WP-C** | AC-2 评测基准脚本（≥3 段 2/4/6 人样本 + paraformer-v2 云端参照 + WER 计算 + 多说话人分离准确性补测） | AC-2 | 无 | 输出可复跑报告；Spike 遗留 2.3/5.1/5.3 三项一并覆盖 |
| **WP-D** | Windows PyInstaller+funasr 冻结 CI 冒烟（替身权重，禁真模型下载） | R8/AC-7 | **实施首任务** | Windows CI 绿灯；云包体积零增长回归 |

主干 R1/R2/R3（本地 ASR 挂线、管线集成、CAM++ 回归）按既定分工仍由 QoderIDE 侧推进；WP-A~D 与主干接口点少，可并行派发。

**第二轮及后续派工（登记于 ROADMAP v10，本表不双写细节）**：WP-E（R1/R2/R3 主干接线 + AC-4 回退）、WP-F（R5 前端 UI）已验收；**WP-G**（R8 打包 + **双平台一键安装**，派工说明内部归档，owner=DevOps 工程师，D-G1~D-G5 已裁决 · **已派工**）、**WP-H**（超时天花板 + 降级消息语气收口，owner=后端工程师 · **已派工**）、**WP-I**（R9 分段增量上屏，需求见 [REQUIREMENT-LOCAL-REALTIME-INCR.md](REQUIREMENT-LOCAL-REALTIME-INCR.md)，owner=后端工程师，D-I1~D-I4 已采纳 · **已派工，优先级 P1**）、**CI 缺陷**（`ci-local-engine.yml` 0s 失败，owner=DevOps 工程师 · **已派工**）。除 D-G4 由项目方亲口推翻加码外，其余决策取值均为**产品代理裁决**（项目方 blanket 授权 2026-09-24，含指派工程师），派工单与开工序见 ROADMAP v10。
