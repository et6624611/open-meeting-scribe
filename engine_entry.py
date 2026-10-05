#!/usr/bin/env python3
"""
engine_entry.py — 独立引擎包（OMSEngine）冻结入口（R8 / WP-G，D-G1 方案 A）

由 build/pyinstaller_engine.spec 冻结为 onedir 引擎包的可执行体：
  <引擎根>/OMSEngine(.exe) + <引擎根>/_internal/ + <引擎根>/engine-manifest.json

行为与 `python -m core.engine_worker`（开发态路径）完全一致：
stdin/stdout JSON Lines 协议；stderr 为日志通道（宿主 core/engine_host.py 收集，B-3 修复）。

注意：本入口只在引擎包内使用；主应用冻结包（desktop.py）不包含 torch/funasr，
`--engine-worker` 再入分派保留为开发态/降级路径（D-G1 子项②）。
"""

import multiprocessing
import sys


def _run() -> int:
    # Spike §3.2 / PRD R5 实施约束②：冻结包多进程必须显式 freeze_support，
    # 防止引擎包被子子进程重复引导（观察到 import 重复 5–6 次）
    multiprocessing.freeze_support()

    import logging
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    from core.engine_worker import main as engine_worker_main
    return engine_worker_main()


if __name__ == "__main__":
    sys.exit(_run())
