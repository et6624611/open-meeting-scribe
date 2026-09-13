"""
core/i18n — 国际化支持

基于 Babel + gettext 实现后端多语言：
  - I18nMiddleware：从请求头解析语言偏好，注入 request.state
  - get_translator()：按 locale 获取翻译函数（lru_cache 缓存）
  - _()：便捷翻译函数（无 request context 时使用默认 locale）
"""
from core.i18n.middleware import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    I18nMiddleware,
    _,
    get_current_locale,
    get_translator,
    reset_current_locale,
    set_current_locale,
)

__all__ = [
    "I18nMiddleware",
    "get_translator",
    "_",
    "set_current_locale",
    "reset_current_locale",
    "get_current_locale",
    "SUPPORTED_LOCALES",
    "DEFAULT_LOCALE",
]
