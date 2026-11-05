"""app/routers/chat_history_routes.py — 附件支撑端点。

端点：
  POST /api/chat/attachments       — 上传 AI 会话附件
  GET  /api/chat/attachments/{id}  — 读取附件（内联预览 / 下载）

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-05（从 chat.py 拆分）
"""

import logging
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app import chat_attachment_store
from core.i18n import _

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/api/chat/attachments")
async def upload_chat_attachments(files: list[UploadFile] = File(...)):
    """上传 AI 会话附件（本地文件与图片），返回元数据列表。"""
    if not files:
        raise HTTPException(400, _("No files uploaded"))
    if len(files) > chat_attachment_store.ATTACHMENT_MAX_COUNT:
        raise HTTPException(400, _("Too many attachments (max {max})").format(
            max=chat_attachment_store.ATTACHMENT_MAX_COUNT))

    saved: list[dict] = []
    try:
        for f in files:
            data = await f.read()
            saved.append(chat_attachment_store.save_attachment(
                f.filename or "untitled", f.content_type, data))
    except chat_attachment_store.AttachmentError as e:
        for meta in saved:  # 部分失败：回滚已存附件
            chat_attachment_store.delete_attachment(meta["id"])
        status = 413 if str(e) == "file too large" else 400
        if status == 413:
            raise HTTPException(status, _("File too large (max {max} MB)").format(max=10))
        raise HTTPException(status, _("Invalid file"))
    return {"attachments": saved}


@router.get("/api/chat/attachments/{attach_id}")
async def fetch_chat_attachment(attach_id: str, download: int = 0):
    """读取附件（默认内联预览，download=1 强制下载）。"""
    try:
        meta, data = chat_attachment_store.load_bytes(attach_id)
    except chat_attachment_store.AttachmentError:
        raise HTTPException(404, _("Attachment not found"))
    disposition = "attachment" if download else "inline"
    from urllib.parse import quote
    return StreamingResponse(
        iter([data]),
        media_type=meta["content_type"],
        headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(meta['filename'])}"},
    )
