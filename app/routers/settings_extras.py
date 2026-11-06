"""app/routers/settings_extras.py — 系统提示词查看 + 存储管理。

端点：
  GET  /api/system-prompts         — 系统级提示词列表（只读）
  GET  /api/storage/usage          — 存储用量统计（60s 缓存）
  POST /api/storage/clean          — 清理所有中间产物
  POST /api/storage/clean-orphaned — 仅清理冗余文件

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-05（从 settings.py 拆分）
"""

import logging
import time
from pathlib import Path

from fastapi import APIRouter

from app.routers.chat import CHAT_SYSTEM_PROMPT
from core.realtime_summary import SUMMARY_SYSTEM_PROMPT
from core.summarize import SYSTEM_PROMPT, TITLE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# 系统提示词查看（只读，增加软件开放性） / System Prompt Viewer (read-only; for openness)
# ============================================================

# 提示词注册表：名称 → (来源模块, 提示词内容, 用途说明) / Prompt registry: name → (module, prompt, purpose)
SYSTEM_PROMPTS = {
    "会议纪要生成": {
        "module": "core/summarize.py",
        "description": "批处理管线生成会议纪要时使用的系统提示词，指导 LLM 按结构化模板输出纪要",
        "prompt": SYSTEM_PROMPT,
    },
    "会议标题生成": {
        "module": "core/summarize.py",
        "description": "根据对话内容自动生成会议标题",
        "prompt": TITLE_SYSTEM_PROMPT,
    },
    "实时增量总结": {
        "module": "core/realtime_summary.py",
        "description": "录音过程中每分钟触发一次增量总结，指导 LLM 在已有总结基础上整合新内容",
        "prompt": SUMMARY_SYSTEM_PROMPT,
    },
    "AI 对话助手": {
        "module": "app/routers/chat.py",
        "description": "右侧 AI 对话框的基础系统提示词，定义助手能力边界与回复风格",
        "prompt": CHAT_SYSTEM_PROMPT,
    },
}


@router.get("/api/system-prompts")
async def get_system_prompts():
    """获取系统级提示词列表 / Get system prompt list (read-only)."""
    return SYSTEM_PROMPTS


# ============================================================
# 存储管理 / Storage Management
# ============================================================

# 存储用量缓存（60 秒过期，避免频繁 I/O） / Storage usage cache (60s TTL; avoids frequent I/O)
_storage_usage_cache: dict = {}
_storage_usage_cache_time: float = 0
_STORAGE_CACHE_TTL = 60  # 秒 / seconds


def _scan_dir_usage(dir_path: Path) -> dict:
    """扫描目录 / Scan directory."""
    size = 0
    count = 0
    if dir_path.exists():
        for f in dir_path.iterdir():
            if f.is_file():
                size += f.stat().st_size
                count += 1
    return {"size_bytes": size, "file_count": count}


def _scan_intermediate_usage() -> dict:
    """扫描中间产物 / Scan intermediate artifacts."""
    normalized_size = 0
    normalized_count = 0
    raw_size = 0
    raw_count = 0
    dup_size = 0
    dup_count = 0

    for scan_dir in [Path("data/recordings"), Path("data/uploads")]:
        if not scan_dir.exists():
            continue
        for f in scan_dir.iterdir():
            if not f.is_file():
                continue
            if "_normalized_normalized" in f.name:
                dup_size += f.stat().st_size
                dup_count += 1
            elif f.suffix == ".raw":
                raw_size += f.stat().st_size
                raw_count += 1
            elif "_normalized" in f.name and f.suffix == ".wav":
                normalized_size += f.stat().st_size
                normalized_count += 1

    return {
        "normalized_files": {"size_bytes": normalized_size, "file_count": normalized_count},
        "raw_files": {"size_bytes": raw_size, "file_count": raw_count},
        "duplicate_normalized": {"size_bytes": dup_size, "file_count": dup_count},
    }


@router.get("/api/storage/usage")
def get_storage_usage():
    """获取存储用量统计（含 60 秒缓存） / Get storage usage stats (60s cache)."""
    global _storage_usage_cache, _storage_usage_cache_time

    now = time.time()
    if _storage_usage_cache and (now - _storage_usage_cache_time) < _STORAGE_CACHE_TTL:
        return _storage_usage_cache

    recordings = _scan_dir_usage(Path("data/recordings"))
    uploads = _scan_dir_usage(Path("data/uploads"))
    tasks_usage = _scan_dir_usage(Path("data/tasks"))
    output = _scan_dir_usage(Path("data/output"))
    intermediate = _scan_intermediate_usage()

    total = recordings["size_bytes"] + uploads["size_bytes"] + tasks_usage["size_bytes"] + output["size_bytes"]
    reclaimable = (
        intermediate["normalized_files"]["size_bytes"]
        + intermediate["raw_files"]["size_bytes"]
        + intermediate["duplicate_normalized"]["size_bytes"]
    )

    result = {
        "recordings": recordings,
        "uploads": uploads,
        "tasks": tasks_usage,
        "output": output,
        "intermediate": intermediate,
        "total_bytes": total,
        "reclaimable_bytes": reclaimable,
    }

    _storage_usage_cache = result
    _storage_usage_cache_time = now
    return result


@router.post("/api/storage/clean")
def clean_intermediate_files():
    """清理所有中间产物 / Cleanup all intermediate artifacts."""
    from app.store import cleanup_orphaned_intermediate_files

    # 先执行启动清理 / First run startup cleanup
    result = cleanup_orphaned_intermediate_files()

    # 再清理所有归一化文件 / Then cleanup all normalized files
    normalized_freed = 0
    normalized_count = 0
    for scan_dir in [Path("data/recordings"), Path("data/uploads")]:
        if not scan_dir.exists():
            continue
        for f in scan_dir.iterdir():
            if f.is_file() and "_normalized" in f.name and f.suffix == ".wav":
                size = f.stat().st_size
                try:
                    f.unlink()
                    normalized_count += 1
                    normalized_freed += size
                except Exception as e:
                    logger.warning(f"清理归一化文件失败: {f.name}: {e}")

    # 清除缓存 / Clear cache
    global _storage_usage_cache, _storage_usage_cache_time
    _storage_usage_cache = {}
    _storage_usage_cache_time = 0

    total_freed = result["freed_bytes"] + normalized_freed
    logger.info(
        f"[存储] 手动清理完成: "
        f"归一化 {normalized_count} 个 ({normalized_freed / 1024 / 1024:.1f} MB) + "
        f"冗余 {result['duplicate_normalized']} 个 + "
        f"孤儿 .raw {result['orphan_raw']} 个 = "
        f"总计 {total_freed / 1024 / 1024:.1f} MB"
    )

    return {
        "cleaned": {
            "normalized_files": {"count": normalized_count, "freed_bytes": normalized_freed},
            "duplicate_normalized": {"count": result["duplicate_normalized"], "freed_bytes": result["freed_bytes"] - result.get("_raw_freed", 0)},
            "orphan_raw": {"count": result["orphan_raw"]},
        },
        "total_freed_bytes": total_freed,
    }


@router.post("/api/storage/clean-orphaned")
def clean_orphaned_files():
    """仅清理冗余文件 / Cleanup redundant files only."""
    from app.store import cleanup_orphaned_intermediate_files

    result = cleanup_orphaned_intermediate_files()

    # 清除缓存 / Clear cache
    global _storage_usage_cache, _storage_usage_cache_time
    _storage_usage_cache = {}
    _storage_usage_cache_time = 0

    return {
        "cleaned": {
            "duplicate_normalized": result["duplicate_normalized"],
            "orphan_raw": result["orphan_raw"],
        },
        "freed_bytes": result["freed_bytes"],
    }
