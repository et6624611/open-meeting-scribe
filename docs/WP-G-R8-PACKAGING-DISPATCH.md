---
id: WP-G
title: R8 分发与构建 · 打包路线派工说明（含决策点）
version: 0.1.0
status: draft-for-decision (D-G1/D-G3 未裁决，阻塞开工)
date: 2026-09-24
source: docs/ROADMAP.md v10「WP-G 派工（2026-09-24）」
prd: docs/PRD-LOCAL-ENGINE.md §R8 / §13 WP-D
adr: docs/adr/0018-本地可选计算引擎与声纹离线化.md (D-R3 已采纳)
spike: docs/SPIKE-R8-LOCAL-ENGINE.md §3
owner: 待指派（建议工程侧打包/客户端 owner）
approvers: 项目方（D-G1 引擎包形态、D-G3 Windows 可写目录锚点）
---

# WP-G · R8 打包路线派工说明

## 0. 目标与完成判据

**目标**：让「本地引擎」在**冻结安装包**里真的可用，同时云模式用户升级后包体与行为零变化。

**Done 判据（全部满足才算完）**：

1. 冻结态（非 venv）在 macOS 与 Windows 上完成 AC-1 断网闭环：装组件 → 下载权重 → 切 local → 录音 → 出带说话人的转写 → 全程抓包零出网。
2. AC-7 三重守护全绿：spec 静态检查 + 冻结依赖图检查 + 云包体积阈值。
3. 云包构建链路（`build/pyinstaller.spec` / `pyinstaller_macos.spec`）与 `build-windows.yml` / `build-macos.yml` 产物**未被本地引擎污染**。
4. 引擎组件缺失/损坏/版本不匹配三种状态，UI 给的是**可行动的分级指引**，不是报错堆栈。

**当前状态**：WP-G 仅有 ROADMAP 派工登记（`a589ea3`），**无代码提交、无分支**。

---

## 1. 现状盘点（证据）

| WP-G 子项 | 状态 | 证据 |
|---|---|---|
| onedir 冻结代码包 + 外置引擎目录（D-R3） | 未做，且被现有 spec 反向阻塞 | `build/pyinstaller.spec:101-109`、`build/pyinstaller_macos.spec:82-90` 显式 `excludes=['torch','torchaudio']`；无任何 engine 专用 spec |
| Windows Inno Setup「本地引擎组件」可选安装 | 未做 | `build/installer.iss` 无 `[Components]` 段，仅 `[Tasks]`（桌面图标，:78/:99）。installer 本身可编译（`05356fe`、`55feea5` 两次修复为证） |
| 冻结应用内首启引导接 WP-F UI | 未做（依赖已就绪） | WP-F UI 已落 `aaaaa958`，仅在 web/dev 态可达；冻结态首启未接线 |
| CI local 链路冒烟（替身权重，禁真实下载） | 被存量缺陷卡住 | `.github/workflows/ci-local-engine.yml` 5 次运行全部 0s 失败、0 jobs（见 §5 诊断） |
| 引擎子进程再入分派 | 代码已在，但冻结态不成立 | `core/engine_host.py:48-56` 冻结态返回 `[sys.executable, "--engine-worker"]`；`desktop.py:329-337` 已有 `freeze_support()` + 标志分派 |

---

## 2. 三个冻结态必踩的阻塞缺陷（开工前先看，决定 D-G1）

### B-1｜引擎子进程形态与云包瘦身互斥（**最高优先**）

现状自相矛盾，两头都不成立：

- `core/engine_host.py:55` 冻结态把引擎当**同一个主 exe 的再入进程**拉起（`<exe> --engine-worker`）。
- 但主 exe 在 `build/pyinstaller.spec:103` 明确排除了 `torch`/`torchaudio`（AC-7 云包零增长 + v5 依赖瘦身的既定方向，`requirements.txt` 已无 torch）。

→ 结论：**按现在的打包配置，冻结包里没有 funasr/torch，`--engine-worker` 再入必然 import 失败。** 而"把 torch 放回主包"直接违反 R8/AC-7（`docs/PRD-LOCAL-ENGINE.md:182` 已写明"否决内置云精简主包"）。这不是实现细节，是包形态决策未定，见 §3 D-G1。

### B-2｜模型目录是相对路径，冻结态会指进只读 bundle

`core/model_registry.py:81-90` 默认返回 `Path("data/models/")`（相对），`core/engine_host.py:137` 的子进程 `cwd` 取 `Path(__file__).parent.parent` —— 冻结态这是 `sys._MEIPASS` 只读 bundle 根，不是 exe 同级可写目录。对照正确写法：`core/audio.py:44-45`（ffmpeg 用 `sys.executable` 同级解析）、`desktop.py:66`（`.env` 用 exe 同级）。

→ 后果：即使权重已下好，`check_required_models()`（`core/engine_host.py:110`）也会报 `models_missing`；而 Windows 下 `data/models/` 的宿主位置受 D-G3 的可写目录决策影响。

### B-3｜引擎子进程 stderr 被丢弃，冻结首启失败不可诊断

`core/engine_host.py:133` `stderr=subprocess.DEVNULL`。Spike §3.2 记录冻结态 funasr import 最高 86s、Windows 杀软场景更差，且 spawn 重复引导会出现 5–6 次 import —— 一旦组件装错/版本不匹配，用户只看到 `engine_unhealthy`，日志里什么都没有。

→ WP-G 期间**必须**把引擎子进程 stderr 收进任务日志（对齐 AC-8 可观测 + `core/joblog.py` 脱敏规则），否则 Windows 侧排障成本会全部转嫁给验收阶段。

---

## 3. 决策点（需项目方/工程 owner 拍板）

### D-G1｜引擎可执行体的包形态 —— 阻塞，先定这个

| 方案 | 做法 | 代价 | 产品判定 |
|---|---|---|---|
| **A. 独立引擎包（推荐）** | 新增 `build/pyinstaller_engine.spec` → onedir 引擎目录（Win `OMSEngine.exe`，mac 同名可执行体）；主包 spec 一字不动；`build_worker_command()` 改为"定位外置引擎目录中的可执行体 + 协议版本握手" | 新增 1 个 spec、`engine_host` 路径解析 + 版本协商、installer/zip 两套布局；引擎包与主包需版本兼容矩阵 | ✅ 唯一同时守住 AC-7（云包静态可判）与 D-R3（≈975MB 只在装组件时出现）的方案；云用户升级零感知的承诺由此可证 |
| B. 同 exe 双产物 | 两份 spec 产出同名 exe 的"云版/引擎版"，分发通道区分 | 构建矩阵与更新通道翻倍；AC-7 只能靠分发而非构建保证，体积守护需重写；用户混装风险 | ⚠️ 不推荐：把包形态正确性从构建期推到发布期 |
| C. 条件打包（单 spec + 环境变量开关） | 同一 spec 按 `OMS_ENGINE_BUILD` 决定是否 excludes torch | CI 一旦漏配开关即污染云包，且静态守护失去可判性 | ❌ 建议否决：AC-7 是"存量无损"承诺，不该依赖人为配置 |

**A 方案附带子决策（必须一并定）**：
1. 三条安装通道（应用内引导下载 / Inno 组件 / 内网离线包）**共用同一目录布局与同一份 manifest 文件**——目录布局建议：`<引擎根>/OMSEngine(.exe)` + `<引擎根>/_internal/`，`<引擎根>/engine-manifest.json`（版本、协议版本、文件 SHA256）。
2. `--engine-worker` 再入分派（`desktop.py:335`）保留还是退役：建议保留为**开发态/降级路径**，冻结态正式路径走独立引擎包，避免两套语义在 CI 冒烟里互相掩盖。
3. 主包 ↔ 引擎包的协议版本不匹配时的行为：拒绝启动 + 明确"请升级本地引擎组件"，不得静默回退云端（对齐 `can_fallback_cloud=False` 语义）。

### D-G2｜ct-punc（1.0GB，占权重 50%）在打包层怎么表达

现状 `core/model_registry.py` 已有 `optional` 字段，`check_required_models()` 按 `meta["optional"]` 跳过预检 —— 打包层沿用即可。但预算结论未定：全家桶 ≈2.0GB vs 去标点 ≈1.0GB，AC-3 门槛 ≤3GB。

→ **不在 WP-G 内提前裁决**：按 ROADMAP:150 已定的"先实测后议"，等真机验收的标点可读性实测出来，再触发「可选转必装」或「接受降级 + 文档标注」。WP-G 只负责保证两条路径都能装：清单区分必装三件/可选项、可选件缺失不影响 `ready` 判定。

### D-G3｜Windows 组件落到哪个可写目录 —— 阻塞政企路径

Inno Setup 默认装到 `Program Files`（非管理员不可写）。而引擎组件要写日志、权重要写 `data/models/`、ModelScope 缓存要写目录。三选一，需拍：
- (a) 权重与引擎运行时数据落 `%LOCALAPPDATA%\OpenMeetingScribe\models\`，安装目录只放只读代码包 —— 产品倾向：与"云包零增长 + 组件可独立更新"最一致，且不要求管理员权限。
- (b) 装机时把整个应用装到 `%LOCALAPPDATA%`（Per-user install）—— 改变现有升级方案（历史决策沿用 Inno），影响面大。
- (c) 维持 `Program Files` + 要求管理员运行 —— ❌ 不接受，伤云模式存量体验。

选定后 D-G2 的 `model_dir` 默认值需按平台改（现为 `app/settings_store.py:350` 的 `data/models/`），并同步 WP-F UI 的存储位置展示与磁盘预检。

### D-G4｜macOS 引擎组件的分发形态

Spike §3 只在 macOS 验证过冻结**构建与运行**，没有 mac 安装包方案（现 `build-macos.yml` + `build_macos.py` 是云包链路）。建议：引擎组件以 **zip 形态 onedir 目录包**由应用内引导下载落位，macOS 不做 pkg/dmg 组件安装（省公证与签名成本），Inno 组件路径仅服务 Windows 政企离线场景。需项目方确认"是否对用户承诺 macOS 一键安装"。

### D-G5（产品要求，非决策）｜首启 86s 的体验契约

冻结态 funasr import 数十秒是**已知且接受**的代价，但必须有反馈：拉起引擎期间 UI 显示"正在启动本地引擎（首次约 1–2 分钟）"进度态，`ENGINE_START_TIMEOUT=120` 超时时给"启动失败 + 日志位置 + 重试"，而不是把 `engine_unhealthy` 原文丢给用户。

---

## 4. 任务拆分与依赖序

| # | 子任务 | 产出物 | 依赖 |
|---|---|---|---|
| G-1 | 冻结态三缺陷修复方案确认（B-1/B-2/B-3 的最小复现 + 修复口径） | 复现记录 + 修复 PR 描述 | **D-G1、D-G3 裁决** |
| G-2 | 新增 `build/pyinstaller_engine.spec`（mac+Win onedir）+ 引擎包 manifest/协议版本 | 可运行引擎包（替身权重下） | G-1 |
| G-3 | `core/engine_host.py` 改造：引擎可执行体定位、`model_dir` 平台锚点、stderr 入日志 | 单测 + 开发态回归不红 | G-1/G-2 |
| G-4 | `build/installer.iss` 新增 `[Components]` 本地引擎组件（含可选件开关）+ 内网离线包目录/校验文档 | Win 安装包：不装组件=云包体积不变 | D-G3、G-2 |
| G-5 | 冻结态首启引导接 WP-F UI（组件未装/未就绪/不匹配三态） | mac+Win 真机首启走通到"下载权重" | G-2、D-G5 |
| G-6 | CI：修好 `ci-local-engine.yml` 后补 local 链路冒烟（替身权重，禁真实下载） | Windows 冻结冒烟绿灯 + AC-7 体积守护绿灯 | §5 |

可并行：G-4 与 G-5 在 G-2 完成后并行；G-6 由 WP-D owner 与 G-2 并行启动。

---

## 5. 前置阻塞：`ci-local-engine.yml` 0s 失败（已排除的方向）

WP-G 全部产物依赖这条 workflow 做验证，不修就是"造了没秤称"。已实测证据：

- `gh workflow list`：其余 4 条 workflow 显示 `name:`，唯独此条显示 **`.github/workflows/ci-local-engine.yml`** —— GitHub 未解析出 workflow 元数据。
- `gh api runs/<id>`：`conclusion=failure`、`/jobs` 返回 `total_count: 0`、`error` 字段为 null、对应 commit 的 check-runs 里**没有**该 workflow 的注解。
- 本地已排除：YAML 解析通过、**无重复键**、无 tab、无 CRLF、UTF-8 无 BOM、`name: CI Local Engine`、jobs 两个键正常（`runs-on: windows-latest`，timeout 150/75）。

→ 尚未定位到根因，**不再靠猜**。给 owner 的有界下一步：用一次只含 `cloud-package-size-guard` 单 job、去掉 `concurrency` 段（`:55-57`）与中文 job name 的最小 workflow 做二分提交；重点验证两个可疑点——`concurrency.cancel-in-progress` 里的 `${{ github.event_name == 'pull_request' }}` 表达式，以及 job-level `if`（`:63-66`）在非 dispatch 事件下引用 `inputs.freeze_smoke`。若确认是私有仓库 Windows metered 额度问题，则按 ROADMAP:151 走账号侧处置，并把 local 冒烟临时降级为 macOS-only（Windows 侧留真机验收人工冒烟）。

---

## 6. 验收判据（可测口径）

1. **AC-1（断网闭环）**：冻结包 + 已装引擎组件 + 已下权重，拔网线完成一场录音并出转写；抓包白名单只允许 localhost。判据落在 G-3/G-5 产物上，**不接受用 venv 冒替**。
2. **AC-7（存量无损）**：`git diff` 后云包 spec 未变；size-guard 三重检查（spec 静态 / 冻结依赖图 / 体积阈值）绿灯；`build-windows.yml`、`build-macos.yml` 产物体积与 main 基线差 ≤ 噪声。
3. **组件三态**：未装 / 装了未下权重 / 版本不匹配，三态各截图 + 文案，均需给出下一步动作。
4. **B-3 可诊断性**：故意放一个损坏的引擎包，任务日志能看到引擎侧 stderr 摘要（脱敏后）。
5. **最长会议时长**：⚠️ 不在 WP-G 修，见 §7；但 AC-1 用例必须包含一段 ≥30 分钟的样本，好让超时缺陷在验收阶段被显式抓到而不是漏过。

---

## 7. 明确不做（防扩范围）

- **逐字级流式实时转写**：`docs/PRD-LOCAL-ENGINE.md:72` 非目标，任何"本地也要逐字流"的诉求走非目标拒绝/延后，不进 WP-G。
- **本地模式两个已知硬坑**（另立 WP-H，勿塞进本包，否则 G-2/G-4 排期会被拖）：
  1. `core/engine_host.py:31` `ENGINE_REQUEST_TIMEOUT=180s` 是单请求上限，按 Spike RTF≈0.081 反推音频超过约 37 分钟必超时；本地模式 `can_fallback_cloud=False` → 超时即**整场转写失败、录音白录**。
  2. `app/routers/record.py:466-477` 把设计内的"本地降级"当异常兜住并推 `type:"error"` 消息，用户每次开始录音都看到一条红色报错，与同页降级横幅（`RecTranscriptPanel.vue:65`）自相矛盾。
  3. 连带口径问题：横幅与 PRD 写的是"实时转写按分段批处理输出"，而实现是**录音期间完全不出稿、结束后一次性全量批处理**（`core/realtime_asr.py:222-233` 直接抛 `realtime_degraded_to_batch`）。→ **2026-09-24 项目方已裁决取方案 B（真做分段增量上屏）**，落地定义见 [REQUIREMENT-LOCAL-REALTIME-INCR.md](REQUIREMENT-LOCAL-REALTIME-INCR.md)，实施包为 ROADMAP **WP-I**（其强前置即本包的 D-G1）。本包不含 B 的实现，但 G-3/G-5 的接口设计**不得把"单请求全量"写死**，否则 WP-I 返工。
- CUDA / 多硬件加速矩阵、端侧训练微调、订阅化：均为 PRD 非目标。

---

## 8. 证据 / 假设 / 未知

**已确认（代码与 CI 实读）**：B-1、B-2、B-3、§1 现状表、§5 CI 诊断证据、引擎再入分派与 `freeze_support` 已在 `desktop.py:329-337` 落地。

**合理假设（需真机证）**：`excludes torch` 是主包零增长的**唯一**屏障（不排除还有间接引用路径）；RTF 0.081 可外推到 30–60 分钟会议（仅 1 段 10 分钟样本、单机 CPU）。

**未知（需拍板/实测）**：D-G1 最终形态、D-G3 Windows 可写锚点、D-G4 macOS 是否承诺一键安装、`ci-local-engine.yml` 失败根因、Windows Defender 场景下引擎包首启真实耗时、多说话人分离准确性。
