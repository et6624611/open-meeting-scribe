---
id: WP-G1
title: 冻结态三缺陷（B-1/B-2/B-3）复现记录与修复口径
version: 1.0.0
status: done（修复随 G-2/G-3 同分支落地）
date: 2026-09-24
owner: DevOps 工程师（waker 78087de278c8）
source: docs/WP-G-R8-PACKAGING-DISPATCH.md §2（B-1/B-2/B-3）、§3（D-G1/D-G3 裁决）
branch: task/local-engine-wpg-20260924
---

# G-1 · 三缺陷最小复现 + 修复口径

复现方式说明：三缺陷均为**冻结态（PyInstaller frozen）**路径缺陷，最小复现以
「代码级证据链 + 可执行单测模拟冻结态」完成（单测 monkeypatch `sys.frozen` /
`sys._MEIPASS` / `sys.executable`，见 `tests/test_engine_packaging_g3.py`）。
真机冻结包复现留给 G-6 CI 冒烟与真机验收（AC-1），此处不做 25min+ 的本地冻结全量构建。

## B-1｜引擎子进程形态与云包瘦身互斥（最高优先）

**证据链**：
1. `core/engine_host.py` `build_worker_command()`：冻结态返回 `[sys.executable, "--engine-worker"]`——把引擎当**主 exe 再入进程**拉起。
2. `build/pyinstaller.spec` `excludes=['torch','torchaudio',...]`；`build/pyinstaller_macos.spec` 同样排除——主 exe 冻结图内**无 torch/funasr**（AC-7 云包零增长的既定屏障，`requirements.txt` 已无 torch）。
3. `core/engine_worker.py` `_get_asr_model()` 惰性 `from funasr import AutoModel`——再入进程执行到此处必然 `ModuleNotFoundError`。

**最小复现**：任何按主包 spec 构建的冻结包中触发本地转写（`engine_host.infer`）→ 子进程 ping 可通（`engine_worker.main` 顶层不 import funasr），但首次 `cmd=infer` 即 worker_error（funasr 缺失），或若 hiddenimports 收敛后直接启动失败。

**修复口径（D-G1 方案 A，已裁决）**：
- 新增 `build/pyinstaller_engine.spec` 产出**独立引擎包**（onedir，`OMSEngine(.exe)` + `_internal/`，含 torch/funasr/modelscope 全套）；**主包 spec 一字不动**。
- 冻结态 `build_worker_command()` 改为定位外置引擎可执行体（搜索序见 G-3），不再再入主 exe。
- `--engine-worker` 再入分派保留为**开发态/降级路径**（`desktop.py` 入口分派不动），冻结态正式路径只走独立引擎包（D-G1 子项②）。
- 引擎根携带 `engine-manifest.json`（组件名/引擎版本/协议版本/逐文件 SHA256），由 `build/make_engine_manifest.py` 构建期生成；协议版本不匹配 → 拒绝启动 + 「请升级本地引擎组件」，**不静默回退云端**（D-G1 子项③，`can_fallback_cloud=False`）。

## B-2｜模型目录相对路径，冻结态指进只读 bundle

**证据链**：
1. `core/model_registry.py` `get_model_dir()`：默认 `data/models/`（**相对路径**），来自 `app/settings_store.py` `DEFAULT_MODEL_DIR`。
2. `core/engine_host.py` `EngineHost.start()`：子进程 `cwd=Path(__file__).parent.parent`——冻结态 `__file__` 在 `sys._MEIPASS` 内，`cwd` 即**只读 bundle 根**；相对 `data/models/` 解析进 bundle。
3. 对照正确写法：`core/audio.py` `_ensure_ffmpeg_in_path()`（exe 同级解析）、`desktop.py` `_setup_desktop_env()`（`.env` 用 exe 同级）。

**最小复现**：`tests/test_engine_packaging_g3.py::test_b2_frozen_relative_model_dir_points_into_bundle`——模拟冻结态断言旧行为（`get_model_dir()` resolve 后落在 `_MEIPASS` 下）；修复后同文件断言新行为（落平台锚点）。

**修复口径（D-G3 (a)，已裁决）**：
- 新增 `core/engine_paths.py` 统一平台锚点：
  - 冻结态 Win：`%LOCALAPPDATA%\OpenMeetingScribe\`（models\ / logs\ / engine\）
  - 冻结态 mac：`~/Library/Application Support/OpenMeetingScribe/`
  - 开发态：项目根 `data/`（不变，`data/models/`）
- `settings_store.get_engine_config()` 的 `model_dir` 默认值改为按平台锚点计算（用户显式配置仍优先）。
- 引擎子进程 `cwd` 冻结态改为引擎根目录（可执行体同级），不再用 `__file__` 推导。
- `model_registry.get_model_dir()` 增加 `MODELSCOPE_CACHE` 环境变量优先（引擎子进程内与宿主一致，宿主经 `build_worker_env()` 注入）。

## B-3｜引擎子进程 stderr 被丢弃，冻结首启失败不可诊断

**证据链**：
1. `core/engine_host.py` `start()`：`stderr=subprocess.DEVNULL`。
2. Spike §3.2：冻结态 funasr import 最高 86s、spawn 重复引导 5–6 次；`engine_worker.py` `__main__` 将 logging 配置到 **stderr**——即引擎侧全部日志在冻结态被丢弃。
3. 后果：组件装错/版本不匹配时用户只见 `engine_unhealthy`，任务日志零信息。

**最小复现**：`tests/test_engine_packaging_g3.py::test_b3_stderr_captured_into_logs`——以真实子进程（`python -c` 向 stderr 写标记行）驱动 `EngineHost`，断言 stderr 摘要进入宿主日志缓冲与 `<锚点>/logs/engine-stderr.log`。

**修复口径**：
- `stderr=subprocess.PIPE` + 守护读取线程：逐行进 `logger.warning`、环形缓冲（最近 200 行）、追加写 `<运行时锚点>/logs/engine-stderr.log`。
- 启动失败（ping 超时/协议不匹配/进程早退）时，`error.detail` 携带 stderr 尾部摘要（截断至 2000 字符，做最小脱敏：掩去形如 `sk-…`/`token=…`/`key=…` 的凭据样式），对齐 AC-8 可观测与 `core/joblog.py` 的脱敏精神。
- Windows 侧子进程加 `CREATE_NO_WINDOW`，避免 GUI 主程序拉起引擎时闪控制台窗。

## 验收对照（WP-G §6）

- 判据 4「B-3 可诊断性」：损坏引擎包 → 任务日志可见引擎侧 stderr 摘要——由 `test_b3_*` 单测覆盖逻辑层，真机层留 G-6/AC-1。
- 三缺陷修复均不触碰主包 spec（AC-7 判据 2：`git diff` 后 `build/pyinstaller.spec` 无变更）。
