"""
core/model_registry.py — 本地引擎模型清单与状态（R5 / WP-B）

模型清单依据 R8 本地引擎 Spike 报告 §2.1（D-R1 已采纳）：
全家桶四模型 ≈2.0GB；ct-punc（1.0GB）为唯一可裁剪大件（可选项）。
cam++ 同时服务说话人分离（R2）与声纹（R3），共用同一份权重。

存储布局（与 ModelScope SDK 默认缓存布局对齐，MODELSCOPE_CACHE 指向 model_dir）：
  {model_dir}/hub/{modelscope_id}/...    模型权重文件
  {model_dir}/.integrity.json            完整性清单（相对路径 → sha256/size）
  {model_dir}/**/*.part                  断点续传临时分片
"""

import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# 完整性清单读-改-写互斥锁：`"all"` 下载会并行多个线程，各自完成时写入同一份
# .integrity.json；无锁的 RMW 会 last-writer-wins 丢失条目，导致已下载模型被误判 missing。
# Guards the read-modify-write of .integrity.json against parallel "all" downloads.
_integrity_lock = threading.Lock()

MB = 1024 * 1024

# 完整性清单文件名 / Integrity manifest filename
INTEGRITY_MANIFEST_NAME = ".integrity.json"

# ModelScope 权重许可：引导下载、不内置分发（PRD R5 边界）；逐模型许可以 ModelScope 页面为准
MODELSCOPE_LICENSE_NOTE = "ModelScope（引导下载，不内置分发；许可以 ModelScope 模型页为准）"

# 模型清单 / Model manifest (Spike §2.1, D-R1)
MODEL_MANIFEST: list[dict] = [
    {
        "key": "seaco-paraformer-zh",
        "name": "SeACo-Paraformer 中文转写",
        "modelscope_id": "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
        "size_bytes": int(944 * MB),
        "purpose": "转写主模型（R2）",
        "optional": False,
        "license": MODELSCOPE_LICENSE_NOTE,
    },
    {
        "key": "fsmn-vad",
        "name": "FSMN-VAD 语音活动检测",
        "modelscope_id": "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
        "size_bytes": int(3.9 * MB),
        "purpose": "语音活动检测（R2）",
        "optional": False,
        "license": MODELSCOPE_LICENSE_NOTE,
    },
    {
        "key": "cam-plus",
        "name": "CAM++ 说话人分离/声纹",
        "modelscope_id": "iic/speech_campplus_sv_zh-cn_16k-common",
        "size_bytes": int(28 * MB),
        "purpose": "说话人分离（R2）与声纹（R3）共用权重",
        "optional": False,
        "license": MODELSCOPE_LICENSE_NOTE,
    },
    {
        "key": "ct-punc",
        "name": "CT-Transformer 标点恢复",
        "modelscope_id": "iic/punc_ct-transformer_cn-en-common-vocab471067-large",
        "size_bytes": int(1.0 * 1024 * MB),
        "purpose": "标点恢复（R2，可选项——唯一可裁剪大件，省 1.0GB）",
        "optional": True,
        "license": MODELSCOPE_LICENSE_NOTE,
    },
]

MODEL_BY_KEY = {m["key"]: m for m in MODEL_MANIFEST}

# 总下载体积（AC-3 预算 ≤3GB）/ Total download size
TOTAL_SIZE_ALL_BYTES = sum(m["size_bytes"] for m in MODEL_MANIFEST)
TOTAL_SIZE_REQUIRED_BYTES = sum(m["size_bytes"] for m in MODEL_MANIFEST if not m["optional"])


def get_model_dir() -> Path:
    """模型存储目录（B-2 修复，D-G3 (a)）。

    解析优先级：
      1. ``MODELSCOPE_CACHE`` 环境变量——引擎子进程内与宿主一致
         （宿主经 ``build_worker_env()`` 注入，冻结态引擎包无宿主 settings 可读）；
      2. settings ``engine.local.model_dir`` 显式配置；
      3. 平台默认锚点（``core.engine_paths.get_default_model_dir``）：
         开发态 ``data/models/``；冻结态 Win ``%LOCALAPPDATA%\\OpenMeetingScribe\\models``、
         mac ``~/Library/Application Support/OpenMeetingScribe/models``。
         冻结态禁止相对路径（会解析进只读 ``sys._MEIPASS`` bundle）。
    """
    import os

    env_dir = os.environ.get("MODELSCOPE_CACHE", "").strip()
    if env_dir:
        return Path(env_dir).expanduser()
    try:
        from app.settings_store import get_engine_config
        model_dir = get_engine_config()["local"]["model_dir"]
    except Exception:
        model_dir = ""
    if model_dir:
        return Path(model_dir).expanduser()
    from core.engine_paths import get_default_model_dir
    return get_default_model_dir()


def get_model_root(model_key: str) -> Path:
    """单个模型的权重根目录（ModelScope SDK 兼容布局 hub/{id}）。"""
    meta = MODEL_BY_KEY[model_key]
    return get_model_dir() / "hub" / meta["modelscope_id"]


def load_integrity_manifest() -> dict:
    """读取完整性清单 {model_key: {rel_path: {"sha256":..., "size":...}}}。"""
    path = get_model_dir() / INTEGRITY_MANIFEST_NAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"完整性清单读取失败: {e}")
        return {}


def save_integrity_entry(model_key: str, files: dict) -> None:
    """写入单个模型的完整性记录（下载成功后调用）。

    读-改-写全程持 _integrity_lock，并通过 atomic_write_json 原子落盘，
    避免并行下载（"all"）时条目被覆盖丢失或读到半截文件。
    """
    from core.fs_atomic import atomic_write_json

    path = get_model_dir() / INTEGRITY_MANIFEST_NAME
    with _integrity_lock:
        manifest = load_integrity_manifest()
        manifest[model_key] = files
        atomic_write_json(path, manifest)


def get_disk_free_bytes(path: Path | None = None) -> int:
    """目标盘剩余空间 / Free disk space for the target volume."""
    import shutil
    target = Path(path) if path else get_model_dir()
    # 目录可能尚不存在，向上找最近的存在祖先 / Walk up to nearest existing ancestor
    probe = target
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free
