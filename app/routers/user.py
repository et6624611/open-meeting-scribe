"""
app/routers/user.py — 用户信息 + 说话人绑定
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import users as user_module
from core.i18n import _

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
        raise HTTPException(400, _("Name cannot be empty"))
    user = user_module.set_current_user(req.name, req.avatar_color)
    return {"user": user}


@router.post("/api/user/bind-speaker")
def user_bind_speaker(req: UserBindSpeakerRequest):
    """将当前用户绑定到指定任务的某说话人（写 users.json）"""
    user = user_module.get_current_user()
    if not user:
        raise HTTPException(400, _("Please set up your name first"))
    speaker_uuid = user_module.bind_current_user_to_speaker(req.task_id, req.speaker_id)
    if not speaker_uuid:
        raise HTTPException(400, _("Binding failed"))
    return {"speaker_uuid": speaker_uuid, "user_name": user["name"]}


class UserPrefsUpdateRequest(BaseModel):
    local_diarization: bool | None = None


@router.get("/api/user/prefs")
def get_user_prefs():
    """获取当前用户偏好设置及订阅状态。

    返回：
      - prefs: 用户偏好（如 local_diarization）
      - subscription: 订阅信息（tier 等）
      - effective_diarization: 实际生效的声纹方案（"local" 或 "cloud"）
    """
    user = user_module.get_current_user()
    if not user:
        return {
            "prefs": {},
            "subscription": {"tier": "free"},
            "effective_diarization": "local",
        }

    prefs = user.get("prefs", {})
    subscription = user.get("subscription", {"tier": "free"})
    use_local = user_module.should_use_local_diarization()

    return {
        "prefs": {
            "local_diarization": prefs.get("local_diarization", False),
        },
        "subscription": {
            "tier": subscription.get("tier", "free"),
        },
        "effective_diarization": "local" if use_local else "cloud",
    }


@router.post("/api/user/prefs")
def update_user_prefs(req: UserPrefsUpdateRequest):
    """更新当前用户偏好设置。

    可更新字段：
      - local_diarization: bool — 是否使用本地 MFCC 声纹（仅订阅用户可设置，
        非订阅用户强制本地 MFCC，设置无效）

    返回更新后的偏好及实际生效方案。
    """
    user = user_module.get_current_user()
    if not user:
        raise HTTPException(401, _("Please log in first"))

    updates = {}

    if req.local_diarization is not None:
        subscription = user.get("subscription", {"tier": "free"})
        tier = subscription.get("tier", "free")
        if tier == "free":
            # 非订阅用户不允许切换，强制本地
            updates["local_diarization"] = True
        else:
            updates["local_diarization"] = req.local_diarization

    if updates:
        user_module.update_user_prefs(user["id"], updates)

    # 重新读取以获取最新值
    updated_user = user_module.get_current_user()
    prefs = updated_user.get("prefs", {}) if updated_user else {}
    use_local = user_module.should_use_local_diarization()

    return {
        "prefs": {
            "local_diarization": prefs.get("local_diarization", False),
        },
        "effective_diarization": "local" if use_local else "cloud",
    }
