# WP-G + CI 缺陷 · 阶段性回报（DevOps工程师 → 产品经理）

日期：2026-09-24（v2，按项目方裁决更新 G-7 状态与交付口径） ｜ **v10 交付口径收敛**：mac L2（引擎组件应用内一键落位，G-4b）+ Windows L1（Inno [Components]，G-4）+ Windows 冻结冒烟（G-6） ｜ 分支：`task/local-engine-wpg-20260924`（本地已提交，**待 push 确认**）、`fix/ci-local-engine-20260924`（已合入 main）

## 1. CI 缺陷（B 包）：根因链闭环，冒烟本体已全绿

- 根因三层全部修复：①workflow 元数据注册（改名重注册）→ ②job 级 `env:` 使用 `runner` 上下文导致整个 workflow 编译失败（HTTP 422，解释了 0s/0 jobs/name 不解析/paths 失效全部症状）→ ③内容级缺陷（cp1252 中文崩溃、TOC 扫描误报、`[STUB] PASS` 契约断言不匹配、诊断性上传被账号 artifact 配额误杀）。
- **历史性进展**：run 35948224216 首次真实执行两个 job。Windows 冻结冒烟本体全部通过：torch 2.14.0+cpu import → funasr import → multiprocessing spawn 冻结子进程 → AutoModel 替身权重加载链 → generate 推理产出文本 → MODELSCOPE_CACHE 零文件守护（未触发任何真实下载）。AC-7 体积守护 `[SIZE] PASS`。
- 末段两个非本体失败已修（commit `1366a5c`，已合 main）：stub 末行补契约字面 `[STUB] PASS`；冒烟日志/体积报告两处 `upload-artifact` 加 `continue-on-error: true`。
- ✅ **验证 run 35949609223 首次双 job 全绿**（main@a7aac5d）：「Windows 冻结引擎替身冒烟（WP-D）」success + 「AC-7 云精简包体积守护」success。G-6 local 链路冒烟（替身权重）随本 run 达成。
- ⚠️ **需项目方决策**：GitHub 账号级 artifact 存储配额已满（`Failed to CreateArtifact: Artifact storage quota has been hit`）。删除历史 artifacts 属共享资源操作，我不擅自执行；请项目方选择：清理历史 artifacts 或升级存储配额。

## 2. WP-G 交付状态（A 包）

| 子任务 | 状态 | 说明 |
| --- | --- | --- |
| G-1 三缺陷复现+修复口径 | ✅ | `docs/WP-G1-DEFECTS-REPRO-FIX.md`；B-1/B-2/B-3 修复全部落地 |
| G-2 引擎包 spec+manifest | ✅ | `build/pyinstaller_engine.spec`（onedir，主包 spec 一字不动）+ `engine_entry.py` + `build/make_engine_manifest.py`（protocol_version 握手） |
| G-3 engine_host 改造 | ✅ | `core/engine_paths.py` 平台锚点（D-G3）；4 级搜索序；stderr 环形缓冲+脱敏+落盘（B-3）；协议不匹配拒绝启动+可行动提示（D-G5），不静默回退云端 |
| G-4 Win Inno 组件 | ✅ | `[Types] standard/full/custom` + `[Components] engine`；standard 云模式体积不变；`docs/ENGINE-COMPONENT-OFFLINE-PACK.md` 离线包手册 |
| G-4b mac 应用内一键落位 | ✅（后端） | `core/engine_installer.py`（zip sha256→zip-slip 防护→manifest 逐文件校验→原子换入 `<锚点>/engine/`，含剥壳误判修复）+ `/api/engine/component/*` 路由 |
| G-5 首启引导接 UI | ⛔ 需协调 | 前端接线撞上 6 个在途 WIP 文件（`frontend/src/api/engine.ts`、`stores/engine.ts`、`SettingsView.vue`），按纪律不碰；后端数据源已就绪（component 三态+安装进度轮询 API），请 PM 协调 WP-F UI owner 接线 |
| G-6 CI local 冒烟 | ✅ | run 35949609223 双 job 全绿：冻结冒烟（import/spawn/加载链/推理/零真实下载守护）+ AC-7 体积守护 |
| G-7 mac 签名+公证+dmg | ⏸ **DEFERRED（移出 v10）** | 项目方 2026-09-24 裁决「暂时不考虑 Apple 开发者账号与凭据」。已交付的脚本链（`build/macos_sign_notarize.sh` + entitlements + build-macos.yml 改造）保留备查、头部已加 DEFERRED 标注，不再推进、不催凭据 |

- 测试：新增 43 例（`test_engine_packaging_g3.py` 23 + `test_engine_installer_g4.py` 20）全绿；全量 303 passed 无回归（worktree 环境差异已排除：补 `.env`/`data/settings.json`/`philosophies.json` 后与主工作区一致）。
- 提交：4 批（`e31aa3f` feat G-2/G-3、`a83154c` feat G-4/G-4b、`fd1b699` ci G-7+build-engine、`0f6bb77` docs）+ 本报告。6 个在途文件未触碰，全程逐文件 stage。
- **请求确认**：`task/local-engine-wpg-20260924` 分支 push 到 origin。

## 3. AC-10 验收口径预判

- L2（引擎组件应用内一键落位）：双平台后端就绪；剩余依赖 `build-engine.yml` 首跑（引擎包产物）+ G-5 前端接线。
- L1（mac .dmg+签名+公证）：**DEFERRED，移出 v10**（项目方 2026-09-24 裁决）。发布材料口径硬约束：不得出现「macOS 一键安装」字样，只可写「macOS 支持应用内一键安装本地引擎组件」——已排查本报告/离线包手册/workflow/installer 脚本，现有措辞均合规。
- 组件三态截图：需真机/冻结包，待 G-6 绿灯后补。
