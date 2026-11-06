"""app/routers/record.py — 录制控制 + 实时总结/绑定 聚合入口。

原 record.py（1093 行，2026-11-05 拆分为 5 模块）：
  record_devices.py   — 设备枚举/诊断/设置
  record_lifecycle.py — 开始/停止录制（主流程）
  record_state.py     — 状态查询 + 暂停/恢复/放弃 + 僵尸清理
  record_summary.py   — 实时总结控制
  record_speakers.py  — 实时说话人绑定

**禁止 `from app.store import X` 对标量**（RECORDINGS_DIR、_stream_task_id）——
普通 import 在模块加载时快照值，初始 None 会永远卡住。可变 dict（realtime_*）按值
import 安全；标量（RECORDINGS_DIR、_stream_task_id）必须 `import app.store as store`
后 `store.RECORDINGS_DIR` 模块引用读取。

测试直接从本模块 import（test_def_device_01be.py:101）：
  RecordDeviceRequest, set_record_device —— re-export 保持兼容。
测试 monkeypatch 本模块属性（test_local_engine_wph/wpi.py）：
  is_stream_recording / start_recording_with_stream / RealtimeTranscriber /
  create_realtime_diarizer / get_feature_flags / push_realtime_msg / start_record
  —— record_lifecycle 内经 _rec() 穿透访问，patch 落点即本命名空间。
"""

from fastapi import APIRouter

# patch 落点 re-export（测试 monkeypatch record.X；lifecycle 经 _rec().X 穿透）
from app.store import (  # noqa: F401
    get_feature_flags,
    push_realtime_msg,
    realtime_diarizers,
    realtime_full_transcripts,
    realtime_queues,
    realtime_speaker_maps,
    realtime_transcribers,
    tasks,
)
from core.audio import (  # noqa: F401
    is_stream_recording,
    start_recording_with_stream,
)
from core.diarization import create_realtime_diarizer  # noqa: F401
from core.realtime_asr import RealtimeTranscriber  # noqa: F401

from .record_devices import (  # noqa: F401 — 测试与外部 import 依赖
    RecordDeviceRequest,
    set_record_device,
)
from .record_devices import (
    router as _devices_router,
)
from .record_lifecycle import (
    router as _lifecycle_router,
)
from .record_lifecycle import start_record, stop_record  # noqa: F401
from .record_speakers import (
    router as _speakers_router,
)
from .record_state import (
    router as _state_router,
)
from .record_summary import (
    router as _summary_router,
)

router = APIRouter(tags=["record"])
router.include_router(_devices_router)
router.include_router(_lifecycle_router)
router.include_router(_state_router)
router.include_router(_summary_router)
router.include_router(_speakers_router)
