"""
app/chat_attachment_store.py — AI 会话附件存储 / AI chat attachment store

职责 / Responsibilities:
  - 保存用户在 AI 面板通过 @附件 上传的本地文件与图片
  - 元数据落盘 + 原始字节读取（供后端展开为多模态消息 / 导出智能体工作区）

存储布局 / Layout:
  data/chat_attachments/<attach_id>/meta.json
  data/chat_attachments/<attach_id>/blob
"""

import json
import logging
import mimetypes
import shutil
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

ATTACHMENTS_DIR = Path("data/chat_attachments")
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)

# 限额 / Limits
ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024   # 单文件 10MB
ATTACHMENT_MAX_COUNT = 6                  # 单轮附件数


class AttachmentError(Exception):
    """附件校验/读取失败（消息面向用户，走 i18n 由调用方处理）。"""


def save_attachment(filename: str, content_type: str | None, data: bytes) -> dict:
    """保存一个附件，返回元数据 dict。超限抛 AttachmentError。"""
    if not filename:
        raise AttachmentError("empty filename")
    if len(data) == 0:
        raise AttachmentError("empty file")
    if len(data) > ATTACHMENT_MAX_BYTES:
        raise AttachmentError("file too large")

    attach_id = uuid.uuid4().hex
    directory = ATTACHMENTS_DIR / attach_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "blob").write_bytes(data)

    guessed = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    meta = {
        "id": attach_id,
        "filename": filename,
        "size": len(data),
        "content_type": guessed,
    }
    (directory / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    logger.info("保存聊天附件 id=%s name=%s size=%d", attach_id, filename, len(data))
    return meta


def get_meta(attach_id: str) -> dict:
    """读取附件元数据；不存在或 id 非法抛 AttachmentError。"""
    if not attach_id or "/" in attach_id or ".." in attach_id:
        raise AttachmentError("invalid attachment id")
    meta_file = ATTACHMENTS_DIR / attach_id / "meta.json"
    if not meta_file.exists():
        raise AttachmentError("attachment not found")
    return json.loads(meta_file.read_text(encoding="utf-8"))


def load_bytes(attach_id: str) -> tuple[dict, bytes]:
    """读取元数据 + 原始字节。"""
    meta = get_meta(attach_id)
    blob = ATTACHMENTS_DIR / attach_id / "blob"
    if not blob.exists():
        raise AttachmentError("attachment blob missing")
    return meta, blob.read_bytes()


def delete_attachment(attach_id: str) -> None:
    """删除附件目录（清理用，缺失静默）。"""
    if not attach_id or "/" in attach_id or ".." in attach_id:
        return
    directory = ATTACHMENTS_DIR / attach_id
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=True)
