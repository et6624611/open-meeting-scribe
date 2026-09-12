"""
core/i18n/middleware.py — i18n 中间件与翻译工具

职责：
  1. I18nMiddleware：解析 Accept-Language / Cookie / 查询参数，写入 ContextVar + request.state
  2. get_translator(locale)：返回 gettext 翻译函数（lru_cache 缓存）
  3. _()：便捷翻译函数，自动读取当前请求的 locale（ContextVar 驱动）

设计说明：
  采用 ContextVar 而非 request.state 传递 locale，使深层调用栈（如 core/errors.py、
  router 内 raise HTTPException）无需显式传 request 即可获得请求级语言，
  与 core/users.py 的 set_request_user_id 模式一致。
"""
import gettext
import os
from contextvars import ContextVar
from functools import lru_cache

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# ─── 配置 ───
SUPPORTED_LOCALES = {"zh_CN", "en"}
DEFAULT_LOCALE = "en"
DOMAIN = "messages"
LOCALES_DIR = os.path.join(os.path.dirname(__file__), "locales")
_current_locale: ContextVar[str] = ContextVar("i18n_locale", default=DEFAULT_LOCALE)


def set_current_locale(locale: str):
    """设置当前上下文的 locale（供中间件与 WebSocket 处理器调用）"""
    if locale not in SUPPORTED_LOCALES:
        locale = DEFAULT_LOCALE
    return _current_locale.set(locale)


def reset_current_locale(token) -> None:
    """请求结束后重置 ContextVar，避免连接池复用时状态泄漏"""
    try:
        _current_locale.reset(token)
    except (ValueError, LookupError):
        pass


def get_current_locale() -> str:
    """读取当前上下文的 locale"""
    return _current_locale.get()


@lru_cache(maxsize=32)
def get_translator(locale: str):
    """
    获取指定 locale 的 gettext 翻译函数。

    使用 lru_cache 缓存，避免重复加载 .mo 文件。
    如果指定 locale 的翻译文件不存在，回退到默认 locale。
    """
    try:
        return gettext.translation(
            DOMAIN, LOCALES_DIR, languages=[locale]
        )
    except FileNotFoundError:
        return gettext.translation(
            DOMAIN, LOCALES_DIR, languages=[DEFAULT_LOCALE]
        )


def _(text: str) -> str:
    """
    便捷翻译函数：自动使用当前请求的 locale（ContextVar）。

    无请求上下文时（如脚本、后台任务）回退到默认 locale。
    可在 router、core 模块的任意调用深度直接使用，无需传 request。
    """
    return get_translator(_current_locale.get()).gettext(text)


class I18nMiddleware(BaseHTTPMiddleware):
    """
    国际化中间件。

    语言选择优先级：
      1. 查询参数 ?lang=zh_CN
      2. Cookie "locale"
      3. Accept-Language 请求头
      4. 默认 locale（en）

    注入：
      - ContextVar（供 _() 全局读取）
      - request.state.locale / request.state.gettext（供显式使用）
    """

    async def dispatch(self, request: Request, call_next):
        locale = self._resolve_locale(request)
        token = set_current_locale(locale)
        request.state.locale = locale
        request.state.gettext = get_translator(locale).gettext
        try:
            return await call_next(request)
        finally:
            reset_current_locale(token)

    @staticmethod
    def _resolve_locale(request: Request) -> str:
        """按优先级解析语言偏好"""
        # 1. 查询参数
        locale = request.query_params.get("lang", "").strip()
        if locale:
            locale = locale.replace("-", "_")
            if locale in SUPPORTED_LOCALES:
                return locale

        # 2. Cookie
        locale = request.cookies.get("locale", "").strip()
        if locale:
            locale = locale.replace("-", "_")
            if locale in SUPPORTED_LOCALES:
                return locale

        # 3. Accept-Language 头
        accept = request.headers.get("accept-language", "")
        if accept:
            # 取第一个语言标签（如 "zh-CN,zh;q=0.9,en;q=0.8" → "zh-CN"）
            first = accept.split(",")[0].strip().split(";")[0].strip()
            locale = first.replace("-", "_")
            if locale in SUPPORTED_LOCALES:
                return locale

        # 4. 默认
        return DEFAULT_LOCALE
