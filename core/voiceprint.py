"""
core/voiceprint.py — 声纹提取与自动识别（云端 embedding + per-meeting 统筹分配）

职责：
  1. 从音频片段提取声纹嵌入向量（192 维，云端 CAM++ 服务）
  2. 声纹注册：将说话人的声纹向量持久化到注册表
  3. 声纹匹配：余弦相似度比对，自动将 speaker_id 映射为已注册说话人
  4. 批量自动识别：提取所有说话人声纹 → per-meeting 中心化 → 匈牙利算法一对一分配

依赖：
  - httpx（云端 embedding API 调用）
  - scipy.optimize.linear_sum_assignment（匈牙利算法，最优一对一分配）

数据文件：
  - data/voiceprint_registry.json：声纹注册表（speaker_uuid → embedding + 元数据）

设计原则：
  - 提取与匹配纯函数化，无全局状态
  - 注册表独立于 speakers.json，解耦声纹数据与人员档案
  - 匹配失败不阻塞管线，降级为手动绑定
  - 每条注册记录带 model_version，encoder 升级时旧记录自动失效
  - 匹配侧采用 per-meeting 统筹分配：中心化消除同会议信道公共分量，
    匈牙利算法保证一对一（不会把两个 ASR 说话人分给同一个注册人）
  - embedding 提取通过 core.embedding_provider 抽象层，支持云端/降级切换
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
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

# 声纹模型版本标识。云端服务返回 "cam++-v1-cloud"，与本地 "cam++-v1" 互相兼容。
VOICEPRINT_MODEL_VERSION = "cam++-v1-cloud"

# 兼容版本集合：本地 cam++-v1 与云端 cam++-v1-cloud 提取的 embedding 可互相匹配
# 参见 ADR-0009
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
    sample_count: int = 1                      # 注册时使用的音频样本数
    source_meeting_id: str = ""               # 注册来源会议 ID
    model_version: str = VOICEPRINT_MODEL_VERSION  # 提取 encoder 版本

    def to_dict(self) -> dict:
        return {
            "speaker_uuid": self.speaker_uuid,
            "embedding": self.embedding,
            "registered_at": self.registered_at,
            "updated_at": self.updated_at,
            "sample_count": self.sample_count,
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
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"[声纹] 注册表已保存: {len(registry)} 条")
    except Exception as e:
        logger.error(f"[声纹] 保存注册表失败: {e}")


def register_voiceprint(
    speaker_uuid: str,
    embedding: np.ndarray,
    source_meeting_id: str = "",
    accumulate: bool = True,
    sample_count: Optional[int] = None,
) -> VoiceprintRecord:
    """
    注册/更新说话人声纹。

    Args:
        speaker_uuid: 说话人 UUID
        embedding: 192 维嵌入向量
        source_meeting_id: 注册来源会议
        accumulate: 已有声纹时是否按样本数加权累积（多会议样本平均可
            抑制单场录音的信道偏置，提升跨会议判别力）；False 为整体覆盖
        sample_count: 显式指定样本数（跨会议重建时一次写入多场样本数）；
            None 表示在原有基础上 +1

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
        elif accumulate:
            old = np.array(record.embedding, dtype=np.float32)
            n = max(record.sample_count, 1)
            merged = _l2((old * n + embedding) / (n + 1))
            record.embedding = merged.tolist()
            record.sample_count = sample_count if sample_count is not None else record.sample_count + 1
        else:
            record.embedding = embedding.tolist()
            record.sample_count = sample_count if sample_count is not None else record.sample_count + 1
            record.model_version = VOICEPRINT_MODEL_VERSION
        record.updated_at = now
        record.source_meeting_id = source_meeting_id
        mode = f"累积第 {record.sample_count} 个样本" if accumulate else "覆盖"
        logger.info(f"[声纹] 更新声纹: speaker={speaker_uuid[:8]}...（{mode}）")
    else:
        record = VoiceprintRecord(
            speaker_uuid=speaker_uuid,
            embedding=embedding.tolist(),
            registered_at=now,
            updated_at=now,
            sample_count=sample_count if sample_count is not None else 1,
            source_meeting_id=source_meeting_id,
            model_version=VOICEPRINT_MODEL_VERSION,
        )
        registry[speaker_uuid] = record
        logger.info(f"[声纹] 注册声纹: speaker={speaker_uuid[:8]}...")

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


# ============================================================
# 批量自动识别
# ============================================================

def _load_audio(audio_path: Path) -> Optional[tuple[int, np.ndarray]]:
    """
    加载 WAV 音频为 float32 信号。

    Returns:
        (采样率, 音频数据)，失败返回 None
    """
    from scipy.io import wavfile

    try:
        sr, audio_data = wavfile.read(str(audio_path))
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32) / 32768.0
        return sr, audio_data
    except Exception as e:
        logger.error(f"[声纹] 加载音频失败: {e}")
        return None


def _collect_speaker_segments(dialogue: list[dict]) -> dict[int, list[tuple[float, float]]]:
    """
    从对话稿按 speaker_id 收集发言时间段（秒）。

    Returns:
        {speaker_id: [(begin_sec, end_sec), ...]}
    """
    speaker_segments: dict[int, list[tuple[float, float]]] = {}
    for item in dialogue:
        sid = item.get("speaker_id", 0)
        for sent in item.get("sentences", []):
            begin_ms = sent.get("begin_time", 0)
            end_ms = sent.get("end_time", 0)
            if end_ms > begin_ms:
                speaker_segments.setdefault(sid, []).append((begin_ms / 1000.0, end_ms / 1000.0))
    return speaker_segments


def _cap_segments(
    segments: list[tuple[float, float]],
    max_sec: float,
) -> list[tuple[float, float]]:
    """
    按总时长上限截断发言时间段（保序取前段）。

    注册与匹配两侧必须使用同一上限，保证嵌入可比。
    """
    capped: list[tuple[float, float]] = []
    acc = 0.0
    for begin, end in segments:
        if acc >= max_sec:
            break
        dur = end - begin
        if acc + dur > max_sec:
            dur = max_sec - acc
            end = begin + dur
        capped.append((begin, end))
        acc += dur
    return capped


@dataclass
class AutoMatchResult:
    """自动识别结果"""
    speaker_id: int                          # ASR 返回的 speaker_id
    matched_uuid: Optional[str] = None       # 匹配到的说话人 UUID
    matched_name: Optional[str] = None       # 匹配到的说话人姓名
    similarity: float = 0.0                  # 最佳候选相似度（未命中时也记录真实值）
    status: str = "unmatched"                # matched / unmatched / insufficient_audio
    best_candidate: Optional[str] = None     # 未命中时的最佳候选姓名（仅供人工参考）
    margin: float = 0.0                      # 最佳与次优的差距

    def to_dict(self) -> dict:
        return {
            "speaker_id": self.speaker_id,
            "matched_uuid": self.matched_uuid,
            "matched_name": self.matched_name,
            "similarity": round(self.similarity, 3),
            "status": self.status,
            "best_candidate": self.best_candidate,
            "margin": round(self.margin, 3),
        }


def _extract_single_speaker_embedding(
    audio_data: np.ndarray,
    sr: int,
    segments: list[tuple[float, float]],
) -> tuple[Optional[np.ndarray], float]:
    """
    为单个说话人拼接音频片段并提取嵌入。

    Returns:
        (embedding 或 None, 实际参与提取的音频总时长秒)
    """
    capped = _cap_segments(segments, MAX_SEC_PER_SPEAKER)
    chunks = [audio_data[int(begin * sr):int(end * sr)] for begin, end in capped]
    chunks = [c for c in chunks if len(c) > 0]
    if not chunks:
        return None, 0.0
    embedding = extract_embedding(np.concatenate(chunks), sr)
    used_sec = sum(end - begin for begin, end in capped)
    return embedding, used_sec


def auto_identify_speakers(
    audio_path: str | Path,
    dialogue: list[dict],
    threshold: Optional[float] = None,
) -> list[AutoMatchResult]:
    """
    对对话稿中每位说话人提取声纹，用 per-meeting 统筹分配匹配注册表。

    算法（v4 升级）：
      1. 提取所有说话人的声纹嵌入
      2. Per-meeting 中心化：减去所有说话人的均值，消除同会议录音的
         公共信道分量（同一麦克风/线路导致所有说话人 embedding 偏向
         同一方向，中心化后拉开人间差距）
      3. 匈牙利算法（scipy.optimize.linear_sum_assignment）做最优
         一对一分配，保证不会把两个 ASR 说话人分给同一个注册人
      4. 对分配结果做阈值 + margin 双重校验

    Args:
        audio_path: 归一化后的音频文件路径（16kHz 单声道 WAV）
        dialogue: 对话稿（含 speaker_id 和 sentences 时间戳）
        threshold: 匹配阈值；None 表示使用默认 MATCH_THRESHOLD

    Returns:
        每位说话人的匹配结果列表
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        logger.warning(f"[声纹] 音频文件不存在: {audio_path}")
        return []

    # 注册表为空（或无版本匹配的记录）时直接跳过
    registry = load_registry()
    valid_registry = {
        u: r for u, r in registry.items()
        if _is_compatible_version(r.model_version)
    }
    if not valid_registry:
        logger.info("[声纹] 注册表为空或无当前 encoder 版本记录，跳过自动匹配")
        return []

    # 加载音频
    loaded = _load_audio(audio_path)
    if loaded is None:
        return []
    sr, audio_data = loaded

    # 按 speaker_id 收集时间段
    speaker_segments = _collect_speaker_segments(dialogue)

    # ── Step 1: 提取所有说话人的嵌入 ──────────────────────
    speaker_embeddings: dict[int, np.ndarray] = {}
    insufficient_sids: set[int] = set()

    for sid in sorted(speaker_segments.keys()):
        segments = speaker_segments[sid]
        total_sec = sum(end - begin for begin, end in segments)

        if total_sec < MIN_REGISTER_SEC:
            insufficient_sids.add(sid)
            logger.info(f"[声纹] speaker_{sid}: 音频不足 ({total_sec:.1f}s < {MIN_REGISTER_SEC}s)")
            continue

        embedding, _ = _extract_single_speaker_embedding(audio_data, sr, segments)
        if embedding is None:
            insufficient_sids.add(sid)
            continue
        speaker_embeddings[sid] = embedding

    if not speaker_embeddings:
        logger.info("[声纹] 所有说话人音频均不足，跳过匹配")
        return []

    # ── Step 2: Per-meeting 中心化 ────────────────────────
    # 同一会议的所有说话人共享录音信道（同一麦克风/线路），embedding 中
    # 含有公共信道分量。减去均值后，公共分量被消除，个体差异被放大。
    # 仅当 ≥2 位有效说话人时执行（单人时均值 = 自身，中心化后为零向量无意义）
    sids = sorted(speaker_embeddings.keys())
    embeddings_array = np.stack([speaker_embeddings[sid] for sid in sids])

    if len(sids) >= 2:
        mean_embedding = np.mean(embeddings_array, axis=0)
        centered_embeddings = embeddings_array - mean_embedding
        logger.info(
            f"[声纹] 应用 per-meeting 中心化: {len(sids)} 位说话人, "
            f"均值向量 norm={np.linalg.norm(mean_embedding):.4f}"
        )
    else:
        centered_embeddings = embeddings_array

    # ── Step 3: 构建相似度矩阵 + 匈牙利算法分配 ──────────
    ref_uuids = list(valid_registry.keys())
    ref_embeddings = np.stack([
        _l2(np.array(valid_registry[u].embedding, dtype=np.float32))
        for u in ref_uuids
    ])

    n_speakers = len(sids)
    n_refs = len(ref_uuids)

    # 相似度矩阵: (n_speakers, n_refs)
    sim_matrix = np.zeros((n_speakers, n_refs), dtype=np.float32)
    for i in range(n_speakers):
        probe = centered_embeddings[i]
        probe_norm = np.linalg.norm(probe)
        if probe_norm < 1e-9:
            continue  # 零向量跳过（中心化后可能出现）
        for j in range(n_refs):
            sim_matrix[i, j] = cosine_similarity(probe, ref_embeddings[j])

    # 匈牙利算法求最大总相似度的一对一分配
    # linear_sum_assignment 求最小值 → 取负相似度转为最小化问题
    from scipy.optimize import linear_sum_assignment
    row_ind, col_ind = linear_sum_assignment(-sim_matrix)

    # ── Step 4: 构建结果 ─────────────────────────────────
    thr = MATCH_THRESHOLD if threshold is None else threshold
    results: list[AutoMatchResult] = []

    # 被匈牙利算法分配到某个注册人的 ASR speaker 集合
    assigned: dict[int, int] = {}  # row_idx → col_idx
    for r, c in zip(row_ind, col_ind):
        if r < n_speakers and c < n_refs:
            assigned[r] = c

    from core.speakers import get_speaker_by_id

    for i, sid in enumerate(sids):
        if sid in insufficient_sids:
            results.append(AutoMatchResult(speaker_id=sid, status="insufficient_audio"))
            continue

        if i not in assigned:
            results.append(AutoMatchResult(speaker_id=sid, status="unmatched"))
            continue

        j = assigned[i]
        best_uuid = ref_uuids[j]
        best_sim = float(sim_matrix[i, j])

        # 计算 margin：中心化空间中该 speaker 与最佳 vs 次优注册人的差距
        sims_for_this = sim_matrix[i]
        sorted_sims = np.sort(sims_for_this)[::-1]
        second_sim = float(sorted_sims[1]) if len(sorted_sims) > 1 else 0.0
        margin = best_sim - second_sim

        best_speaker = get_speaker_by_id(best_uuid)
        best_name = best_speaker.name if best_speaker else None

        # 接受准则：
        # - 中心化空间（≥2 说话人 & ≥2 注册人）：绝对相似度不可比（受会议信道
        #   影响），仅以 margin 为接受门槛。匈牙利算法已保证最优一对一分配。
        # - 非中心化（单人或单注册人）：退化为绝对阈值
        centered_mode = len(sids) >= 2 and len(ref_uuids) >= 2
        if centered_mode:
            accepted = margin >= MIN_MATCH_MARGIN
        else:
            accepted = best_sim >= thr and margin >= MIN_MATCH_MARGIN

        if accepted:
            results.append(AutoMatchResult(
                speaker_id=sid,
                matched_uuid=best_uuid,
                matched_name=best_name,
                similarity=best_sim,
                status="matched",
                best_candidate=best_name,
                margin=margin,
            ))
        else:
            results.append(AutoMatchResult(
                speaker_id=sid,
                similarity=best_sim,
                status="unmatched",
                best_candidate=best_name,
                margin=margin,
            ))

    matched_count = sum(1 for r in results if r.status == "matched")
    logger.info(
        f"[声纹] 自动识别（per-meeting 统筹分配）: "
        f"{len(results)} 位说话人, {matched_count} 位匹配成功"
    )
    return results


def build_auto_mapping(results: list[AutoMatchResult]) -> dict[int, str]:
    """
    从自动识别结果构建 speaker_id → speaker_uuid 映射。

    仅包含匹配成功的结果。

    Returns:
        {speaker_id: speaker_uuid}
    """
    mapping = {}
    for r in results:
        if r.status == "matched" and r.matched_uuid:
            mapping[r.speaker_id] = r.matched_uuid
    return mapping


# ============================================================
# 绑定后自动注册（闭环）
# ============================================================

def merge_embeddings(embeddings: list[np.ndarray]) -> np.ndarray:
    """
    均值融合多个嵌入并 L2 归一化。

    用于跨会议声纹重建：将同一说话人在多场会议中的嵌入平均，
    抑制单场录音的信道偏置。
    """
    return _l2(np.mean(np.stack(embeddings), axis=0))


def extract_speaker_embedding(
    audio_path: str | Path,
    dialogue: list[dict],
    speaker_id: int,
    max_sec_per_speaker: float = MAX_SEC_PER_SPEAKER,
) -> tuple[Optional[np.ndarray], float]:
    """
    从单场会议音频中提取指定 speaker_id 的声纹嵌入。

    按对话稿中该说话人的发言时间段截取音频片段（总时长上限
    max_sec_per_speaker，与匹配侧共用 _cap_segments 保证嵌入可比），
    拼接后提取嵌入。供绑定注册与跨会议重建复用。

    Args:
        audio_path: 归一化后的音频文件路径（16kHz 单声道 WAV）
        dialogue: 该场会议的对话稿（含 speaker_id 和 sentences 时间戳）
        speaker_id: ASR 返回的说话人编号
        max_sec_per_speaker: 单人参与提取的音频上限（秒）

    Returns:
        (嵌入向量或 None, 实际参与提取的音频总时长秒)
    """
    loaded = _load_audio(Path(audio_path))
    if loaded is None:
        return None, 0.0
    sr, audio_data = loaded

    segs = _collect_speaker_segments(dialogue or []).get(speaker_id, [])
    total_sec = sum(end - begin for begin, end in segs)
    if not segs or total_sec < MIN_REGISTER_SEC:
        return None, total_sec

    capped = _cap_segments(segs, max_sec_per_speaker)
    chunks = [audio_data[int(begin * sr):int(end * sr)] for begin, end in capped]
    chunks = [c for c in chunks if len(c) > 0]
    if not chunks:
        return None, total_sec

    embedding = extract_embedding(np.concatenate(chunks), sr)
    used_sec = sum(end - begin for begin, end in capped)
    return embedding, used_sec


def register_from_binding(
    audio_path: str | Path,
    dialogue: list[dict],
    mapping: dict,
    meeting_id: str = "",
    max_sec_per_speaker: float = MAX_SEC_PER_SPEAKER,
) -> dict[str, dict]:
    """
    按已确认的绑定关系为每位说话人注册/更新声纹（自动注册闭环）。

    用户确认 speaker_id → speaker_uuid 绑定后调用：从归一化音频中
    按各说话人的发言时间段提取声纹并写入注册表，使后续会议可以
    通过声纹自动匹配身份，而不依赖跨会议复用的历史映射。

    Args:
        audio_path: 归一化后的音频文件路径（16kHz 单声道 WAV）
        dialogue: 对话稿（含 speaker_id 和 sentences 时间戳）
        mapping: {speaker_id: speaker_uuid}，key 允许 str/int
        meeting_id: 注册来源会议 ID
        max_sec_per_speaker: 单人参与提取的音频上限（秒）

    Returns:
        {speaker_uuid: {"status": registered/insufficient_audio/extract_failed, ...}}
    """
    results: dict[str, dict] = {}

    # 归一化 mapping 的 key 为 int
    normalized: dict[int, str] = {}
    for k, v in (mapping or {}).items():
        try:
            normalized[int(k)] = v
        except (TypeError, ValueError):
            continue
    if not normalized:
        return results

    if not audio_path:
        return {uuid: {"status": "audio_unavailable"} for uuid in normalized.values()}

    loaded = _load_audio(Path(audio_path))
    if loaded is None:
        return {uuid: {"status": "audio_unavailable"} for uuid in normalized.values()}

    for sid, uuid in normalized.items():
        embedding, acc = extract_speaker_embedding(
            audio_path, dialogue or [], sid, max_sec_per_speaker
        )
        if embedding is None:
            if acc < MIN_REGISTER_SEC:
                results[uuid] = {"status": "insufficient_audio", "duration_sec": round(acc, 1)}
                logger.info(f"[声纹] 跳过注册: speaker={uuid[:8]}..., 音频不足 ({acc:.1f}s)")
            else:
                results[uuid] = {"status": "extract_failed"}
                logger.warning(f"[声纹] 注册失败: speaker={uuid[:8]}..., 嵌入提取失败")
            continue

        register_voiceprint(uuid, embedding, source_meeting_id=meeting_id)
        results[uuid] = {"status": "registered", "duration_sec": round(acc, 1)}

    registered = sum(1 for r in results.values() if r["status"] == "registered")
    logger.info(f"[声纹] 绑定自动注册: {registered}/{len(normalized)} 位说话人写入注册表")
    return results
