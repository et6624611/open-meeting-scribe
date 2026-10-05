"""
core/perf.py — 轻量性能监控工具 / Lightweight performance monitoring tool

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-08
版本 / Version: 1.0.0

职责 / Responsibilities:
  1. 提供统一的耗时计时上下文管理器 / 装饰器 / Provide unified timing context manager / decorator
  2. 收集各阶段耗时，支持任务级汇总 / Collect stage timings, support task-level aggregation
  3. 输出结构化性能日志，便于定位瓶颈 / Output structured performance logs for bottleneck analysis

使用方式 / Usage:
  from core.perf import perf_timer, PerfCollector

  # 方式一 / Option 1：上下文管理器 / Context manager
  with perf_timer("阶段名 / stage_name") as t:
      ...
  # 自动记录 / Auto-log: [PERF] 阶段名: 1.234s

  # 方式二 / Option 2：任务级收集器 / Task-level collector (aggregates multiple stages)
  collector = PerfCollector("task_id")
  collector.time("归一化 / normalize", normalize_audio, ...)
  collector.time("转写 / transcribe", transcribe_audio, ...)
  collector.dump()  # 输出汇总日志 / Output aggregated log
"""

import functools
import logging
import time

logger = logging.getLogger(__name__)

# 慢操作告警阈值（秒），超过此值的操作会在日志中以 WARNING 级别标记 / Slow operation warning thresholds (seconds)
SLOW_THRESHOLD = {
    "ffmpeg_normalize": 30,     # 音频归一化超过 30s 告警 / Audio normalization > 30s
    "transcribe": 120,          # 转写超过 2 分钟告警 / Transcription > 2 min
    "llm_sync": 30,             # LLM 同步调用超过 30s 告警 / LLM sync call > 30s
    "llm_async": 30,            # LLM 异步调用超过 30s 告警 / LLM async call > 30s
    "pipeline_stage1": 300,     # 管线第一阶段超过 5 分钟告警 / Pipeline stage 1 > 5 min
    "pipeline_stage2": 120,     # 管线第二阶段超过 2 分钟告警 / Pipeline stage 2 > 2 min
    "voiceprint_extract": 30,   # 声纹提取超过 30s 告警 / Voiceprint extraction > 30s
    "voiceprint_match": 10,     # 声纹匹配超过 10s 告警 / Voiceprint matching > 10s
}


class perf_timer:
    """
    耗时计时上下文管理器 / Timing context manager.

    用法 / Usage:
        with perf_timer("归一化 / normalize") as t:
            normalize_audio(...)
        # 日志输出 / Log output: [PERF] 归一化: 1.234s

    也可作为装饰器 / Can also be used as decorator:
        @perf_timer("归一化 / normalize")
        def normalize_audio(...):
            ...
    """

    def __init__(self, name: str, category: str | None = None):
        """
        Args:
            name: 操作名称（用于日志标识） / Operation name (for log identification)
            category: 性能分类（用于慢操作告警阈值匹配），为 None 时不告警 / Performance category (for slow operation threshold matching), None = no warning
        """
        self.name = name
        self.category = category
        self.elapsed = 0.0
        self._start = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed = time.perf_counter() - self._start
        self._log()

    def __call__(self, func):
        """作为装饰器使用 / Used as decorator"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with self:
                return func(*args, **kwargs)
        return wrapper

    def _log(self):
        # 检查是否超过慢操作阈值 / Check if exceeds slow operation threshold
        threshold = SLOW_THRESHOLD.get(self.category) if self.category else None
        if threshold and self.elapsed > threshold:
            logger.warning(
                f"[PERF] ⚠ {self.name}: {self.elapsed:.3f}s "
                f"(超过阈值 {threshold}s)"
            )
        else:
            logger.info(f"[PERF] {self.name}: {self.elapsed:.3f}s")


class PerfCollector:
    """
    任务级性能收集器 / Task-level performance collector.

    收集多个阶段的耗时，最终 dump() 输出汇总日志 / Collect timings for multiple stages, dump() outputs aggregated log.
    适合在管线任务中使用，一次性看到各阶段耗时分布 / Ideal for pipeline tasks, see all stage timings at a glance.

    用法 / Usage:
        collector = PerfCollector("abc123")
        collector.time("归一化 / normalize", normalize_audio, audio_path)
        collector.time("转写 / transcribe", transcribe_audio, file_path)
        collector.dump()
        # 日志输出 / Log output:
        # [PERF] abc123 归一化: 1.234s
        # [PERF] abc123 转写: 45.678s
        # [PERF] abc123 总计: 46.912s
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.records: list[tuple[str, float]] = []
        self._total_start = time.perf_counter()

    def time(self, name: str, func, *args, category: str | None = None, **kwargs):
        """
        计时执行一个函数 / Timed function execution.

        Args:
            name: 操作名称 / Operation name
            func: 要执行的函数 / Function to execute
            *args, **kwargs: 函数参数 / Function arguments
            category: 性能分类（用于慢操作告警） / Performance category (for slow operation warning)
        """
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            elapsed = time.perf_counter() - start
            self.records.append((name, elapsed))
            self._log_one(name, elapsed, category)
            return result
        except Exception:
            elapsed = time.perf_counter() - start
            self.records.append((name, elapsed))
            self._log_one(name, elapsed, category)
            raise

    def record(self, name: str, elapsed: float, category: str | None = None):
        """手动记录一个耗时（不执行函数，仅记录） / Manually record a duration (no function execution, record only)"""
        self.records.append((name, elapsed))
        self._log_one(name, elapsed, category)

    def dump(self):
        """输出汇总日志 / Output aggregated log"""
        total = time.perf_counter() - self._total_start
        prefix = f"[PERF] {self.task_id[:8]}"
        for name, elapsed in self.records:
            logger.info(f"{prefix} {name}: {elapsed:.3f}s")
        logger.info(f"{prefix} 总计: {total:.3f}s")
        return total

    def _log_one(self, name: str, elapsed: float, category: str | None = None):
        prefix = f"[PERF] {self.task_id[:8]}"
        threshold = SLOW_THRESHOLD.get(category) if category else None
        if threshold and elapsed > threshold:
            logger.warning(
                f"{prefix} ⚠ {name}: {elapsed:.3f}s "
                f"(超过阈值 {threshold}s)"
            )
        else:
            logger.info(f"{prefix} {name}: {elapsed:.3f}s")
