"""
core/voiceprint.py — 声纹提取与自动识别（兼容 re-export 层） / Voiceprint extraction and auto-identification (compatibility re-export layer)

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-03
版本 / Version: 2.0.0

v2.0 重构：按职责拆分为两个子模块 / v2.0 refactor: split by responsibility into two submodules.
  - core/voiceprint_registry.py — 数据层：常量 + 注册表 + 匹配算法 / Data layer: constants + registry + matching algorithm
  - core/voiceprint_identify.py — 管线层：自动识别 + 绑定注册 + 跨会议重建 / Pipeline layer: auto-identification + binding registration + cross-meeting rebuild

本文件保留为 re-export 兼容层，所有现有 import 路径无需修改 / This file retained as re-export compatibility layer; all existing import paths work unchanged.
"""

# 管线层：自动识别 + 绑定注册 / Pipeline layer: auto-identification + binding registration
from core.voiceprint_identify import (  # noqa: F401
    CHUNK_SEC,
    GROUP_MAJORITY_RATIO,
    AutoMatchResult,
    auto_identify_speakers,
    build_auto_mapping,
    extract_speaker_embedding,
    extract_speaker_embedding_group,
    merge_embeddings,
    register_from_binding,
)

# 数据层：常量 + 注册表 + 匹配
from core.voiceprint_registry import (  # noqa: F401
    COMPATIBLE_VERSIONS,
    DATA_DIR,
    EMBEDDING_DIM,
    MATCH_THRESHOLD,
    MAX_SAMPLES_PER_MEETING,
    MAX_SAMPLES_PER_SPEAKER,
    MAX_SEC_PER_SPEAKER,
    MIN_MATCH_MARGIN,
    MIN_REGISTER_SEC,
    PERSONAL_THR_CAP,
    PERSONAL_THR_FLOOR,
    PERSONAL_THR_MIN_SAMPLES,
    PERSONAL_THR_STD_K,
    REGISTRY_FILE,
    SAMPLE_RATE,
    VOICEPRINT_MODEL_VERSION,
    MatchDetail,
    VoiceprintRecord,
    _get_expected_embedding_dimension,
    _is_compatible_version,
    _l2,
    cosine_similarity,
    delete_voiceprint,
    extract_embedding,
    extract_embedding_from_pcm,
    get_voiceprint_status,
    load_registry,
    match_voiceprint,
    match_voiceprint_detail,
    register_voiceprint,
    register_voiceprint_samples,
    save_registry,
)
