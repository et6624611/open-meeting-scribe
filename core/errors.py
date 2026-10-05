"""
core/errors.py — 错误分类与判断 / Error classification and detection

为管线失败提供统一的错误分类机制 / Unified error classification for pipeline failures:
  - 判断是否为瞬时错误（可自动重试） / Detect transient errors (auto-retryable)
  - 分类错误类型，生成用户可读的建议（支持 i18n 多语言） / Classify error types, generate user-readable suggestions (i18n supported)
"""

import logging

from core.i18n import _

logger = logging.getLogger(__name__)


class LocalEngineError(RuntimeError):
    """本地引擎（离线 FunASR / CAM++）推理失败的结构化错误（R1/R3 / AC-4）。

    携带机器可读 error_code 与「是否可回退云端」标志，供上层做显式确认后回退
    （PRD R7：绝不静默上云）。error_code 取值：
      - models_missing / models_tampered：模型未就绪或被篡改（前往设置下载/重下）
      - engine_unhealthy：常驻子进程启动或健康检查失败
      - engine_timeout：推理超时（子进程可能需重启）
      - inference_failed：FunASR 推理返回错误
      - audio_not_found：音频文件缺失
      - audio_too_long：超过本地批转写支持上限（WP-H，切分文件或显式回退云端）
      - realtime_degraded_to_batch：实时预览按设计降级为批处理（非故障，WP-H 状态声明）
    """

    def __init__(
        self,
        message: str,
        error_code: str = "inference_failed",
        can_fallback_cloud: bool = False,
        detail: dict | None = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.can_fallback_cloud = can_fallback_cloud
        self.detail = detail or {}


def is_transient_error(error: Exception) -> bool:
    """
    判断是否为瞬时错误（可自动重试） / Detect if error is transient (auto-retryable).

    瞬时错误包括 / Transient errors include:
      - 网络超时 / Network timeouts (TimeoutError, requests.exceptions.Timeout)
      - 连接失败 / Connection failures (ConnectionError, requests.exceptions.ConnectionError)
      - API 限流 / API rate limiting (HTTP 429, "too many requests", "throttl")
      - 服务暂时不可用 / Service temporarily unavailable (HTTP 503)
      - DashScope 任务级临时失败 / DashScope task-level transient failures

    Returns:
        True: 瞬时错误，可重试 / Transient error, retryable
        False: 永久错误，不应重试 / Permanent error, should not retry
    """
    error_str = str(error).lower()

    # 网络层错误 / Network-layer errors
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True

    # requests 库异常（通过类名匹配，避免硬依赖） / requests library exceptions (match by class name, avoid hard dependency)
    error_type = type(error).__name__
    if error_type in ("Timeout", "ConnectionError", "ConnectTimeout", "ReadTimeout"):
        return True

    # 模型误拒（充足对话被判内容不足）：重试大概率成功，且可避免拒答话术覆盖既有纪要
    # Model mis-refusal on substantial dialogue: retry likely succeeds; prevents refusal text overwriting good minutes
    if error_type == "SummaryRefusalError":
        return True

    # HTTP 状态码 / HTTP status codes
    status_code = getattr(error, "response", None)
    if status_code is not None:
        try:
            code = status_code.status_code
            if code in (429, 503):
                return True
        except AttributeError:
            pass

    # 关键词匹配（覆盖各种封装场景） / Keyword matching (covers various wrapping scenarios)
    transient_keywords = [
        "too many requests",
        "throttl",
        "rate limit",
        "temporarily unavailable",
        "service unavailable",
        "connection reset",
        "connection refused",
        "connection aborted",
        # httpx/ollama 原生文案（洞察板 connect 归因实拍：All connection attempts failed / Server disconnected）
        "connection attempts failed",
        "server disconnected",
        "connection error",
        "timed out",
        "timeout",
        "503",
        "429",
        "临时",
        "稍后重试",
    ]
    return any(kw in error_str for kw in transient_keywords)


def classify_error(error: Exception) -> dict:
    """
    分类错误，返回用户可读信息 / Classify error, return user-readable info.

    Returns:
        {
            "category": "transient" | "audio" | "api_config" | "unknown",
            "message": 错误描述（技术向） / Error description (technical),
            "suggestion": 给用户的建议（业务向） / User suggestion (business-oriented),
        }
    """
    error_str = str(error).lower()

    # ── 本地引擎错误（R1/R3 / AC-4）：优先于通用分类，给出可行动出口 ──
    if isinstance(error, LocalEngineError):
        code = error.error_code
        if code in ("models_missing", "models_tampered"):
            suggestion = _("Local engine models are not ready. Please download them in Settings, or switch back to cloud.")
        elif code == "engine_timeout":
            suggestion = _("Local engine timed out. Please retry, or switch back to cloud.")
        elif code == "audio_too_long":
            # WP-H：超过本地批转写支持上限（口径见 core/engine_host.LOCAL_ASR_MAX_SUPPORTED_SECONDS）
            suggestion = _("Audio is longer than the local engine supports per file. Split the file, or switch back to cloud and retry; the original audio is kept.")
        else:
            suggestion = _("Local engine inference failed. You can switch back to cloud and retry; your task state is preserved.")
        return {
            "category": "local_engine",
            "error_code": code,
            "can_fallback_cloud": error.can_fallback_cloud,
            "message": str(error),
            "suggestion": suggestion,
        }

    # ── 瞬时错误 / Transient errors ──
    if is_transient_error(error):
        return {
            "category": "transient",
            "message": str(error),
            "suggestion": _("Service temporarily unavailable, please try again later."),
        }

    # ── 音频文件相关错误 / Audio file errors ──
    audio_keywords = [
        "文件不存在",
        "not found",
        "不支持的文件类型",
        "unsupported",
        "音频过短",
        "too short",
        "invalid audio",
        "ffmpeg",
        "音频文件",
        "no such file",
        "filenotfounderror",
    ]
    if any(kw in error_str for kw in audio_keywords):
        return {
            "category": "audio",
            "message": str(error),
            "suggestion": _("Audio file issue detected. Please check the file format and integrity."),
        }

    # ── API 配置错误 / API configuration errors ──
    api_keywords = [
        "api_key",
        "api key",
        "未设置",
        "unauthorized",
        "401",
        "403",
        "invalid key",
        "quota",
        "配额",
        "余额",
        "balance",
        "dashscope_api_key",
    ]
    if any(kw in error_str for kw in api_keywords):
        return {
            "category": "api_config",
            "message": str(error),
            "suggestion": _("API configuration error. Please check API Key and account status."),
        }

    # ── 转写无有效语音（DashScope 返回 SUCCESS_WITH_NO_VALID_FRAGMENT） / No valid speech in transcription (DashScope returns SUCCESS_WITH_NO_VALID_FRAGMENT) ──
    # 注意：此检查必须在通用「转写任务失败」之前，否则会被后者的宽泛关键词先匹配 / Note: must precede generic "transcription failed" check, otherwise broader keywords match first
    if any(kw in error_str for kw in [
        "no_valid_fragment",
        "no valid fragment",
        "未检测到有效语音",
        "no valid speech",
    ]):
        return {
            "category": "audio",
            "message": str(error),
            "suggestion": _("No valid speech detected in the audio. Please confirm the recording contains human voice."),
        }

    # ── 转写任务失败（DashScope 返回 FAILED） / Transcription task failed (DashScope returns FAILED) ──
    if "转写任务失败" in error_str or "transcription" in error_str:
        return {
            "category": "transient",
            "message": str(error),
            "suggestion": _("Transcription service error. Please try re-transcribing."),
        }

    # ── 未知错误 / Unknown errors ──
    return {
        "category": "unknown",
        "message": str(error),
        "suggestion": _("Processing failed. Please try again. Contact support if the issue persists."),
    }
