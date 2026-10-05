"""
core/speaker_count.py — 说话人数量估算（采样 + 谱聚类） / Speaker count estimation (sampling + spectral clustering)

职责 / Responsibilities:
  1. 从音频文件快速估算说话人数量 / Quick speaker count estimation from audio file
  2. 谱聚类 eigengap 启发式确定最优 k / Spectral clustering eigengap heuristic for optimal k
  3. 与贪心聚类结果交叉验证 / Cross-validate with greedy clustering results

用于文件上传场景（无实时录音过程，缺少实时聚类估算值） / Used for file upload scenarios (no realtime recording, lacks realtime clustering estimate).
"""

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# speaker_count 估算范围上下限 / speaker_count estimation range bounds
SPEAKER_COUNT_MIN = 1
SPEAKER_COUNT_MAX = 10


def estimate_speaker_count(audio_path: Path) -> int | None:
    """
    从音频文件快速估算说话人数量（采样法 + 谱聚类） / Quick speaker count estimation from audio (sampling + spectral clustering).

    流程 / Pipeline:
      1. 读取 WAV 文件头，计算总时长 / Read WAV header, compute total duration
      2. 在时长范围内均匀取 10-30 个采样点，每点提取 3 秒音频 / Uniformly sample 10-30 points, extract 3s audio each
      3. 对每个采样片段提取 CAM++ 声纹嵌入（降级 MFCC） / Extract CAM++ embedding per segment (fallback MFCC)
      4. 构建余弦相似度矩阵 → 谱聚类（eigengap 启发式）确定最优 k / Cosine similarity matrix → spectral clustering (eigengap heuristic) for optimal k
      5. 与贪心聚类结果交叉验证，取更可靠的一方 / Cross-validate with greedy clustering, take more reliable result
      6. 钳制到 [SPEAKER_COUNT_MIN, SPEAKER_COUNT_MAX] / Clamp to [SPEAKER_COUNT_MIN, SPEAKER_COUNT_MAX]

    谱聚类相比贪心余弦聚类的优势 / Advantages of spectral clustering over greedy cosine:
      - 不依赖固定阈值（贪心用 0.55，对不同录音适应性差） / No fixed threshold dependency (greedy uses 0.55, poor adaptability)
      - eigengap 启发式自动确定最优簇数 / Eigengap heuristic auto-determines optimal cluster count
      - 对非球形簇分布更鲁棒 / More robust to non-spherical cluster distributions

    用于文件上传场景（无实时录音过程，缺少实时聚类估算值） / Used for file upload scenarios (no realtime recording, lacks realtime clustering estimate).
    """
    try:
        import struct as _struct

        from core.audio import normalize_audio
        from core.diarization import (
            SAMPLE_RATE,
            SpeakerDiarizer,
            _is_speech,
            extract_speaker_feature,
        )

        # 先归一化为 WAV（上传文件可能是 MP3/M4A 等） / Normalize to WAV first (uploaded file may be MP3/M4A etc.)
        normalized = normalize_audio(audio_path)

        with open(normalized, "rb") as f:
            # 读取 WAV 文件头，定位 data chunk / Read WAV header, locate data chunk
            riff = f.read(4)
            if riff != b"RIFF":
                logger.warning(f"[说话人估算] 非 WAV 文件: {audio_path.name}")
                return None

            f.read(4)  # file size
            f.read(4)  # WAVE

            data_offset = None
            num_channels = 1
            sample_rate = SAMPLE_RATE
            bits_per_sample = 16

            while True:
                chunk_id = f.read(4)
                if len(chunk_id) < 4:
                    break
                chunk_size = _struct.unpack("<I", f.read(4))[0]

                if chunk_id == b"fmt ":
                    fmt_data = f.read(chunk_size)
                    num_channels = _struct.unpack("<H", fmt_data[2:4])[0]
                    sample_rate = _struct.unpack("<I", fmt_data[4:8])[0]
                    bits_per_sample = _struct.unpack("<H", fmt_data[14:16])[0]
                elif chunk_id == b"data":
                    data_offset = f.tell()
                    data_size = chunk_size
                    break
                else:
                    f.seek(chunk_size, 1)  # 跳过未知 chunk

            if data_offset is None:
                logger.warning("[说话人估算] 未找到 data chunk")
                return None

            # 计算音频时长
            bytes_per_sample = num_channels * bits_per_sample // 8
            total_samples = data_size // bytes_per_sample
            duration_sec = total_samples / sample_rate

            if duration_sec < 3:
                logger.info(f"[说话人估算] 音频过短 ({duration_sec:.1f}s)，默认 1 人")
                return 1

            # 均匀采样：10-30 个点，每点取 3 秒片段
            num_points = max(10, min(30, int(duration_sec / 10)))
            chunk_duration = 3.0  # 每段 3 秒
            chunk_bytes = int(chunk_duration * sample_rate * bytes_per_sample)

            # ── 提取特征向量（直接提取，不经过聚类器内部聚类） ──
            features = []
            diarizer = SpeakerDiarizer()  # 仍用贪心法做交叉验证

            for i in range(num_points):
                if num_points == 1:
                    sample_start = 0
                else:
                    sample_start = (i / (num_points - 1)) * (duration_sec - chunk_duration)
                sample_start = max(0, min(sample_start, duration_sec - chunk_duration))

                byte_pos = data_offset + int(sample_start * sample_rate * bytes_per_sample)
                f.seek(byte_pos)
                chunk_data = f.read(chunk_bytes)

                if len(chunk_data) < chunk_bytes:
                    continue

                # VAD 过滤：静音段不提取特征
                if not _is_speech(chunk_data):
                    continue

                feat = extract_speaker_feature(chunk_data)
                if feat is not None:
                    features.append(feat)

                # 同时馈入贪心聚类器（交叉验证用）
                diarizer.feed_audio(chunk_data, timestamp=sample_start)

            if len(features) < 3:
                # 特征不足，退化到贪心结果（含后处理合并）
                greedy_count = diarizer.finalize()
                clamped = max(SPEAKER_COUNT_MIN, min(SPEAKER_COUNT_MAX, greedy_count))
                logger.info(f"[说话人估算] 特征不足({len(features)})，仅贪心: {clamped}")
                return clamped

            # ── 谱聚类：eigengap 启发式确定最优 k ──
            spectral_count = _spectral_estimate_k(features)
            greedy_count = diarizer.finalize()  # 含后处理合并

            # 选择策略：
            # - 谱聚类结果在 [2, 8] 范围内时优先采信（eigengap 有明确信号）
            # - 否则退化到贪心结果
            if spectral_count is not None and 2 <= spectral_count <= 8:
                chosen = spectral_count
                method = "spectral"
            else:
                chosen = greedy_count
                method = "greedy"

            clamped = max(SPEAKER_COUNT_MIN, min(SPEAKER_COUNT_MAX, chosen))
            logger.info(
                f"[说话人估算] {audio_path.name}: 时长={duration_sec:.0f}s, "
                f"采样={num_points}点, 特征={len(features)}, "
                f"谱聚类={spectral_count}, 贪心={greedy_count}, "
                f"选用={chosen}({method}), 钳制={clamped}"
            )
            return clamped

    except Exception as e:
        logger.warning(f"[说话人估算] 失败: {e}")
        return None


def _spectral_estimate_k(
    features: list[np.ndarray],
    max_k: int = 8,
) -> int | None:
    """
    谱聚类 eigengap 启发式：自动确定最优簇数 k。

    算法：
      1. 构建余弦相似度矩阵 A（高斯核变换）
      2. 计算归一化图拉普拉斯 L_sym = I - D^{-1/2} A D^{-1/2}
      3. 求 L_sym 的前 max_k+1 个最小特征值
      4. 找最大 eigengap（相邻特征值之差最大的位置）

    Returns:
        最优 k（2~max_k），或 None（特征不足 / 计算失败）
    """
    n = len(features)
    if n < 4:
        return None

    F = np.stack(features)
    # L2 归一化（防御性）
    norms = np.linalg.norm(F, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-9)
    F = F / norms

    # 余弦相似度矩阵 → 高斯核（sigma 自适应）
    sim = F @ F.T
    np.fill_diagonal(sim, 0)  # 去掉自环

    # sigma = 所有正相似度的中位数（自适应带宽）
    positive_sims = sim[sim > 0]
    if len(positive_sims) == 0:
        return None
    sigma = float(np.median(positive_sims))
    if sigma < 1e-9:
        return None

    A = np.exp(-(1 - sim) / (2 * sigma ** 2))
    np.fill_diagonal(A, 0)

    # 归一化拉普拉斯 L_sym = I - D^{-1/2} A D^{-1/2}
    d = A.sum(axis=1)
    d_inv_sqrt = np.where(d > 1e-9, 1.0 / np.sqrt(d), 0)
    D_inv_sqrt = np.diag(d_inv_sqrt)
    L_sym = np.eye(n) - D_inv_sqrt @ A @ D_inv_sqrt

    # 对称化（消除数值误差）
    L_sym = (L_sym + L_sym.T) / 2

    # 求最小的 max_k+1 个特征值（numpy.linalg.eigh 替代 scipy.linalg.eigh）
    try:
        all_eigenvalues = np.linalg.eigvalsh(L_sym)
        k = min(max_k, n - 1) + 1
        eigenvalues = all_eigenvalues[:k]
    except Exception:
        return None

    eigenvalues = np.sort(np.real(eigenvalues))

    # eigengap：相邻特征值之差
    if len(eigenvalues) < 3:
        return None
    gaps = np.diff(eigenvalues[1:])  # 跳过第一个接近 0 的特征值

    if len(gaps) == 0:
        return None

    # 最大 eigengap 的位置 → k
    best_k = int(np.argmax(gaps) + 2)  # +2 补偿跳过第一个 + diff 偏移

    # 置信度检查：最大 gap 必须显著大于平均 gap
    mean_gap = float(np.mean(gaps))
    max_gap = float(gaps[np.argmax(gaps)])
    if max_gap < mean_gap * 1.5:
        # eigengap 信号不够强，返回 None（让调用方退化到贪心）
        logger.debug(
            f"[谱聚类] eigengap 信号弱: max={max_gap:.4f}, "
            f"mean={mean_gap:.4f}, ratio={max_gap/max(mean_gap,1e-9):.2f}"
        )
        return None

    logger.debug(f"[谱聚类] eigenvalues={eigenvalues[:min(6,len(eigenvalues))].round(4)}, k={best_k}")
    return best_k
