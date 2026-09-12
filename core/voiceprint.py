"""
core/voiceprint.py — 声纹提取与自动识别（兼容 re-export 层）

作者：王永亮
创建：2026-09-03
版本：2.0.0

v2.0 重构：按职责拆分为两个子模块。
  - core/voiceprint_registry.py — 数据层：常量 + 注册表 + 匹配算法
  - core/voiceprint_identify.py — 管线层：自动识别 + 绑定注册 + 跨会议重建

本文件保留为 re-export 兼容层，所有现有 import 路径无需修改。
"""

# 数据层：常量 + 注册表 + 匹配
from core.voiceprint_registry import (
    DATA_DIR,
    REGISTRY_FILE,
    VOICEPRINT_MODEL_VERSION,
    COMPATIBLE_VERSIONS,
    MATCH_THRESHOLD,
    MIN_MATCH_MARGIN,
    EMBEDDING_DIM,
    MIN_REGISTER_SEC,
    MAX_SEC_PER_SPEAKER,
    SAMPLE_RATE,
    VoiceprintRecord,
    MatchDetail,
    extract_embedding,
    extract_embedding_from_pcm,
    load_registry,
    save_registry,
    register_voiceprint,
    delete_voiceprint,
    get_voiceprint_status,
    cosine_similarity,
    match_voiceprint,
    match_voiceprint_detail,
    _is_compatible_version,
    _get_expected_embedding_dimension,
    _l2,
)

# 管线层：自动识别 + 绑定注册
from core.voiceprint_identify import (
    AutoMatchResult,
    auto_identify_speakers,
    build_auto_mapping,
    merge_embeddings,
    extract_speaker_embedding,
    register_from_binding,
)
