"""
core/voiceprint_identify.py — 声纹管线层：自动识别 + 绑定注册 + 跨会议重建

作者：王永亮
创建：2026-09-03
版本：2.0.0

职责：
  - 音频加载与说话人片段收集
  - 批量自动识别（per-meeting 中心化 + 匈牙利算法）
  - 绑定后自动注册（闭环）
  - 跨会议声纹重建

从 core/voiceprint.py 拆分而来。
"""

import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import numpy as np

# 以模块方式引用 voiceprint_registry：测试通过 monkeypatch 修改源模块属性，
# 必须通过模块引用（而非 from...import 名称绑定）才能生效。
from core import voiceprint_registry as _vr

logger = logging.getLogger(__name__)


# ============================================================
# 音频工具函数
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


# ============================================================
# 数据模型
# ============================================================

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


# ============================================================
# 批量自动识别
# ============================================================

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
    capped = _cap_segments(segments, _vr.MAX_SEC_PER_SPEAKER)
    chunks = [audio_data[int(begin * sr):int(end * sr)] for begin, end in capped]
    chunks = [c for c in chunks if len(c) > 0]
    if not chunks:
        return None, 0.0
    embedding = _vr.extract_embedding(np.concatenate(chunks), sr)
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
    registry = _vr.load_registry()
    valid_registry = {
        u: r for u, r in registry.items()
        if _vr._is_compatible_version(r.model_version)
    }
    if not valid_registry:
        logger.info("[声纹] 注册表为空或无当前 encoder 版本记录，跳过自动匹配")
        return []

    # 维度过滤：剔除与当前 encoder 输出维度不一致的记录（如 MFCC 降级 14 维 vs CAM++ 192 维）
    _expected_dim = _vr._get_expected_embedding_dimension()
    dim_filtered = {
        u: r for u, r in valid_registry.items()
        if len(r.embedding) == _expected_dim
    }
    if len(dim_filtered) < len(valid_registry):
        skipped = len(valid_registry) - len(dim_filtered)
        logger.warning(f"[声纹] 跳过 {skipped} 条维度不一致的注册记录（期望 {_expected_dim} 维）")
        valid_registry = dim_filtered
    if not valid_registry:
        logger.info("[声纹] 维度过滤后注册表为空，跳过自动匹配")
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

        if total_sec < _vr.MIN_REGISTER_SEC:
            insufficient_sids.add(sid)
            logger.info(f"[声纹] speaker_{sid}: 音频不足 ({total_sec:.1f}s < {_vr.MIN_REGISTER_SEC}s)")
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
        _vr._l2(np.array(valid_registry[u].embedding, dtype=np.float32))
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
            sim_matrix[i, j] = _vr.cosine_similarity(probe, ref_embeddings[j])

    # 匈牙利算法求最大总相似度的一对一分配
    # linear_sum_assignment 求最小值 → 取负相似度转为最小化问题
    from scipy.optimize import linear_sum_assignment
    row_ind, col_ind = linear_sum_assignment(-sim_matrix)

    # ── Step 4: 构建结果 ─────────────────────────────────
    thr = _vr.MATCH_THRESHOLD if threshold is None else threshold
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
            accepted = margin >= _vr.MIN_MATCH_MARGIN
        else:
            accepted = best_sim >= thr and margin >= _vr.MIN_MATCH_MARGIN

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
    return _vr._l2(np.mean(np.stack(embeddings), axis=0))


def extract_speaker_embedding(
    audio_path: str | Path,
    dialogue: list[dict],
    speaker_id: int,
    max_sec_per_speaker: float = 180.0,
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
    if not segs or total_sec < 3.0:
        return None, total_sec

    capped = _cap_segments(segs, max_sec_per_speaker)
    chunks = [audio_data[int(begin * sr):int(end * sr)] for begin, end in capped]
    chunks = [c for c in chunks if len(c) > 0]
    if not chunks:
        return None, total_sec

    embedding = _vr.extract_embedding(np.concatenate(chunks), sr)
    used_sec = sum(end - begin for begin, end in capped)
    return embedding, used_sec


def register_from_binding(
    audio_path: str | Path,
    dialogue: list[dict],
    mapping: dict,
    meeting_id: str = "",
    max_sec_per_speaker: float = 180.0,
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
            if acc < 3.0:
                results[uuid] = {"status": "insufficient_audio", "duration_sec": round(acc, 1)}
                logger.info(f"[声纹] 跳过注册: speaker={uuid[:8]}..., 音频不足 ({acc:.1f}s)")
            else:
                results[uuid] = {"status": "extract_failed"}
                logger.warning(f"[声纹] 注册失败: speaker={uuid[:8]}..., 嵌入提取失败")
            continue

        _vr.register_voiceprint(uuid, embedding, source_meeting_id=meeting_id, duration_sec=acc)
        results[uuid] = {"status": "registered", "duration_sec": round(acc, 1)}

    registered = sum(1 for r in results.values() if r["status"] == "registered")
    logger.info(f"[声纹] 绑定自动注册: {registered}/{len(normalized)} 位说话人写入注册表")
    return results
