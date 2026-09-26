"""
core/voiceprint_registry.py — 声纹数据层：常量 + 注册表 + 匹配算法 / Voiceprint data layer: constants + registry + matching algorithm

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-03
版本 / Version: 2.0.0

职责 / Responsibilities:
  - 配置常量（阈值、维度、版本兼容） / Configuration constants (thresholds, dimensions, version compatibility)
  - VoiceprintRecord 数据模型 / VoiceprintRecord data model
  - 注册表 I/O（load/save） / Registry I/O (load/save)
  - 声纹注册/删除/状态查询 / Voiceprint registration/deletion/status query
  - 余弦相似度匹配（含 margin 双重门槛） / Cosine similarity matching (with margin dual threshold)

从 core/voiceprint.py 拆分而来 / Split from core/voiceprint.py.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ============================================================
# 配置常量
# ============================================================

# 数据目录
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# 声纹注册表文件
REGISTRY_FILE = DATA_DIR / "voiceprint_registry.json"

# 声纹模型版本标识。REQ-SETTINGS-IA 第 4 刀（云端声纹下架）后恒为本机 "cam++-v1"；
# 存量 "cam++-v1-cloud" 标记记录经下方兼容集继续可匹配——注册表无需用户数据迁移（ADR-0009）。
VOICEPRINT_MODEL_VERSION = "cam++-v1"

# 兼容版本集合：本机 cam++-v1 与历史云端 cam++-v1-cloud 提取的 embedding 可互相匹配
# （同一 CAM++ 权重与 CMN 前处理口径，同片段 cos=1.0 已验证）。
# 云端链路下架后本集合是存量云标记特征的唯一兼容通道，保留至自然被覆盖，参见 ADR-0009。
COMPATIBLE_VERSIONS: dict[str, set[str]] = {
    "cam++-v1": {"cam++-v1", "cam++-v1-cloud"},
    "cam++-v1-cloud": {"cam++-v1", "cam++-v1-cloud"},
}


def _is_compatible_version(record_version: str) -> bool:
    """检查注册表记录的模型版本是否与当前 encoder 兼容"""
    compatible = COMPATIBLE_VERSIONS.get(VOICEPRINT_MODEL_VERSION)
    if compatible is None:
        return record_version == VOICEPRINT_MODEL_VERSION
    return record_version in compatible


# 各模型版本的嵌入维度（用于过滤维度不一致的注册记录）
_MODEL_EMBEDDING_DIM: dict[str, int] = {
    "cam++-v1": 192,
    "cam++-v1-cloud": 192,
}


def _get_expected_embedding_dimension() -> int:
    """返回当前 encoder 版本的嵌入维度"""
    return _MODEL_EMBEDDING_DIM.get(VOICEPRINT_MODEL_VERSION, 192)


# 余弦相似度阈值（CAM++ 在中文语料上判别力显著优于旧版 GE2E，
# 不再需要 cohort centering 补丁；阈值待离线评测集标定后微调）
MATCH_THRESHOLD = 0.50
MIN_MATCH_MARGIN = 0.05

# 声纹嵌入维度（CAM++ 输出 192 维）
EMBEDDING_DIM = 192

# 注册时最少音频时长（秒），低于此值声纹不可靠
MIN_REGISTER_SEC = 3.0

# 单人参与提取的音频上限（秒）。截断避免长会议的无谓耗时，同时保证注册与匹配两侧嵌入可比
MAX_SEC_PER_SPEAKER = 180.0

# 采样率（云端 CAM++ 编码器要求 16kHz）
SAMPLE_RATE = 16000


def extract_embedding(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> Optional[np.ndarray]:
    """
    从音频信号提取声纹嵌入向量（通过 provider 抽象层）。

    根据配置选择本地 CAM++ / 云端 / MFCC 降级。
    参见 core/embedding_provider.py。

    Args:
        audio: float32 音频信号（值域 [-1, 1]），建议 ≥ 1.5 秒
        sample_rate: 采样率（默认 16000Hz）

    Returns:
        嵌入向量（L2 归一化），或 None（音频太短/提取失败）
    """
    from core.embedding_provider import get_embedding_provider
    provider = get_embedding_provider()
    return provider.extract(audio, sample_rate)


def extract_embedding_from_pcm(pcm_bytes: bytes, sample_rate: int = SAMPLE_RATE) -> Optional[np.ndarray]:
    """
    从 PCM 16bit 字节数据提取声纹嵌入（通过 provider 抽象层）。

    根据配置选择本地 CAM++ / 云端 / MFCC 降级。
    """
    from core.embedding_provider import get_embedding_provider
    provider = get_embedding_provider()
    return provider.extract_from_pcm(pcm_bytes, sample_rate)


# ============================================================
# 声纹注册表
# ============================================================

@dataclass
class VoiceprintRecord:
    """声纹注册记录"""
    speaker_uuid: str                          # 对应 speakers.json 的 speaker_id
    embedding: list[float]                     # 192 维嵌入向量（JSON 序列化用 list）
    registered_at: str = ""                    # 首次注册时间
    updated_at: str = ""                       # 最近更新时间
    sample_count: int = 1                      # 注册次数（历史兼容）
    total_sample_duration: float = 0.0         # 累积声纹样本总时长（秒），用于时长加权
    source_meeting_id: str = ""               # 注册来源会议 ID
    model_version: str = VOICEPRINT_MODEL_VERSION  # 提取 encoder 版本

    def to_dict(self) -> dict:
        return {
            "speaker_uuid": self.speaker_uuid,
            "embedding": self.embedding,
            "registered_at": self.registered_at,
            "updated_at": self.updated_at,
            "sample_count": self.sample_count,
            "total_sample_duration": self.total_sample_duration,
            "source_meeting_id": self.source_meeting_id,
            "model_version": self.model_version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VoiceprintRecord":
        return cls(
            speaker_uuid=data["speaker_uuid"],
            embedding=data["embedding"],
            registered_at=data.get("registered_at", ""),
            updated_at=data.get("updated_at", ""),
            sample_count=data.get("sample_count", 1),
            total_sample_duration=data.get("total_sample_duration", 0.0),
            source_meeting_id=data.get("source_meeting_id", ""),
            model_version=data.get("model_version", "legacy"),
        )


def load_registry() -> dict[str, VoiceprintRecord]:
    """
    加载声纹注册表。

    Returns:
        {speaker_uuid: VoiceprintRecord}
    """
    if not REGISTRY_FILE.exists():
        return {}
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: VoiceprintRecord.from_dict(v) for k, v in data.items()}
    except Exception as e:
        logger.error(f"[声纹] 加载注册表失败: {e}")
        return {}


def save_registry(registry: dict[str, VoiceprintRecord]) -> None:
    """保存声纹注册表"""
    try:
        data = {k: v.to_dict() for k, v in registry.items()}
        from core.fs_atomic import atomic_write_json
        atomic_write_json(REGISTRY_FILE, data)
        logger.info(f"[声纹] 注册表已保存: {len(registry)} 条")
    except Exception as e:
        logger.error(f"[声纹] 保存注册表失败: {e}")


def register_voiceprint(
    speaker_uuid: str,
    embedding: np.ndarray,
    source_meeting_id: str = "",
    accumulate: bool = True,
    sample_count: Optional[int] = None,
    duration_sec: float = 0.0,
) -> VoiceprintRecord:
    """
    注册/更新说话人声纹。

    Args:
        speaker_uuid: 说话人 UUID
        embedding: 192 维嵌入向量
        source_meeting_id: 注册来源会议
        accumulate: 已有声纹时是否按时长加权累积（多会议样本平均可
            抑制单场录音的信道偏置，提升跨会议判别力）；False 为整体覆盖
        sample_count: 显式指定样本数（跨会议重建时一次写入多场样本数）；
            None 表示在原有基础上 +1
        duration_sec: 本次注册的音频时长（秒），用于时长加权累积平均

    Returns:
        注册记录
    """
    registry = load_registry()
    now = datetime.now().isoformat()

    if speaker_uuid in registry:
        record = registry[speaker_uuid]
        # 若旧记录的 encoder 版本与当前不兼容，强制覆盖（不累积，避免混合不可比的向量）
        if not _is_compatible_version(record.model_version):
            logger.info(
                f"[声纹] 旧版本 {record.model_version} 声纹，整体覆盖为 {VOICEPRINT_MODEL_VERSION}"
            )
            record.embedding = embedding.tolist()
            record.model_version = VOICEPRINT_MODEL_VERSION
            record.sample_count = sample_count if sample_count is not None else 1
            record.total_sample_duration = duration_sec
        elif accumulate:
            old = np.array(record.embedding, dtype=np.float32)
            # 时长加权累积：按音频时长而非样本数加权，更准确反映信息量
            old_dur = record.total_sample_duration
            if old_dur > 0 and duration_sec > 0:
                # 按时长加权平均
                total_dur = old_dur + duration_sec
                merged = _l2((old * old_dur + embedding * duration_sec) / total_dur)
                record.total_sample_duration = total_dur
            else:
                # 降级到样本数加权（旧数据无时长信息）
                n = max(record.sample_count, 1)
                merged = _l2((old * n + embedding) / (n + 1))
                record.total_sample_duration = duration_sec if duration_sec > 0 else old_dur
            record.embedding = merged.tolist()
            record.sample_count = sample_count if sample_count is not None else record.sample_count + 1
        else:
            record.embedding = embedding.tolist()
            record.sample_count = sample_count if sample_count is not None else record.sample_count + 1
            record.total_sample_duration = duration_sec
            record.model_version = VOICEPRINT_MODEL_VERSION
        record.updated_at = now
        record.source_meeting_id = source_meeting_id
        mode = f"累积第 {record.sample_count} 个样本（{record.total_sample_duration:.1f}s）" if accumulate else "覆盖"
        logger.info(f"[声纹] 更新声纹: speaker={speaker_uuid[:8]}...（{mode}）")
    else:
        record = VoiceprintRecord(
            speaker_uuid=speaker_uuid,
            embedding=embedding.tolist(),
            registered_at=now,
            updated_at=now,
            sample_count=sample_count if sample_count is not None else 1,
            total_sample_duration=duration_sec,
            source_meeting_id=source_meeting_id,
            model_version=VOICEPRINT_MODEL_VERSION,
        )
        registry[speaker_uuid] = record
        logger.info(f"[声纹] 注册声纹: speaker={speaker_uuid[:8]}...（{duration_sec:.1f}s）")

    save_registry(registry)
    return record


def delete_voiceprint(speaker_uuid: str) -> bool:
    """删除说话人声纹"""
    registry = load_registry()
    if speaker_uuid in registry:
        del registry[speaker_uuid]
        save_registry(registry)
        logger.info(f"[声纹] 删除声纹: speaker={speaker_uuid[:8]}...")
        return True
    return False


def get_voiceprint_status(speaker_uuid: str) -> bool:
    """检查说话人是否已注册声纹（且版本匹配当前 encoder）"""
    registry = load_registry()
    rec = registry.get(speaker_uuid)
    if rec is None:
        return False
    return _is_compatible_version(rec.model_version)


# ============================================================
# 声纹匹配
# ============================================================

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    计算两个向量的余弦相似度。

    输入应已 L2 归一化；若未归一化则手动计算。
    """
    dot = float(np.dot(a, b))
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _l2(vec: np.ndarray) -> np.ndarray:
    """L2 归一化"""
    return vec / (float(np.linalg.norm(vec)) + 1e-9)


@dataclass
class MatchDetail:
    """匹配明细（含被拒绝时的真实分数，便于诊断与人工参考）"""
    best_uuid: Optional[str] = None
    best_sim: float = 0.0
    second_sim: float = 0.0
    accepted: bool = False

    @property
    def margin(self) -> float:
        return self.best_sim - self.second_sim


def match_voiceprint_detail(
    embedding: np.ndarray,
    threshold: Optional[float] = None,
) -> MatchDetail:
    """
    将声纹嵌入匹配到注册表，返回完整明细。

    仅比对 model_version 与当前 encoder 一致的注册记录；旧版本记录被忽略
    （避免跨 encoder 的不可比向量污染匹配结果）。

    Args:
        embedding: 待匹配的 192 维嵌入向量（L2 归一化）
        threshold: 相似度阈值；None 表示使用默认 MATCH_THRESHOLD

    Returns:
        MatchDetail（accepted 表示是否通过阈值与次优优势双重门槛）
    """
    registry = load_registry()
    if not registry:
        return MatchDetail()

    # 仅取版本兼容的记录（本地 cam++-v1 与云端 cam++-v1-cloud 互相兼容）
    valid = {
        u: r for u, r in registry.items()
        if _is_compatible_version(r.model_version)
    }
    if not valid:
        logger.info(
            f"[声纹] 注册表无匹配当前 encoder ({VOICEPRINT_MODEL_VERSION}) 的记录"
        )
        return MatchDetail()

    # 维度过滤：剔除维度不一致的记录（避免 np.stack 崩溃）
    _expected_dim = _get_expected_embedding_dimension()
    valid = {u: r for u, r in valid.items() if len(r.embedding) == _expected_dim}
    if not valid:
        logger.warning(f"[声纹] 维度过滤后注册表为空（期望 {_expected_dim} 维）")
        return MatchDetail()

    uuids = list(valid.keys())
    refs = np.stack([np.array(valid[u].embedding, dtype=np.float32) for u in uuids])
    # 归一化（防御性：注册时已 L2 归一化，但累积平均后可能略有漂移）
    refs = np.stack([_l2(v) for v in refs])
    probe = _l2(embedding)

    sims = refs @ probe
    order = np.argsort(-sims)
    thr = MATCH_THRESHOLD if threshold is None else threshold

    detail = MatchDetail(
        best_uuid=uuids[int(order[0])],
        best_sim=float(sims[order[0]]),
        second_sim=float(sims[order[1]]) if len(order) > 1 else 0.0,
    )
    detail.accepted = detail.best_sim >= thr and detail.margin >= MIN_MATCH_MARGIN

    if detail.accepted:
        logger.info(
            f"[声纹] 匹配成功: speaker={detail.best_uuid[:8]}..., "
            f"similarity={detail.best_sim:.3f}, 优势={detail.margin:.3f}"
        )
    else:
        logger.info(
            f"[声纹] 无匹配: best={detail.best_sim:.3f}/阈值{thr} "
            f"margin={detail.margin:.3f}/下限{MIN_MATCH_MARGIN}"
        )
    return detail


def match_voiceprint(
    embedding: np.ndarray,
    threshold: Optional[float] = None,
) -> Optional[tuple[str, float]]:
    """
    将声纹嵌入匹配到注册表中的说话人。

    Returns:
        (speaker_uuid, similarity) 最佳匹配，或 None（无匹配）
    """
    detail = match_voiceprint_detail(embedding, threshold)
    if detail.accepted and detail.best_uuid:
        return (detail.best_uuid, detail.best_sim)
    return None
