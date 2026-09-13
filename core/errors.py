"""
core/errors.py — 错误分类与判断

为管线失败提供统一的错误分类机制：
  - 判断是否为瞬时错误（可自动重试）
  - 分类错误类型，生成用户可读的建议（支持 i18n 多语言）
"""

import logging

from core.i18n import _

logger = logging.getLogger(__name__)


def is_transient_error(error: Exception) -> bool:
    """
    判断是否为瞬时错误（可自动重试）。

    瞬时错误包括：
      - 网络超时（TimeoutError, requests.exceptions.Timeout）
      - 连接失败（ConnectionError, requests.exceptions.ConnectionError）
      - API 限流（HTTP 429, "too many requests", "throttl"）
      - 服务暂时不可用（HTTP 503）
      - DashScope 任务级临时失败

    Returns:
        True: 瞬时错误，可重试
        False: 永久错误，不应重试
    """
    error_str = str(error).lower()

    # 网络层错误
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True

    # requests 库异常（通过类名匹配，避免硬依赖）
    error_type = type(error).__name__
    if error_type in ("Timeout", "ConnectionError", "ConnectTimeout", "ReadTimeout"):
        return True

    # HTTP 状态码
    status_code = getattr(error, "response", None)
    if status_code is not None:
        try:
            code = status_code.status_code
            if code in (429, 503):
                return True
        except AttributeError:
            pass

    # 关键词匹配（覆盖各种封装场景）
    transient_keywords = [
        "too many requests",
        "throttl",
        "rate limit",
        "temporarily unavailable",
        "service unavailable",
        "connection reset",
        "connection refused",
        "connection aborted",
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
    分类错误，返回用户可读信息。

    Returns:
        {
            "category": "transient" | "audio" | "api_config" | "unknown",
            "message": 错误描述（技术向）,
            "suggestion": 给用户的建议（业务向）,
        }
    """
    error_str = str(error).lower()

    # ── 瞬时错误 ──
    if is_transient_error(error):
        return {
            "category": "transient",
            "message": str(error),
            "suggestion": _("Service temporarily unavailable, please try again later."),
        }

    # ── 音频文件相关错误 ──
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

    # ── API 配置错误 ──
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

    # ── 转写无有效语音（DashScope 返回 SUCCESS_WITH_NO_VALID_FRAGMENT）──
    # 注意：此检查必须在通用「转写任务失败」之前，否则会被后者的宽泛关键词先匹配
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

    # ── 转写任务失败（DashScope 返回 FAILED）──
    if "转写任务失败" in error_str or "transcription" in error_str:
        return {
            "category": "transient",
            "message": str(error),
            "suggestion": _("Transcription service error. Please try re-transcribing."),
        }

    # ── 未知错误 ──
    return {
        "category": "unknown",
        "message": str(error),
        "suggestion": _("Processing failed. Please try again. Contact support if the issue persists."),
    }
