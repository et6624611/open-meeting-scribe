"""
app/chat_attachment_store.py — 兼容 re-export 层 / Compatibility re-export layer

实际实现已下沉至 core/chat_attachment_store.py（2026-11-06）；本文件保留以维持既有 import 路径。
/ Implementation sunk to core/chat_attachment_store.py; this file remains for backward-compat import paths.

使用模块 __getattr__ 动态代理。注意：patch ATTACHMENTS_DIR 等常量请落到 core 层，
本层 setattr 只遮蔽代理，不影响实现读取的模块全局。
"""

import core.chat_attachment_store as _core


def __getattr__(name):
    """动态代理到 core.chat_attachment_store。"""
    if name.startswith("_"):
        raise AttributeError(name)
    try:
        return getattr(_core, name)
    except AttributeError:
        raise AttributeError(f"module 'app.chat_attachment_store' has no attribute {name!r}")


# ruff: noqa: F822 — re-export 层，__all__ 列出的名字通过 __getattr__ 动态转发到 core.*，静态分析无法识别
__all__ = [
    "ATTACHMENT_MAX_BYTES",
    "ATTACHMENT_MAX_COUNT",
    "ATTACHMENTS_DIR",
    "AttachmentError",
    "delete_attachment",
    "get_meta",
    "load_bytes",
    "save_attachment",
]
