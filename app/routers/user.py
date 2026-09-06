"""
app/routers/user.py — 用户信息 + 说话人绑定
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import users as user_module

router = APIRouter(tags=["user"])


class UserSetRequest(BaseModel):
    name: str
    avatar_color: str = "#4A90D9"


class UserBindSpeakerRequest(BaseModel):
    task_id: str
    speaker_id: str  # ASR 说话人编号，如 "0", "1"


@router.get("/api/user")
def get_user():
    """获取当前用户信息（读 users.json）"""
    user = user_module.get_current_user()
    return {"user": user}


@router.post("/api/user")
def set_user(req: UserSetRequest):
    """设置/更新当前用户姓名（写 users.json）"""
    if not req.name.strip():
        raise HTTPException(400, "姓名不能为空")
    user = user_module.set_current_user(req.name, req.avatar_color)
    return {"user": user}


@router.post("/api/user/bind-speaker")
def user_bind_speaker(req: UserBindSpeakerRequest):
    """将当前用户绑定到指定任务的某说话人（写 users.json）"""
    user = user_module.get_current_user()
    if not user:
        raise HTTPException(400, "请先设置用户姓名")
    speaker_uuid = user_module.bind_current_user_to_speaker(req.task_id, req.speaker_id)
    if not speaker_uuid:
        raise HTTPException(400, "绑定失败")
    return {"speaker_uuid": speaker_uuid, "user_name": user["name"]}
