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

# 单人保留的注册样本上限（chunk 数，FIFO 淘汰）。
# 每样本为一个 192 维向量（JSON ≈ 2KB），36 条 ≈ 70KB/人，磁盘与 load 成本可接受。
MAX_SAMPLES_PER_SPEAKER = 36

# 单场会议保留的注册样本上限（180s cap / 20s chunk = 9）
MAX_SAMPLES_PER_MEETING = 9

# ── 个人阈值（per-speaker calibrated threshold）──────────────
# 用本人注册样本的 leave-one-out 自比对分布标定：
#   thr = mean(intra_sim) - k * std(intra_sim)，再 clamp 到 [FLOOR, CAP]。
# 样本来自不同 chunk/会议，分布天然包含跨信道变异，比全局 0.50 更贴本人。
# 样本不足 PERSONAL_THR_MIN_SAMPLES 时不标定，识别侧回退全局/中心化旧逻辑。
PERSONAL_THR_MIN_SAMPLES = 3
PERSONAL_THR_STD_K = 1.0
PERSONAL_THR_FLOOR = 0.35   # 跨信道（远场/设备差异）同人相似度的经验下界
PERSONAL_THR_CAP = 0.62     # 上限：防止分布过紧导致阈值虚高误拒真人

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

def _normalize_samples(raw) -> list[dict]:
    """
    归一化样本列表。

    样本项紧凑结构 / Compact item: {"e": [float...], "d": float, "m": str}
      e — 嵌入向量 / embedding
      d — 有效音频时长秒 / valid duration seconds（0 表示未知，加权时退化为等权）
      m — 来源会议 ID（同会议重复注册时用于去重刷新） / source meeting id
    """
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict) or not item.get("e"):
            continue
        out.append({
            "e": list(item["e"]),
            "d": float(item.get("d", 0.0) or 0.0),
            "m": str(item.get("m", "") or ""),
        })
    return out


@dataclass
class VoiceprintRecord:
    """声纹注册记录"""
    speaker_uuid: str                          # 对应 speakers.json 的 speaker_id
    embedding: list[float]                     # 样本时长加权质心（匹配热路径用，与 samples 同源）
    registered_at: str = ""                    # 首次注册时间
    updated_at: str = ""                       # 最近更新时间
    sample_count: int = 1                      # = len(samples)，保留字段名兼容旧读侧
    total_sample_duration: float = 0.0         # 全部样本有效时长之和（秒）
    source_meeting_id: str = ""               # 最近一次注册来源会议 ID
    model_version: str = VOICEPRINT_MODEL_VERSION  # 提取 encoder 版本
    # v2.1：保留每次注册的原始样本，用于个人阈值标定；旧记录迁移为单样本
    samples: list[dict] = None                # type: ignore[assignment]
    # 个人阈值缓存（样本足够时由 compute_personal_threshold 写入）；None = 未标定
    personal_threshold: Optional[float] = None

    def __post_init__(self):
        if self.samples is None:
            # 旧记录/直接构造的兼容迁移：质心自身作为唯一样本
            self.samples = [{
                "e": list(self.embedding),
                "d": float(self.total_sample_duration or 0.0),
                "m": self.source_meeting_id or "",
            }]
        else:
            self.samples = _normalize_samples(self.samples)
        self.sample_count = len(self.samples)

    def to_dict(self) -> dict:
        return {
            "speaker_uuid": self.speaker_uuid,
            "embedding": self.embedding,
            "registered_at": self.registered_at,
            "updated_at": self.updated_at,
            "sample_count": len(self.samples),
            "total_sample_duration": self.total_sample_duration,
            "source_meeting_id": self.source_meeting_id,
            "model_version": self.model_version,
            "samples": self.samples,
            "personal_threshold": self.personal_threshold,
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
            samples=data.get("samples"),
            personal_threshold=data.get("personal_threshold"),
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


def _weighted_centroid(samples: list[dict]) -> list[float]:
    """样本时长加权质心（L2 归一化）；全部时长缺失（0）时退化为等权平均。"""
    embs = np.stack([np.array(s["e"], dtype=np.float32) for s in samples])
    weights = np.array([s["d"] if s["d"] > 0 else 1.0 for s in samples], dtype=np.float32)
    return _l2((embs * weights[:, None]).sum(axis=0) / float(weights.sum())).tolist()


def compute_personal_threshold(
    samples: list[dict],
    k: float = PERSONAL_THR_STD_K,
) -> Optional[float]:
    """
    基于本人注册样本的 leave-one-out 自比对分布标定个人阈值。

    对每个样本，计算它与「其余样本时长加权质心」的余弦相似度，
    得到本人分数分布；阈值取 mean - k·std 并 clamp 到 [FLOOR, CAP]。

    样本跨 chunk / 跨会议时，分布覆盖信道与状态变异，阈值比全局 0.50
    更贴合该说话人本身的可辨识程度。

    Returns:
        阈值 float；样本不足 PERSONAL_THR_MIN_SAMPLES 返回 None。
    """
    if len(samples) < PERSONAL_THR_MIN_SAMPLES:
        return None
    embs = [_l2(np.array(s["e"], dtype=np.float32)) for s in samples]
    weights = [s["d"] if s["d"] > 0 else 1.0 for s in samples]
    scores: list[float] = []
    for i in range(len(embs)):
        others_idx = [j for j in range(len(embs)) if j != i]
        w = np.array([weights[j] for j in others_idx], dtype=np.float32)
        cen = _l2(
            (np.stack([embs[j] for j in others_idx]) * w[:, None]).sum(axis=0)
            / float(w.sum())
        )
        scores.append(float(np.dot(embs[i], cen)))
    thr = float(np.mean(scores)) - k * float(np.std(scores))
    return float(min(PERSONAL_THR_CAP, max(PERSONAL_THR_FLOOR, thr)))


def _cap_samples_inplace(samples: list[dict]) -> list[dict]:
    """单会议上限（保最新）+ 全局上限（FIFO）裁剪。"""
    # 单会议上限：同会议超出时保留最新的 MAX_SAMPLES_PER_MEETING 条
    by_meeting: dict[str, list[int]] = {}
    for idx, s in enumerate(samples):
        if s["m"]:
            by_meeting.setdefault(s["m"], []).append(idx)
    drop: set[int] = set()
    for idxs in by_meeting.values():
        if len(idxs) > MAX_SAMPLES_PER_MEETING:
            drop.update(idxs[:len(idxs) - MAX_SAMPLES_PER_MEETING])
    if drop:
        samples = [s for idx, s in enumerate(samples) if idx not in drop]

    # 全局 FIFO
    while len(samples) > MAX_SAMPLES_PER_SPEAKER:
        samples.pop(0)
    return samples


def _append_samples_capped(record: VoiceprintRecord, new_items: list[dict]) -> None:
    """新样本并入记录：同会议去重刷新 → append → 单会议/全局上限裁剪 → 重算质心与阈值。"""
    meeting_ids = {item["m"] for item in new_items if item["m"]}
    if meeting_ids:
        record.samples = [s for s in record.samples if s["m"] not in meeting_ids]
    record.samples.extend(new_items)
    record.samples = _cap_samples_inplace(record.samples)

    record.embedding = _weighted_centroid(record.samples)
    record.total_sample_duration = float(sum(s["d"] for s in record.samples))
    record.sample_count = len(record.samples)
    record.personal_threshold = compute_personal_threshold(record.samples)


def register_voiceprint_samples(
    speaker_uuid: str,
    samples: list[tuple],
    meeting_id: str = "",
    accumulate: bool = True,
) -> VoiceprintRecord:
    """
    批量注册/更新说话人声纹（一场会议可贡献多个 chunk 样本）。

    Args:
        speaker_uuid: 说话人 UUID
        samples: 样本列表，每项为
            (embedding: np.ndarray, duration_sec: float) 或
            (embedding, duration_sec, source_meeting_id: str)
            第三元组优先；二元组统一取 meeting_id 参数。
        meeting_id: 默认来源会议 ID
        accumulate: True 并入历史样本（同会议样本刷新去重）；
            False 整体替换（跨会议重建语义，旧样本全部废弃）

    Returns:
        注册记录
    """
    items: list[dict] = []
    for tup in samples or []:
        emb = tup[0]
        dur = float(tup[1]) if len(tup) > 1 else 0.0
        mid = tup[2] if len(tup) > 2 and tup[2] else meeting_id
        if emb is None:
            continue
        items.append({"e": _l2(np.asarray(emb, dtype=np.float32)).tolist(), "d": dur, "m": mid})
    if not items:
        raise ValueError("register_voiceprint_samples: 无有效样本")

    # 统一在入口做单会议/全局上限裁剪（新注册、累积、覆盖三条路径都受约束）
    items = _cap_samples_inplace(items)

    registry = load_registry()
    now = datetime.now().isoformat()
    latest_meeting = next((it["m"] for it in reversed(items) if it["m"]), meeting_id)

    def _replace_all(record: VoiceprintRecord, new_items: list[dict]) -> None:
        capped_items = _cap_samples_inplace(list(new_items))
        record.samples = capped_items
        record.model_version = VOICEPRINT_MODEL_VERSION
        record.embedding = _weighted_centroid(capped_items)
        record.total_sample_duration = float(sum(s["d"] for s in capped_items))
        record.sample_count = len(capped_items)
        record.personal_threshold = compute_personal_threshold(capped_items)

    if speaker_uuid in registry:
        record = registry[speaker_uuid]
        if not _is_compatible_version(record.model_version):
            logger.info(
                f"[声纹] 旧版本 {record.model_version} 声纹，整体覆盖为 {VOICEPRINT_MODEL_VERSION}"
            )
            _replace_all(record, items)
        elif accumulate:
            _append_samples_capped(record, items)
        else:
            _replace_all(record, items)
        record.updated_at = now
        record.source_meeting_id = latest_meeting
        logger.info(
            f"[声纹] 更新声纹: speaker={speaker_uuid[:8]}... "
            f"（{record.sample_count} 样本 / {record.total_sample_duration:.1f}s"
            f"{' / 个人阈值=' + format(record.personal_threshold, '.3f') if record.personal_threshold else ''}）"
        )
    else:
        record = VoiceprintRecord(
            speaker_uuid=speaker_uuid,
            embedding=_weighted_centroid(items),
            registered_at=now,
            updated_at=now,
            total_sample_duration=float(sum(s["d"] for s in items)),
            source_meeting_id=latest_meeting,
            model_version=VOICEPRINT_MODEL_VERSION,
            samples=items,
            personal_threshold=compute_personal_threshold(items),
        )
        registry[speaker_uuid] = record
        logger.info(
            f"[声纹] 注册声纹: speaker={speaker_uuid[:8]}... "
            f"（{len(items)} 样本 / {record.total_sample_duration:.1f}s）"
        )

    save_registry(registry)
    return record


def register_voiceprint(
    speaker_uuid: str,
    embedding: np.ndarray,
    source_meeting_id: str = "",
    accumulate: bool = True,
    duration_sec: float = 0.0,
) -> VoiceprintRecord:
    """
    注册/更新说话人声纹（单样本便捷封装，语义见 register_voiceprint_samples）。

    历史行为保持 / Legacy behavior preserved:
      accumulate=True  累积（同会议单样本刷新，跨会议追加）
      accumulate=False 整体覆盖
    """
    return register_voiceprint_samples(
        speaker_uuid,
        [(embedding, duration_sec, source_meeting_id)],
        meeting_id=source_meeting_id,
        accumulate=accumulate,
    )


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

    detail = MatchDetail(
        best_uuid=uuids[int(order[0])],
        best_sim=float(sims[order[0]]),
        second_sim=float(sims[order[1]]) if len(order) > 1 else 0.0,
    )
    # 阈值优先级：显式入参 > 最佳候选人的个人阈值 > 全局 MATCH_THRESHOLD
    best_record = valid[detail.best_uuid]
    if threshold is not None:
        thr = threshold
    elif best_record.personal_threshold is not None:
        thr = best_record.personal_threshold
    else:
        thr = MATCH_THRESHOLD
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
