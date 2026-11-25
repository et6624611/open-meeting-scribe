"""core/realtime_asr_providers/registry.py — 实时 ASR 厂商注册表。

首批开放 auto / dashscope / volcengine；讯飞、腾讯保留 spec，available=False。
"""

from __future__ import annotations

from .base import RealtimeProviderSpec
from .dashscope import build_spec as _dashscope_spec

VOLCENGINE_RESOURCE_OPTIONS = [
    {"value": "volc.seedasr.sauc.duration", "label_key": "settings.compute.realtime_volc_res_20_duration"},
    {"value": "volc.seedasr.sauc.concurrent", "label_key": "settings.compute.realtime_volc_res_20_concurrent"},
    {"value": "volc.bigasr.sauc.duration", "label_key": "settings.compute.realtime_volc_res_10_duration"},
    {"value": "volc.bigasr.sauc.concurrent", "label_key": "settings.compute.realtime_volc_res_10_concurrent"},
]


def _auto_spec() -> RealtimeProviderSpec:
    return RealtimeProviderSpec(
        key="auto",
        label_key="settings.compute.realtime_provider_auto",
        available=True,
        transport="auto",
        models=[],
        default_model="",
        capabilities={
            "speaker_diarization": False,
            "punctuation": True,
            "itn": True,
            "hotwords": True,
            "timestamps": True,
        },
    )


def _volcengine_spec() -> RealtimeProviderSpec:
    return RealtimeProviderSpec(
        key="volcengine",
        label_key="settings.compute.realtime_provider_volcengine",
        available=True,
        transport="ws",
        models=["bigmodel"],
        default_model="bigmodel",
        credential_fields=[
            {
                "name": "api_key",
                "label_key": "settings.compute.realtime_cred_api_key",
                "type": "password",
                "required": True,
                "secret": True,
            },
            {
                "name": "resource_id",
                "label_key": "settings.compute.realtime_cred_resource_id",
                "type": "select",
                "required": True,
                "secret": False,
                "options": VOLCENGINE_RESOURCE_OPTIONS,
                "default": "volc.bigasr.sauc.duration",
            },
        ],
        capabilities={
            "speaker_diarization": True,
            "punctuation": True,
            "itn": True,
            "hotwords": False,
            "timestamps": True,
        },
        sample_rate=16000,
        chunk_bytes=6400,
        docs_url="https://docs.volcengine.com/docs/doubao-voice/large-model-streaming-automatic-speech-recognition-api-1",
        # 豆包大模型流式把说话人放在 utterances[].additions.speaker_id
        speaker_label_paths=["additions.speaker_id", "speaker", "speaker_id", "spk"],
    )


def _xfyun_spec() -> RealtimeProviderSpec:
    return RealtimeProviderSpec(
        key="xfyun",
        label_key="settings.compute.realtime_provider_xfyun",
        available=False,
        transport="ws",
        models=["cn", "en"],
        default_model="cn",
        credential_fields=[
            {"name": "app_id", "label_key": "settings.compute.realtime_cred_app_id", "type": "text", "required": True, "secret": False},
            {"name": "api_key", "label_key": "settings.compute.realtime_cred_api_key", "type": "password", "required": True, "secret": True},
        ],
        capabilities={
            "speaker_diarization": True,
            "punctuation": True,
            "itn": False,
            "hotwords": False,
            "timestamps": True,
        },
        sample_rate=16000,
        chunk_bytes=1280,
        docs_url="https://www.xfyun.cn/doc/asr/rtasr/API.html",
        speaker_label_paths=["role", "spk", "speaker"],
    )


def _tencent_spec() -> RealtimeProviderSpec:
    return RealtimeProviderSpec(
        key="tencent",
        label_key="settings.compute.realtime_provider_tencent",
        available=False,
        transport="ws",
        models=["16k_zh", "16k_zh_en_speaker_2.0"],
        default_model="16k_zh",
        credential_fields=[
            {"name": "app_id", "label_key": "settings.compute.realtime_cred_app_id", "type": "text", "required": True, "secret": False},
            {"name": "secret_id", "label_key": "settings.compute.realtime_cred_secret_id", "type": "text", "required": True, "secret": False},
            {"name": "secret_key", "label_key": "settings.compute.realtime_cred_secret_key", "type": "password", "required": True, "secret": True},
        ],
        capabilities={
            "speaker_diarization": False,
            "punctuation": True,
            "itn": True,
            "hotwords": True,
            "timestamps": True,
        },
        model_capabilities={
            "16k_zh_en_speaker_2.0": {"speaker_diarization": True},
        },
        sample_rate=16000,
        chunk_bytes=6400,
        docs_url="https://cloud.tencent.com/document/product/1093/48982",
        speaker_label_paths=["speaker_id"],
    )


SPECS: dict[str, RealtimeProviderSpec] = {
    spec.key: spec
    for spec in (
        _auto_spec(),
        _dashscope_spec(),
        _volcengine_spec(),
        _xfyun_spec(),
        _tencent_spec(),
    )
}


def get_spec(key: str) -> RealtimeProviderSpec | None:
    return SPECS.get(key)


def list_public_specs() -> list[dict]:
    return [spec.to_public_dict() for spec in SPECS.values()]


def create_provider(key: str, config: dict, **callbacks):
    """按 provider key 创建客户端。仅 volcengine 有独立实现，dashscope 走 SDK 分支。"""
    if key == "volcengine":
        from .volcengine import VolcengineProvider

        return VolcengineProvider(
            credentials=config.get("credentials") or {},
            model=config.get("model") or "bigmodel",
            options={
                "base_url": config.get("base_url") or "",
                "enable_speaker": bool(config.get("enable_speaker")),
                "speaker_label_paths": (get_spec("volcengine") or _volcengine_spec()).speaker_label_paths,
            },
            **callbacks,
        )
    raise ValueError(f"未实现的实时 ASR 厂商: {key}")
