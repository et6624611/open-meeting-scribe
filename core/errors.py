"""
core/errors.py — 错误分类与判断

为管线失败提供统一的错误分类机制：
  - 判断是否为瞬时错误（可自动重试）
  - 分类错误类型，生成用户可读的建议
"""

import logging

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
    error_type = type(error).__name__

    # ── 瞬时错误 ──
    if is_transient_error(error):
        return {
            "category": "transient",
            "message": str(error),
            "suggestion": "服务暂时不可用，已自动重试。若仍失败请稍后再试。",
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
            "suggestion": "音频文件可能有问题，请检查文件格式和完整性后重试。",
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
            "suggestion": "API 配置异常，请检查 API Key 和账户状态。",
        }

    # ── 转写无有效语音（DashScope 返回 SUCCESS_WITH_NO_VALID_FRAGMENT）──
    if "no_valid_fragment" in error_str or "未检测到有效语音" in error_str:
        return {
            "category": "audio",
            "message": str(error),
            "suggestion": "音频中未检测到有效语音片段，请确认录音是否正常、是否包含人声。",
        }

    # ── 转写任务失败（DashScope 返回 FAILED）──
    if "转写任务失败" in error_str or "transcription" in error_str:
        return {
            "category": "transient",
            "message": str(error),
            "suggestion": "转写服务返回错误，可尝试重新识别。",
        }

    # ── 未知错误 ──
    return {
        "category": "unknown",
        "message": str(error),
        "suggestion": "处理失败，请重试。若问题持续存在请联系支持。",
    }
