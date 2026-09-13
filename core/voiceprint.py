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

# 管线层：自动识别 + 绑定注册
from core.voiceprint_identify import (  # noqa: F401
    AutoMatchResult,
    auto_identify_speakers,
    build_auto_mapping,
    extract_speaker_embedding,
    merge_embeddings,
    register_from_binding,
)

# 数据层：常量 + 注册表 + 匹配
from core.voiceprint_registry import (  # noqa: F401
    COMPATIBLE_VERSIONS,
    DATA_DIR,
    EMBEDDING_DIM,
    MATCH_THRESHOLD,
    MAX_SEC_PER_SPEAKER,
    MIN_MATCH_MARGIN,
    MIN_REGISTER_SEC,
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
    save_registry,
)
