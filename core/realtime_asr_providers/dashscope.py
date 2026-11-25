"""core/realtime_asr_providers/dashscope.py — DashScope 实时转写描述。

实际调用仍走 dashscope SDK（见 core/realtime_asr.py），此处只提供注册表元数据。
"""

from .base import RealtimeProviderSpec

DEFAULT_MODEL = "qwen-audio-3.0-asr-flash-streaming"


def build_spec() -> RealtimeProviderSpec:
    return RealtimeProviderSpec(
        key="dashscope",
        label_key="settings.compute.realtime_provider_dashscope",
        available=True,
        transport="dashscope_sdk",
        models=[DEFAULT_MODEL],
        default_model=DEFAULT_MODEL,
        credential_fields=[
            {
                "name": "api_key",
                "label_key": "settings.compute.realtime_cred_api_key",
                "type": "password",
                "required": True,
                "secret": True,
            },
        ],
        capabilities={
            "speaker_diarization": False,
            "punctuation": True,
            "itn": True,
            "hotwords": True,
            "timestamps": True,
        },
        sample_rate=16000,
        chunk_bytes=0,
        docs_url="https://help.aliyun.com/zh/model-studio/paraformer-real-time-speech-recognition-api",
    )
