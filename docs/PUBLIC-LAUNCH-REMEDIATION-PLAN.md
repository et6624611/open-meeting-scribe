---
title: 转 Public 隐私精确清单与干净发布方案 — OpenMeetingScribe
description: 2026-10-04 全仓实测的隐私残留清单（工作树 + main 全历史 + 54 个 ref）与两套发布处置方案
author: 产品经理（AI 起草）
created_at: 2026-10-04
updated_at: 2026-10-04
version: "1.0.0"
status: active
---

# 转 Public 隐私精确清单与干净发布方案

> 配套 [PUBLIC-LAUNCH-CHECKLIST.md](PUBLIC-LAUNCH-CHECKLIST.md) 的处置方案。本文全部结论来自 2026-10-04 本地实测，扫描只输出计数与路径，未回显任何原文。
> 结论：**A1 阻断坐实，且 9-24 清单漏掉了"远端分支/标签口径"。推荐干净首提交 + 新建 GitHub 仓库发布。**

## 1. 实测总览

| 范围 | 结论 |
|------|------|
| HEAD 工作树 | eval 目录 42 个文件必删、4 个文档须脱敏；eval 之外另有 4 个代码/文档文件含真名、1 处真实内网地址 |
| main 全历史 | eval 全程在史；另有 4 个"已删除但历史可达"的含真名 blob（mock 文件 + 旧前端构建包） |
| 远端分支 | 17 个远端分支全部停留在重写前旧历史：13 个带 qa-evidence 截图（76~185 个对象）、全部带 eval；`origin/backup/main-legacy` 最严重（185 对象） |
| 标签 | 16 个 tag 中 3 个（v6.0.0/v7.0.0/v7.0.1）已脱离 main 线；干净发布后旧 tag 一律不带 |
| 密钥 | 全历史无真实密钥（仅 .env.example 占位、RFC 测试向量）；gitleaks 仍须正式跑一次 |
| 用户数据 | `data/` 敏感文件、`.env`、评测音频全部 ignored 且从未进 main 线 ✅；工作树零未跟踪文件 ✅ |

## 2. HEAD 工作树处置清单

### 2.1 必删：评测真实语料（42 个，全部在 `tests/eval_local_engine/`）

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
| `EVAL-AC2-LOCAL-ENGINE.md` | 真名 23 处、引用逐字句 48 段 | 人名替换为 S1~S6 参会人代号；引用句改为合成示例或删除，保留全部指标表与方法论 |
| `EVAL-AC2-PREVIEW-2P.md` | 逐字引用 21 段 | 同上 |
| `QA-R1-AC2-HUMAN-PROOFREAD-HANDOFF.md` | 逐字引用 18 段 | 保留校对流程描述，删除真实例句 |
| `README.md` | 语料目录说明 | 改写为"合成语料/私有语料不入库"口径 |

### 2.3 原样保留：评测脚本 14 个

全部 `.py`（`compute_metrics.py`、`prepare_segments.py`、`run_cloud_asr.py`、`run_local_asr.py`、`run_llm_tiers.py`、`qa_r1_*.py` 4 个、`vp_*.py` 4 个、`ac2_preview_2p.py`）— 已逐个核查：无硬编码真名、无绝对路径、无密钥（仅环境变量引用与相对路径模板）。

### 2.4 eval 之外的工作树残留（新发现，清单未覆盖）

| 文件 | 问题 | 处置 |
|------|------|------|
| `tests/test_chat.py` | 测试 fixture 使用 3 个真实姓名（含 1 个全名，12 行） | 替换为化名（如"张三/李四"风格的明显测试名），保持断言语义 |
| `selftest_dcr2b.py`（根目录） | 真实姓名 14 行 + 拼音缩写 speaker_id（`spk-wyl`/`spk-zcc`） | 姓名与 id 一并改虚构值 |
| `CHANGELOG.md` L2186 | 缺陷案例例句引用真名 | 替换为"参会人 A/B"，脱敏版在首发布提交中一次成型 |
| `docs/adr/0008-ai操作结果系统校验.md` L9 | 同一例句 | 同上 |
| `tests/test_llm_selfhost.py` | `http://192.168.1.10:11434/8000` 疑似真实内网地址 2 处 | 改为 `http://127.0.0.1:11434` |
| `pyproject.toml` | 作者 126 个人邮箱 | **已定（2026-10-04）**：换 GitHub noreply 邮箱（`ID+用户名@users.noreply.github.com`，Settings → Emails 取值）；首提交作者身份同步使用该邮箱 |

已排除的误报：`docs/` 其他 30+ 命中均为两字名的子串误报（二次精确复核归零）；手机命中为 13800138000 官方测试号与测试夹具假号；`AUTH_DESIGN.md` 命中为 RFC 6238 TOTP 测试向量与空 `JWT_SECRET=`；内网主机命中 84 文件均为 `*.local` 对象属性误报。

## 3. main 全历史独有残留（HEAD 已删、历史可达）

| blob | 路径 | 内容 |
|------|------|------|
| `e280f2e241`、`ee20d0cf77` | `frontend/src/api/decisionsMock.ts`（2 个历史版本） | mock 数据含真名 2 处 |
| `20dc45c1d8`、`e815242a32` | `app/static/assets/decisionText-*.js`（2 个历史构建包） | 上述 mock 编译进 bundle，含真名 |

含义：只改工作树没有意义，这 4 个 blob 连同 eval 全部历史版本，在公开仓库里按 commit hash 仍可检出。**历史处置不可省。**

main 线从未入库（含全部历史版本核查）：`.env`、`data/settings.json`、`data/remote_config.json`、`data/usage/`、`data/speakers.json`、`data/users.json`、会议音频。

## 4. Ref 处置清单（54 个 ref，9-24 清单盲区）

### 4.1 远端分支：17 个，发布前全部删除（或不进入新仓库）

- `origin/backup/main-legacy`：**最高危**，256 个独有提交、185 个 qa-evidence 对象（127 截图 + 58 文本，其中 1 个文本 blob 已确认含真名）。处置：删除远端分支前，本地已有 mirror 备份（`open-meeting-scribe-mirror-backup-20261004.git`），再补一份加密离线归档。
- 13 个 `origin/feat/*`：全部停留在重写前历史（落后 main 242），其中 12 个带 qa-evidence（76~178 对象）、全部带 eval。对应本地分支重写后均已合入 main（见 4.2），无保留价值。
- `origin/feat/req-decision-center-b1`、`origin/task/*`（2 个）：无 qa-evidence 但带 eval（60/43 文件），内容已被 main 覆盖，删除。
- `origin/feature/performance-monitoring`：**唯一无隐私的远端分支**（qa=0、eval=0，16 个独有提交）。若要保留该功能，在干净仓库上从本地同名分支重新 apply；否则一并删除。

### 4.2 本地分支：17 个

- **13 个已完全合并 main，直接删除**：`feat/dc-r2-b`、`feat/dc-r2-be`、`feat/dc-r2-c`、`feat/def-device-01be`、`feat/def-proxy-0203`、`feat/req-access-mode-b1`、`feat/req-access-mode-f1`、`feat/req-decision-r2a`、`feat/req-progress-p0`、`feat/req-spk-rn`、`feat/req-spk-rn-be`、`task/feedback-ui-defects-20260924`、`task/local-engine-wpg-20260924`。
- **3 个有少量独有提交，删除前需确认**：`docs/req-spk-rn-t1-design`（3）、`feat/def-device-01a`（1，注意其后续 01be 已合入）、`feat/req-decision-center-b1`（3，落后 110，早期方案分支）。逐个 diff，有价值的摘出到 docs/，然后删除。
- **1 个保留候选**：`feature/performance-monitoring`（16 个独有提交，无隐私），干净仓库建好后 rebase 过去。

### 4.3 标签：16 个

v7.1.0~v7.4.5 共 13 个在 main 线上（随干净发布作废，新仓库不迁 tag）；v6.0.0、v7.0.0、v7.0.1 已悬空。**旧 tag 一律不迁**，借发布完成版本号治理（见 §7 第 4 步）。

## 5. 工作树卫生（B3，转 public 前完成）

- 根目录 204 张调试 PNG：已被 `.gitignore` 第 60 行 `/*.png` 覆盖（不会随 git 外泄），但"直接分享文件夹"仍泄露 — 移至仓库外归档或集中到 `docs/bug-fix-notes-assets/` 后清理根目录。
- 删除云盘副本 `LICENSE 2`、`VERSION 2`。
- ignored 复核通过：`.env`、`.eval_local_engine/`、`data/` 全部用户数据、`build/`、`voiceprint-service/models/` 均已忽略，`git status` 零未跟踪文件。

## 6. 两套方案对比

| | 方案 A：干净首提交 + 新建仓库（推荐） | 方案 B：二次 filter-repo 重写 |
|---|---|---|
| eval 42 文件及全部历史 | 天然不存在 | 需逐路径剥离，再全量 gc |
| 4 个历史 mock/bundle blob | 天然不存在 | 需额外 --path/callback 处理 |
| 17 个远端旧分支、16 旧 tag | 新仓库天然不带 | 必须逐个删 ref，漏一个即泄露 |
| 工作树 4 文件脱敏 | 在首提交中一次成型 | 需 --replace-text 全历史替换（34 个名字 × 全历史，diff 污染严重） |
| commit 迭代史 | 丢失（242 commit），由 CHANGELOG 与建设复盘文章承接叙事 | 保留，但已是第二轮重写（本仓库 10-04 刚发生过重写事故） |
| GitHub 侧旧 hash 残留 | **不存在**（新仓库没有旧对象） | force push 后旧 commit hash 仍可能被直接访问/被 fork 缓存，通常需联系 GitHub Support 等 GC |
| 工作量 | 半天 | 1~2 天，且需要再次全量验证 |
| 主要风险 | 叙事资产需要重新组织 | 任一远端 ref 漏删即失败；重写过程与微云同步盘并发有覆盖前科 |

## 7. 推荐执行步骤（方案 A）

> 标 🔒 的步骤改变远端或不可逆，必须项目方明确授权后执行；其余纯本地。

1. **本地完整备份（纯本地）**：`git bundle create ../oms-full-backup-20261004.bundle --all` + 确认 10-04 的 mirror 备份可检出；备份置于仓库与同步盘之外。
2. **工作树脱敏（纯本地，独立分支 staging/public-clean）**：
   - 删除 §2.1 的 42 个文件；按 §2.2 脱敏 4 个报告；按 §2.4 处理 6 处代码/文档残留；
   - 清理根目录 PNG 与云盘副本；
   - `pyproject.toml` 邮箱换 GitHub noreply（取值见 §2.4）；
   - 复核：重跑隐私扫描脚本，期望工作树零真名、零真实内网地址。
3. **造干净历史（纯本地）**：在脱敏后的树基础上 `git checkout --orphan` 生成单个首提交；提交信息注明"首个公开发布版本，早期开发历史保留于私有归档"。
4. **版本号治理（纯本地）**：**已定（2026-10-04）首发 `v1.0.0`**——VERSION、README（含 front-matter 现存的 2.1.0）、CHANGELOG 头部三处对齐为 1.0.0，旧版本叙事收敛进 CHANGELOG；"本地引擎"状态如实标注，打且只打 v1.0.0 一个新 tag。
5. 🔒 **新建 GitHub 仓库**（建议同名新仓；旧仓 rename 为 `*-private-archive` 私享留档，观察期后删除）：推送干净 main 与新 tag；`feature/performance-monitoring` rebase 后按需推送。
6. 🔒 **旧仓库收尾**：删除全部 17 个远端分支（含 main-legacy）；确认旧仓保持 private 直至删除；旧仓存在期间不向任何人授权。
7. **转 public 前剩余门禁**：安装并运行 `gitleaks detect --source <新仓库> --no-banner`（兜底，预期零命中）；完成清单 A3（FunASR/ModelScope 四模型许可与"引导下载不随包分发"核查，出 THIRD_PARTY_NOTICES）；B1 真机验收结论同步 README。
8. **门面（可与 2~7 并行）**：30 秒价值主张首屏、topics、demo GIF、截图版 Quickstart、首个 Release 资产、Issue 模板。

## 8. 不做的事

- 不向公开仓库迁移任何旧 ref、旧 tag、旧 bundle 对象。
- 不把声纹片段、评测音频、人工校对稿以"打码截图"形式重新引入（声纹属生物特征关联数据，不存在"轻度脱敏可用"）。
- 评测可复现性如未来需要，另立合成数据工程（虚构会议剧本 + TTS/真人朗读生成），不复用任何真实片段。
