---
title: 转 Public 隐私精确清单与干净发布方案 — Open Meeting Scribe
description: 2026-10-04 全仓实测的隐私残留清单（工作树 + main 全历史 + 远端 ref）与两套发布处置方案；含当日执行进展
author: 产品经理（AI 起草）
created_at: 2026-10-04
updated_at: 2026-10-04
version: "1.0.0"
status: active
---

# 转 Public 隐私精确清单与干净发布方案

> 配套 `PUBLIC-LAUNCH-CHECKLIST.md`（同样在微云事故中丢失，待重建）的处置方案。
> 结论：**A1 阻断坐实，且 9-24 清单漏掉了"远端分支/标签口径"。推荐干净首提交 + 新建 GitHub 仓库发布。**
> 本文 2026-10-04 中午由全仓实测生成，扫描只输出计数与路径，未回显任何原文；15:40 按当日工作进展更新。

## 0. 当前进展（2026-10-04 15:40）

已完成（均在 main，工作区干净，后端 880/880、前端 26/26、vue-tsc 0 错）：

- 开源瘦身（commit `0fe4586`）：42 份内部派工/评审/Spike/QA 过程文档、8 个根目录一次性 `selftest_*.py`（含 §2.4 的 `selftest_dcr2b.py`）、188 个 `app/static/assets` hash 构建产物、MVP_PLAN、旧 spec 已删
- 悬空引用清理（`b4f92ec`）、TS/契约缺口修复（`f53f0f1`）、13 个陈旧/污染测试修复（`ebb446f` 生产修复 + `52de93d` 测试对齐）
- Dockerfile + .dockerignore 已提交（`e2703ac`，多阶段、含内置 ffmpeg、不含 FunASR）；README 双语已含分发声明与 Docker 说明
- GitHub Actions 三个构建工作流已改为仅手动触发；旧仓 main 已推送、远端旧 tag 已清空（实测 `ls-remote --tags` = 0）

仍未做（即本方案剩余动作）：工作树脱敏（§2）、干净历史与新仓库（§7 步骤 1–6）、版本号三处对齐、Docker 镜像实测、gitleaks 兜底、门面。

## 1. 实测总览

| 范围 | 结论 |
|------|------|
| HEAD 工作树 | `tests/eval_local_engine/` 现存 **62 个文件**（43 语料/清单 + 4 报告 + 14 脚本 + README）；eval 之外仍有 3 处代码/文档残留（真名 fixture、内网地址、作者邮箱） |
| main 全历史 | eval 全程在史；另有 4 个"已删除但历史可达"的含真名 blob（mock 文件 + 旧前端构建包） |
| 远端分支 | 旧仓 `git@github.com:et6624611/open-meeting-scribe.git` 现存 **19 个远端分支**，全部停留在重写前旧历史：13 个带 qa-evidence 截图（76~185 个对象）、全部带 eval；`origin/backup/main-legacy` 最严重（185 对象）。远端 tag 已为 0 |
| 本地分支 | 19 个（含 `snapshot/pre-slim-20261004` 微云事故快照分支、`feature/performance-monitoring` 干净候选） |
| 密钥 | 全历史无真实密钥（仅 .env.example 占位、RFC 测试向量）；gitleaks 仍须正式跑一次 |
| 用户数据 | `data/`、`.env`、评测音频均 ignored 且从未进 main 线；根目录调试 PNG 已清零 |

## 2. HEAD 工作树处置清单

### 2.1 必删：评测真实语料（43 个，全部在 `tests/eval_local_engine/`）

**refs/ 20 个** — 人工校对工作表 / 共识稿 / 三列工作台 / 云端时间轴 / 声纹片段索引，含真实逐字发言（每文件 4~182 段），3 个 cloud_timeline 另含真名 123 处：

```
refs/SEG-2P_cloud_timeline.json      refs/SEG-4P_cloud_timeline.json
refs/SEG-6P_cloud_timeline.json      refs/SEG-{2P,4P,6P}_consensus.json
refs/SEG-2P_human_ref.txt            refs/SEG-{2P,4P,6P}_human_ref_draft.txt
refs/SEG-{2P,4P,6P}_3col_workbench.md refs/SEG-{2P,4P,6P}_listen_list.md
refs/SEG-{2P,4P,6P}_proofread_worksheet.md
refs/vp_clips.json                    （声纹片段索引 + 真名 14 处，敏感级最高）
```

**results/ 22 个** — 云端/本地原始转写 6 个、LLM 纪要产物 10 个、声纹结果 3 个、指标 2 个、汇总 1 个：

```
results/cloud_SEG-{2P,4P,6P}.json     results/local_SEG-{2P,4P,6P}.json
results/llm_outputs/qwen*.md（10 个）  results/vp_cmn_fix.json（真名 152 处）
results/vp_compat.json（144 处）       results/vp_root_cause.json（8 处）
results/metrics.json（6 处）           results/llm_tiers.json（真实会议派生片段）
```

**根清单 1 个**：`eval_manifest.json`（真名 26 处 + 音频相对路径 + UUID）。

> 本地原件保留在已 ignored 的 `.eval_local_engine/` 或私有归档，不进任何公开历史。

### 2.2 须脱敏：评测报告 4 个

| 文件 | 问题 | 处置 |
|------|------|------|
| `EVAL-AC2-LOCAL-ENGINE.md` | 真名 23 处、引用逐字句 48 段 | 人名替换为 S1~S6 参会人代号；引用句改合成示例或删除，保留全部指标表与方法论 |
| `EVAL-AC2-PREVIEW-2P.md` | 逐字引用 21 段 | 同上 |
| `QA-R1-AC2-HUMAN-PROOFREAD-HANDOFF.md` | 逐字引用 18 段 | 保留校对流程描述，删除真实例句 |
| `README.md` | 语料目录说明 | 改写为"合成语料/私有语料不入库"口径 |

### 2.3 原样保留：评测脚本 14 个

全部 `.py`（`compute_metrics.py`、`prepare_segments.py`、`run_cloud_asr.py`、`run_local_asr.py`、`run_llm_tiers.py`、`qa_r1_*.py` 4 个、`vp_*.py` 4 个、`ac2_preview_2p.py`）— 已逐个核查：无硬编码真名、无绝对路径、无密钥（仅环境变量引用与相对路径模板）。

### 2.4 eval 之外的工作树残留（实测 2026-10-04 15:40）

| 文件 | 现状 | 处置 |
|------|------|------|
| `tests/test_chat.py` | 真名 fixture 仍在（张三/李四/王五/张玉苗/张宇，L113–198 共 9 处） | 替换为虚构测试名，保持断言语义 |
| `selftest_dcr2b.py`（根目录） | **已随瘦身删除** | 无 |
| `CHANGELOG.md` | 历史例句含真名（同 adr/0008） | 历史档案不改写；干净首提交收敛 CHANGELOG 时统一替换为"参会人 A/B" |
| `docs/adr/0008-ai操作结果系统校验.md` L9 | 同一例句（张玉苗/张宇） | 随 ADR 整体取舍：新仓库不带入历史 ADR 即天然消失；若保留则脱敏 |
| `tests/test_llm_selfhost.py` L48/L225 | 真实内网地址 `http://192.168.1.10:{11434,8000}` | 改为 `http://127.0.0.1:11434` |
| `pyproject.toml` L12/L15 | 真名 + 个人邮箱 `wangyongliang2006@126.com`（authors/maintainers 两处） | **已定（用户拍板）**：换 GitHub noreply（`ID+用户名@users.noreply.github.com`，Settings → Emails 取值）；首提交作者身份同步使用该邮箱 |

已排除的误报：`docs/` 两字名子串误报、13800138000 官方测试号、RFC 6238 TOTP 测试向量、空 `JWT_SECRET=`、`*.local` 属性误报。

## 3. main 全历史独有残留（HEAD 已删、历史可达）

| blob | 路径 | 内容 |
|------|------|------|
| `e280f2e241`、`ee20d0cf77` | `frontend/src/api/decisionsMock.ts`（2 个历史版本） | mock 数据含真名 2 处 |
| `20dc45c1d8`、`e815242a32` | `app/static/assets/decisionText-*.js`（2 个历史构建包） | 上述 mock 编译进 bundle，含真名 |

含义：只改工作树没有意义，这 4 个 blob 连同 eval 全部历史版本，在公开仓库里按 commit hash 仍可检出。**历史处置不可省。**

main 线从未入库（含全部历史版本核查）：`.env`、`data/settings.json`、`data/remote_config.json`、`data/usage/`、`data/speakers.json`、`data/users.json`、会议音频。

## 4. Ref 处置清单

### 4.1 远端分支：19 个，新仓库天然不带（推荐路径）；若留旧仓则发布前全删

- `origin/backup/main-legacy`：**最高危**，256 个独有提交、185 个 qa-evidence 对象（127 截图 + 58 文本，其中 1 个文本 blob 已确认含真名）。删除前确认本地 mirror 备份（`open-meeting-scribe-mirror-backup-20261004.git`）可检出，再补一份加密离线归档 🔒
- 13 个 `origin/feat/*`：全部停留在重写前历史，其中 12 个带 qa-evidence（76~178 对象）、全部带 eval；对应本地分支已合入 main，无保留价值
- `origin/feat/req-decision-center-b1`、`origin/task/*`（2 个）：无 qa-evidence 但带 eval（60/43 文件），内容已被 main 覆盖
- `origin/feature/performance-monitoring`：**唯一无隐私的远端分支**（16 个独有提交）。需要该功能则在干净仓库从本地同名分支 rebase 后再推

### 4.2 本地分支：19 个

- **13 个已完全合并 main，直接删除**：`feat/dc-r2-b`、`feat/dc-r2-be`、`feat/dc-r2-c`、`feat/def-device-01be`、`feat/def-proxy-0203`、`feat/req-access-mode-b1`、`feat/req-access-mode-f1`、`feat/req-decision-r2a`、`feat/req-progress-p0`、`feat/req-spk-rn`、`feat/req-spk-rn-be`、`task/feedback-ui-defects-20260924`、`task/local-engine-wpg-20260924`
- **3 个有少量独有提交，删除前需确认**：`docs/req-spk-rn-t1-design`（3）、`feat/def-device-01a`（1）、`feat/req-decision-center-b1`（3）。逐个 diff，有价值的摘到 docs/ 后删
- **1 个保留候选**：`feature/performance-monitoring`（16 个独有提交，无隐私），干净仓库建好后 rebase 过去
- **1 个事故快照**：`snapshot/pre-slim-20261004`（含未跟踪文件的 WIP 提交），仅本地救援用，新仓库不迁

### 4.3 标签

远端旧 tag 已清空（16 个旧 tag 不迁任何新历史）；干净发布只打且只打 `v1.0.0` 一个新 tag。

## 5. 工作树卫生（转 public 前完成）

- 根目录调试 PNG：实测已清零（`.gitignore` `/*.png` 兜底 + 瘦身清理）
- 删除微云同步盘内的副本 `LICENSE 2`、`VERSION 2`（同步盘冲突曾两度覆盖工作区，发布后注意排除同步）
- ignored 复核：`.env`、`.eval_local_engine/`、`data/` 全部用户数据、`build/`、`voiceprint-service/models/` 均已忽略，`git status` 零未跟踪文件

## 6. 两套方案对比

| | 方案 A：干净首提交 + 新建仓库（推荐） | 方案 B：二次 filter-repo 重写 |
|---|---|---|
| eval 62 文件及全部历史 | 天然不存在 | 需逐路径剥离，再全量 gc |
| 4 个历史 mock/bundle blob | 天然不存在 | 需额外 --path/callback 处理 |
| 19 个远端旧分支 | 新仓库天然不带 | 必须逐个删 ref，漏一个即泄露 |
| 工作树 3 处残留脱敏 | 在首提交中一次成型 | 需 --replace-text 全历史替换（34 个名字 × 全历史，diff 污染严重） |
| commit 迭代史 | 丢失（main 线 242 个提交），由 CHANGELOG 与建设复盘文章承接叙事 | 保留，但已是第二轮重写（本仓库 10-04 刚发生过重写事故） |
| GitHub 侧旧 hash 残留 | **不存在**（新仓库没有旧对象） | force push 后旧 commit hash 仍可能被直接访问/被 fork 缓存，通常需联系 GitHub Support GC |
| 工作量 | 半天 | 1~2 天，且需要再次全量验证 |
| 主要风险 | 叙事资产需要重新组织 | 任一远端 ref 漏删即失败；重写过程与微云同步盘并发有覆盖前科 |

## 7. 推荐执行步骤（方案 A）

> 标 🔒 的步骤改变远端或不可逆，必须项目方明确授权后执行；其余纯本地。

1. **本地完整备份（纯本地）**：`git bundle create ../oms-full-backup-20261004.bundle --all` + 确认 10-04 的 mirror 备份可检出；备份置于仓库与同步盘之外
2. **工作树脱敏（纯本地，独立分支 staging/public-clean）**：
   - 删除 §2.1 的 43 个语料/清单文件（整个 eval 目录可随开源决策整体删除，保留则按 §2.2/§2.3 处置 18 个文件）
   - 按 §2.4 处理：test_chat.py 真名改虚构、selfhost 内网地址改 127.0.0.1、pyproject 邮箱换 noreply
   - 复核：重跑隐私扫描脚本，期望工作树零真名、零真实内网地址
3. **造干净历史（纯本地）**：在脱敏后的树基础上 `git checkout --orphan` 生成单个首提交；提交信息注明"首个公开发布版本，早期开发历史保留于私有归档"
4. **版本号治理（纯本地）**：**已定（2026-10-04）首发 `v1.0.0`**——VERSION（现 7.4.5）、README 中/英 front-matter（现 2.0.1 / 2.1.0）、CHANGELOG 头部三处对齐为 1.0.0；旧版本叙事收敛进 CHANGELOG，"本地引擎"状态如实标注；打且只打 v1.0.0 一个新 tag
5. 🔒 **新建 GitHub 仓库**（建议同名；旧仓 rename 为 `*-private-archive` 私享留档，观察期后删除）：推送干净 main 与新 tag；`feature/performance-monitoring` rebase 后按需推送
6. 🔒 **旧仓库收尾**：删除全部 19 个远端分支（含 main-legacy）；旧仓保持 private 直至删除；存在期间不向任何人授权
7. **转 public 前剩余门禁**：`gitleaks detect --source <新仓库> --no-banner`（兜底，预期零命中）；完成清单 A3（FunASR/ModelScope 四模型许可与"引导下载不随包分发"核查，出 THIRD_PARTY_NOTICES）；B1 真机验收结论同步 README；Docker 镜像实测 `docker build -t open-meeting-scribe .` 并补最小冒烟
8. **门面（可与 2~7 并行）**：30 秒价值主张首屏、topics、demo GIF、截图版 Quickstart、首个 Release 资产、Issue 模板；按 12:59 讨论结论，README 显著声明"非 IT 人员可在 AI 协助下使用 / AI 辅助开发"

## 8. 不做的事

- 不向公开仓库迁移任何旧 ref、旧 tag、旧 bundle 对象
- 不把声纹片段、评测音频、人工校对稿以"打码截图"形式重新引入（声纹属生物特征关联数据，不存在"轻度脱敏可用"）
- 评测可复现性如未来需要，另立合成数据工程（虚构会议剧本 + TTS/真人朗读生成），不复用任何真实片段
- 不提供预编译二进制包：仅源码安装与 Docker 两条路径（用户已拍板，减轻维护负担）
