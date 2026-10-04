"""
core/voiceprint_identify.py — 声纹管线层：自动识别 + 绑定注册 + 跨会议重建 / Voiceprint pipeline layer: auto-identification + binding registration + cross-meeting rebuild

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-03
版本 / Version: 2.0.0

职责 / Responsibilities:
  - 音频加载与说话人片段收集 / Audio loading and speaker segment collection
  - 批量自动识别（per-meeting 中心化 + 匈牙利算法） / Batch auto-identification (per-meeting centering + Hungarian algorithm)
  - 绑定后自动注册（闭环） / Auto-registration after binding (closed loop)
  - 跨会议声纹重建 / Cross-meeting voiceprint rebuild

从 core/voiceprint.py 拆分而来 / Split from core/voiceprint.py.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
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
    from core.audio import read_wav_float32

    try:
        sr, audio_data = read_wav_float32(audio_path)
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
# v2.1：chunk 样本群（group embedding）
# ============================================================
# 每位说话人不再只拼一个 180s 大向量，而是切成多个 ~20s 有效语音的 chunk
# 各自提嵌入：①识别时用「点群 vs 注册人」的中位相似度+多数表决，个别
# 坏块（噪声/重叠/ASR 串人）不再带偏整体；②注册时一场即可产出多个样本，
# 个人阈值当场可标定。
CHUNK_SEC = 20.0
CHUNK_MIN_TAIL_SEC = 5.0     # 尾块不足此时长则并入上一块

# 点群中相似度 ≥ 候选人个人阈值的 chunk 占比下限
GROUP_MAJORITY_RATIO = 0.6

# 碎片化检测：组内 chunk 对组质心的相似度，25 分位低于此值说明
# 该 ASR speaker_id 内混入了两种声音（ASR 把两人切成一个 id）
FRAGMENTED_FLOOR = 0.35


def _v2_enabled() -> bool:
    """v2.1 群嵌入+个人阈值链路开关（feature_flags.voiceprint_v2，默认开，逃生通道）。"""
    try:
        from app.settings_store import get_feature_flags
        return bool(get_feature_flags().get("voiceprint_v2", True))
    except Exception:
        return True


def _chunk_segments(
    segments: list[tuple[float, float]],
    cap_sec: float = _vr.MAX_SEC_PER_SPEAKER,
    chunk_sec: float = CHUNK_SEC,
    min_tail_sec: float = CHUNK_MIN_TAIL_SEC,
) -> list[list[tuple[float, float]]]:
    """
    把 cap 后的发言段按有效时长攒成多个 chunk（跨句拼接，保序）。

    - 每攒够 chunk_sec 成一块；
    - 尾块 ≥ min_tail_sec 独立成块，否则并入上一块；
    - 总时长不足一块（< chunk_sec 但 ≥ 注册下限）时整体成一块，
      保证短音频行为与旧「整段一个向量」一致。

    Returns:
        [chunk_1 的片段列表, chunk_2 的片段列表, ...]
    """
    capped = _cap_segments(segments, cap_sec)
    chunks: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    acc = 0.0
    for seg in capped:
        current.append(seg)
        acc += seg[1] - seg[0]
        if acc >= chunk_sec:
            chunks.append(current)
            current = []
            acc = 0.0
    if current:
        if chunks and acc < min_tail_sec:
            chunks[-1].extend(current)
        else:
            chunks.append(current)
    return chunks


def _extract_embedding_group(
    audio_data: np.ndarray,
    sr: int,
    segments: list[tuple[float, float]],
    use_v2: bool,
    cap_sec: float = _vr.MAX_SEC_PER_SPEAKER,
) -> list[tuple[np.ndarray, float]]:
    """
    为一位说话人提取嵌入样本群。

    v2：按 _chunk_segments 切多块；v1（回退）：整段一块（旧行为）。

    Returns:
        [(L2 归一化嵌入, 块有效时长秒), ...]，提取失败的块被跳过
    """
    chunk_lists = (
        _chunk_segments(segments, cap_sec=cap_sec)
        if use_v2
        else [_cap_segments(segments, cap_sec)]
    )
    out: list[tuple[np.ndarray, float]] = []
    for segs in chunk_lists:
        chunks = [audio_data[int(begin * sr):int(end * sr)] for begin, end in segs]
        chunks = [c for c in chunks if len(c) > 0]
        if not chunks:
            continue
        embedding = _vr.extract_embedding(np.concatenate(chunks), sr)
        if embedding is not None:
            out.append((embedding, sum(end - begin for begin, end in segs)))
    return out


# ============================================================
# 数据模型
# ============================================================

@dataclass
class AutoMatchResult:
    """自动识别结果"""
    speaker_id: int                          # ASR 返回的 speaker_id
    matched_uuid: Optional[str] = None       # 匹配到的说话人 UUID
    matched_name: Optional[str] = None       # 匹配到的说话人姓名
    similarity: float = 0.0                  # 最佳候选的群中位相似度（未命中也记录真实值）
    status: str = "unmatched"                # matched / unmatched / insufficient_audio
    best_candidate: Optional[str] = None     # 未命中时的最佳候选姓名（仅供人工参考）
    margin: float = 0.0                      # 最佳与次优的差距
    group_size: int = 1                      # 该说话人参与比对的 chunk 数
    majority: float = 1.0                    # 群中过候选人个人阈值的 chunk 占比
    fragmented: bool = False                 # ASR speaker 内声音疑似不纯（混入两人）
    gate: str = "global"                     # 采用的门槛：personal / global / margin_only

    def to_dict(self) -> dict:
        return {
            "speaker_id": self.speaker_id,
            "matched_uuid": self.matched_uuid,
            "matched_name": self.matched_name,
            "similarity": round(self.similarity, 3),
            "status": self.status,
            "best_candidate": self.best_candidate,
            "margin": round(self.margin, 3),
            "group_size": self.group_size,
            "majority": round(self.majority, 2),
            "fragmented": self.fragmented,
            "gate": self.gate,
        }


# ============================================================
# 批量自动识别
# ============================================================

def _greedy_assignment(cost_matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """贪心一对一分配（替代 scipy.optimize.linear_sum_assignment）。

    对小型矩阵（说话人匹配场景，通常 < 20x20）效果与匈牙利算法一致。
    每次选取全局最优的 (行, 列) 对，然后排除该行和该列。

    Args:
        cost_matrix: 成本矩阵（越小越优），shape (m, n)

    Returns:
        (row_indices, col_indices) 分配结果
    """
    m, n = cost_matrix.shape
    used_rows: set[int] = set()
    used_cols: set[int] = set()
    rows: list[int] = []
    cols: list[int] = []

    for _ in range(min(m, n)):
        # 在可用行列中找最小值
        best_val = np.inf
        best_r = best_c = -1
        for r in range(m):
            if r in used_rows:
                continue
            for c in range(n):
                if c in used_cols:
                    continue
                if cost_matrix[r, c] < best_val:
                    best_val = cost_matrix[r, c]
                    best_r, best_c = r, c
        if best_r < 0:
            break
        rows.append(best_r)
        cols.append(best_c)
        used_rows.add(best_r)
        used_cols.add(best_c)

    return np.array(rows, dtype=int), np.array(cols, dtype=int)


def auto_identify_speakers(
    audio_path: str | Path,
    dialogue: list[dict],
    threshold: Optional[float] = None,
    exclude_uuids: Optional[set[str]] = None,
    bound_sids: Optional[set[int]] = None,
) -> list[AutoMatchResult]:
    """
    对对话稿中每位说话人提取声纹，用 per-meeting 统筹分配匹配注册表。

    算法（v2.1 升级）：
      1. 每位说话人切多个 ~20s chunk，各提嵌入，得到「点群」而非单点
      2. 原始空间：点群对每位注册人取中位相似度（抗坏块），并统计
         过该注册人个人阈值的 chunk 占比（多数表决）
      3. 分配空间：≥2 人时用说话人级 per-meeting 中心化 + 贪心一对一
         分配（消除同会议公共信道，保证一注册人至多分给一个 ASR 人）
      4. 接受门槛（按候选人择一）：
         a. 注册人有个人阈值：群中位 ≥ 个人阈值 且 多数占比 ≥ 0.6
         b. 中心化模式且无个人阈值：仅 margin（旧行为）
         c. 其余：全局阈值 + margin（旧行为）
      5. 锚点排除：exclude_uuids（本场已确认绑定/被其他证据锁定的注册人）
         不参与候选，杜绝同一注册人被建议给本场第二个说话人
      6. 碎片化检测：组内点明显分裂时标记 fragmented（疑似 ASR 混人）

    feature_flags.voiceprint_v2=false 时回退 v1 单向量+全局口径。

    Args:
        audio_path: 归一化后的音频文件路径（16kHz 单声道 WAV）
        dialogue: 对话稿（含 speaker_id 和 sentences 时间戳）
        threshold: 全局匹配阈值；None 表示使用默认 MATCH_THRESHOLD
        exclude_uuids: 本场已锁定的注册人 UUID 集合（锚点，不参与建议）
        bound_sids: 本场已确认绑定的 ASR speaker_id 集合（不重新识别，
            避免给已确认的人再产出互相矛盾的建议）

    Returns:
        每位说话人的匹配结果列表
    """
    use_v2 = _v2_enabled()
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

    # 锚点排除：本场已确认绑定（或已被其他证据锁定）的注册人不参与候选。
    # 一场会议一个注册人只能对应一个 ASR speaker，否则会出现自相矛盾的建议。
    if exclude_uuids:
        before = len(valid_registry)
        valid_registry = {u: r for u, r in valid_registry.items() if u not in exclude_uuids}
        locked = before - len(valid_registry)
        if locked:
            logger.info(f"[声纹] 锚点排除 {locked} 位本场已锁定的注册人")
        if not valid_registry:
            logger.info("[声纹] 剩余候选为空，跳过自动匹配")
            return []

    # 加载音频
    loaded = _load_audio(audio_path)
    if loaded is None:
        return []
    sr, audio_data = loaded

    # 按 speaker_id 收集时间段
    speaker_segments = _collect_speaker_segments(dialogue)

    # 已确认绑定的 ASR 说话人不再参与识别（用户手工确认优先，不产出反向建议）
    if bound_sids:
        before = len(speaker_segments)
        speaker_segments = {sid: segs for sid, segs in speaker_segments.items() if sid not in bound_sids}
        skipped_sids = before - len(speaker_segments)
        if skipped_sids:
            logger.info(f"[声纹] 跳过 {skipped_sids} 位本场已绑定的 ASR 说话人")
        if not speaker_segments:
            logger.info("[声纹] 说话人均已绑定，无需自动识别")
            return []

    # ── Step 1: 提取所有说话人的 chunk 嵌入群 ─────────────
    groups: dict[int, list[tuple[np.ndarray, float]]] = {}
    insufficient_sids: set[int] = set()

    for sid in sorted(speaker_segments.keys()):
        segments = speaker_segments[sid]
        total_sec = sum(end - begin for begin, end in segments)

        if total_sec < _vr.MIN_REGISTER_SEC:
            insufficient_sids.add(sid)
            logger.info(f"[声纹] speaker_{sid}: 音频不足 ({total_sec:.1f}s < {_vr.MIN_REGISTER_SEC}s)")
            continue

        group = _extract_embedding_group(audio_data, sr, segments, use_v2)
        if not group:
            insufficient_sids.add(sid)
            continue
        groups[sid] = group

    if not groups:
        logger.info("[声纹] 所有说话人音频均不足，跳过匹配")
        return []

    # ── Step 2: 原始空间点群相似度（中位数 + 多数表决依据） ──
    sids = sorted(groups.keys())
    ref_uuids = list(valid_registry.keys())
    ref_embeddings = np.stack([
        _vr._l2(np.array(valid_registry[u].embedding, dtype=np.float32))
        for u in ref_uuids
    ])
    ref_thresholds = [valid_registry[u].personal_threshold for u in ref_uuids]

    n_speakers = len(sids)
    n_refs = len(ref_uuids)

    # raw_chunk_sims[i]: shape (K_i, n_refs)，该 speaker 每个 chunk 对各注册人的原始余弦
    raw_chunk_sims: list[np.ndarray] = []
    group_vecs: list[np.ndarray] = []  # 每组 L2 后的 chunk 向量堆叠（中心化/碎片化复用）
    for sid in sids:
        vecs = np.stack([_vr._l2(emb) for emb, _ in groups[sid]])
        group_vecs.append(vecs)
        raw_chunk_sims.append(vecs @ ref_embeddings.T)

    # 群中位相似度矩阵 (n_speakers, n_refs)：抗个别坏块，作为绝对判定与 margin 的依据
    raw_med = np.zeros((n_speakers, n_refs), dtype=np.float32)
    for i in range(n_speakers):
        raw_med[i] = np.median(raw_chunk_sims[i], axis=0)

    # ── Step 3: 分配空间（说话人级 per-meeting 中心化）+ 贪心一对一 ──
    # 同一会议共享录音信道，说话人质心减全局均值后拉开人间差距；
    # ≥2 说话人 & ≥2 注册人时启用，其余退化为原始中位数矩阵。
    centered_mode = n_speakers >= 2 and n_refs >= 2
    if centered_mode:
        sid_centroids = np.stack([
            _vr._l2(np.mean(vecs, axis=0)) for vecs in group_vecs
        ])
        meeting_mean = np.mean(sid_centroids, axis=0)
        centered = sid_centroids - meeting_mean
        assign_matrix = np.zeros((n_speakers, n_refs), dtype=np.float32)
        for i in range(n_speakers):
            probe = centered[i]
            if np.linalg.norm(probe) < 1e-9:
                continue
            for j in range(n_refs):
                assign_matrix[i, j] = _vr.cosine_similarity(probe, ref_embeddings[j])
        logger.info(
            f"[声纹] 应用 per-meeting 中心化: {n_speakers} 位说话人, "
            f"均值 norm={np.linalg.norm(meeting_mean):.4f}"
        )
    else:
        assign_matrix = raw_med

    # 贪心一对一分配（纯 numpy，替代 scipy.optimize.linear_sum_assignment）
    row_ind, col_ind = _greedy_assignment(-assign_matrix)
    assigned: dict[int, int] = {}  # row_idx → col_idx
    for r, c in zip(row_ind, col_ind):
        if r < n_speakers and c < n_refs:
            assigned[r] = c

    # ── Step 4: 门槛校验（个人阈值多数表决 / 旧口径回退）+ 碎片化检测 ──
    thr = _vr.MATCH_THRESHOLD if threshold is None else threshold
    results: list[AutoMatchResult] = []

    from core.speakers import get_speaker_by_id

    for i, sid in enumerate(sids):
        if sid in insufficient_sids:
            results.append(AutoMatchResult(speaker_id=sid, status="insufficient_audio"))
            continue

        group_size = len(groups[sid])
        if i not in assigned:
            results.append(AutoMatchResult(
                speaker_id=sid, status="unmatched", group_size=group_size,
            ))
            continue

        j = assigned[i]
        best_uuid = ref_uuids[j]
        best_sim = float(raw_med[i, j])

        # margin 统一在原始空间计算：全行次高（旧口径），可能为负 → 拒绝
        sorted_sims = np.sort(raw_med[i])[::-1]
        second_sim = float(sorted_sims[1]) if n_refs > 1 else 0.0
        margin = best_sim - second_sim
        margin_ok = margin >= _vr.MIN_MATCH_MARGIN

        # 点群对最佳候选人的支持度
        chunk_sims_best = raw_chunk_sims[i][:, j]

        # 碎片化检测：组内点与组质心相似度的 25 分位过低 → ASR speaker 疑似混了两人
        fragmented = False
        if use_v2 and group_size >= 2:
            group_cen = _vr._l2(np.mean(group_vecs[i], axis=0))
            q25 = float(np.quantile(group_vecs[i] @ group_cen, 0.25))
            fragmented = q25 < FRAGMENTED_FLOOR
            if fragmented:
                logger.info(f"[声纹] speaker_{sid} 组内声音不纯（Q25={q25:.3f}），标记 fragmented")

        personal_thr = ref_thresholds[j] if use_v2 else None
        if personal_thr is not None:
            majority = float(np.mean(chunk_sims_best >= personal_thr))
            accepted = margin_ok and best_sim >= personal_thr and majority >= GROUP_MAJORITY_RATIO
            gate = "personal"
        elif centered_mode:
            # 无个人阈值时保持旧行为：中心化空间分配，仅 margin 把关
            majority = 1.0
            accepted = margin_ok
            gate = "margin_only"
        else:
            majority = 1.0
            accepted = margin_ok and best_sim >= thr
            gate = "global"

        best_speaker = get_speaker_by_id(best_uuid)
        best_name = best_speaker.name if best_speaker else None

        if accepted:
            results.append(AutoMatchResult(
                speaker_id=sid,
                matched_uuid=best_uuid,
                matched_name=best_name,
                similarity=best_sim,
                status="matched",
                best_candidate=best_name,
                margin=margin,
                group_size=group_size,
                majority=majority,
                fragmented=fragmented,
                gate=gate,
            ))
        else:
            results.append(AutoMatchResult(
                speaker_id=sid,
                similarity=best_sim,
                status="unmatched",
                best_candidate=best_name,
                margin=margin,
                group_size=group_size,
                majority=majority,
                fragmented=fragmented,
                gate=gate,
            ))

    matched_count = sum(1 for r in results if r.status == "matched")
    gate_tag = "v2.1 群嵌入" if use_v2 else "v1 回退"
    logger.info(
        f"[声纹] 自动识别（{gate_tag}，per-meeting 统筹分配）: "
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


def extract_speaker_embedding_group(
    audio_path: str | Path,
    dialogue: list[dict],
    speaker_id: int,
    max_sec_per_speaker: float = 180.0,
) -> tuple[list[tuple[np.ndarray, float]], float]:
    """
    从单场会议音频中提取指定 speaker_id 的声纹样本群（v2.1，多 chunk）。

    与 extract_speaker_embedding 的单向量口径不同：按 ~20s 有效语音切块，
    每块独立提嵌入，用于多样本注册与个人阈值标定。

    Returns:
        (样本群 [(embedding, duration_sec), ...], 发言总时长秒)
        音频不足或全部提取失败时样本群为空。
    """
    loaded = _load_audio(Path(audio_path))
    if loaded is None:
        return [], 0.0
    sr, audio_data = loaded

    segs = _collect_speaker_segments(dialogue or []).get(speaker_id, [])
    total_sec = sum(end - begin for begin, end in segs)
    if not segs or total_sec < _vr.MIN_REGISTER_SEC:
        return [], total_sec

    group = _extract_embedding_group(audio_data, sr, segs, True, max_sec_per_speaker)
    return group, total_sec


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
    sr, audio_data = loaded

    segs_map = _collect_speaker_segments(dialogue or [])

    for sid, uuid in normalized.items():
        segs = segs_map.get(sid, [])
        total_sec = sum(end - begin for begin, end in segs)
        if not segs or total_sec < _vr.MIN_REGISTER_SEC:
            results[uuid] = {"status": "insufficient_audio", "duration_sec": round(total_sec, 1)}
            logger.info(f"[声纹] 跳过注册: speaker={uuid[:8]}..., 音频不足 ({total_sec:.1f}s)")
            continue

        # v2.1：一场会议切多个 chunk 全部入库，个人阈值当场可标定
        group = _extract_embedding_group(audio_data, sr, segs, True, max_sec_per_speaker)
        if not group:
            results[uuid] = {"status": "extract_failed"}
            logger.warning(f"[声纹] 注册失败: speaker={uuid[:8]}..., 嵌入提取失败")
            continue

        acc = sum(dur for _, dur in group)
        _vr.register_voiceprint_samples(
            uuid,
            [(emb, dur, meeting_id) for emb, dur in group],
            meeting_id=meeting_id,
        )
        results[uuid] = {
            "status": "registered",
            "duration_sec": round(acc, 1),
            "samples": len(group),
        }

    registered = sum(1 for r in results.values() if r["status"] == "registered")
    logger.info(f"[声纹] 绑定自动注册: {registered}/{len(normalized)} 位说话人写入注册表")
    return results
