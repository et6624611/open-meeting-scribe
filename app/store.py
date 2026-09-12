"""
app/store.py — 共享状态层（兼容入口）

作者：王永亮
创建：2026-09-03
版本：2.0.0

集中管理所有跨路由的共享状态、配置常量与辅助函数。
各 router 模块通过 import 引用，避免循环依赖。

v2.0 重构：实际逻辑已拆分至以下子模块，本文件作为兼容层
  统一 re-export，确保所有既有 import 路径不受影响。
  - app/task_store.py       — 任务持久化与恢复
  - app/settings_store.py   — 设置管理
  - app/realtime_store.py   — 实时消息推送状态
  - core/pipeline_runner.py — 管线编排（后台执行）
"""

import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# ============================================================
# 目录常量（保留在本模块，被多个路由直接引用）
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

OUTPUT_DIR = Path("data/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

RECORDINGS_DIR = Path("data/recordings")
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

# 录制设备名（默认麦克风，可通过环境变量覆盖；线上会议戴耳机场景可改为 "BlackHole 2ch"）
RECORD_DEVICE = os.getenv("RECORD_DEVICE", "MacBook Pro麦克风")

# ============================================================
# 兼容 re-export：设置管理
# ============================================================
from app.settings_store import (  # noqa: E402, F401
    HOTWORDS_FILE,
    HOTWORD_MAPPINGS_FILE,
    SETTINGS_FILE,
    PHILOSOPHIES_FILE,
    load_settings,
    save_settings_to_disk,
    mask_api_key,
    get_active_api_key,
    get_llm_config,
    get_asr_config,
    get_voiceprint_config,
    get_feature_flags,
    get_silence_detection_config,
)

# ============================================================
# 兼容 re-export：任务持久化
# ============================================================
from app.task_store import (  # noqa: E402, F401
    TASKS_DIR,
    tasks,
    infer_task_source,
    save_task_to_disk,
    load_tasks_from_disk,
    recover_interrupted_tasks,
)

# ============================================================
# 兼容 re-export：实时状态
# ============================================================
from app.realtime_store import (  # noqa: E402, F401
    realtime_queues,
    realtime_transcribers,
    realtime_diarizers,
    realtime_summarizers,
    realtime_chapter_generators,
    realtime_transcript_buffers,
    realtime_full_transcripts,
    realtime_speaker_maps,
    event_loop,
    realtime_last_heartbeat,
    realtime_last_sentence,
    realtime_presence_scores,
    realtime_silence_warnings,
    realtime_silence_monitors,
    REALTIME_BUFFER_MAX,
    push_realtime_msg,
    resolve_realtime_speaker_name,
)

# ============================================================
# 兼容 re-export：管线编排
# ============================================================
from core.pipeline_runner import (  # noqa: E402, F401
    SPEAKER_COUNT_MIN,
    SPEAKER_COUNT_MAX,
    PIPELINE_MAX_RETRIES,
    PIPELINE_RETRY_DELAYS,
    estimate_speaker_count,
    run_pipeline_task,
    run_stage2_task,
)
