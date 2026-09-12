"""
core/speakers.py — 说话人档案管理

作者：王永亮
创建：2026-09-03
版本：1.0.0

职责：
  1. 管理全局说话人列表（姓名、角色、备注）
  2. 管理会议级 speaker_id → 说话人 映射
  3. 提供历史复用机制（同一批人开会时快速复用）

数据文件：
  - data/speakers.json：全局说话人档案
  - data/meeting_mappings.json：会议映射历史（用于复用建议）
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# 数据目录
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# 数据文件路径
SPEAKERS_FILE = DATA_DIR / "speakers.json"
MAPPINGS_FILE = DATA_DIR / "meeting_mappings.json"


# ============================================================
# 数据模型
# ============================================================

class Speaker:
    """说话人档案"""
    def __init__(
        self,
        speaker_id: str,
        name: str,
        role: str = "",
        note: str = "",
        created_at: str = "",
        linked_user_id: str | None = None,
    ):
        self.speaker_id = speaker_id  # 唯一标识（UUID 或自定义）
        self.name = name              # 姓名
        self.role = role              # 角色/职位（可选）
        self.note = note              # 备注（可选）
        self.created_at = created_at or datetime.now().isoformat()
        self.linked_user_id = linked_user_id  # 关联的系统用户 ID（可选）

    def to_dict(self) -> dict:
        return {
            "speaker_id": self.speaker_id,
            "name": self.name,
            "role": self.role,
            "note": self.note,
            "created_at": self.created_at,
            "linked_user_id": self.linked_user_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Speaker":
        return cls(
            speaker_id=data["speaker_id"],
            name=data["name"],
            role=data.get("role", ""),
            note=data.get("note", ""),
            created_at=data.get("created_at", ""),
            linked_user_id=data.get("linked_user_id"),
        )


class MeetingMapping:
    """会议映射记录（用于历史复用）"""
    def __init__(
        self,
        meeting_id: str,
        meeting_name: str,
        mapping: dict[int, str],  # speaker_id → speaker.speaker_id
        created_at: str = "",
    ):
        self.meeting_id = meeting_id
        self.meeting_name = meeting_name
        self.mapping = mapping  # {0: "uuid1", 1: "uuid2"}
        self.created_at = created_at or datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "meeting_id": self.meeting_id,
            "meeting_name": self.meeting_name,
            "mapping": self.mapping,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MeetingMapping":
        # mapping 的 key 需要转回 int
        mapping = {int(k): v for k, v in data.get("mapping", {}).items()}
        return cls(
            meeting_id=data["meeting_id"],
            meeting_name=data["meeting_name"],
            mapping=mapping,
            created_at=data.get("created_at", ""),
        )


# ============================================================
# 全局说话人档案
# ============================================================

def load_speakers() -> list[Speaker]:
    """加载全局说话人列表"""
    if not SPEAKERS_FILE.exists():
        return []
    try:
        with open(SPEAKERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [Speaker.from_dict(item) for item in data]
    except Exception as e:
        logger.error(f"加载说话人档案失败: {e}")
        return []


def save_speakers(speakers: list[Speaker]) -> None:
    """保存全局说话人列表"""
    try:
        data = [s.to_dict() for s in speakers]
        with open(SPEAKERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"说话人档案已保存: {len(speakers)} 人")
    except Exception as e:
        logger.error(f"保存说话人档案失败: {e}")


def add_speaker(name: str, role: str = "", note: str = "") -> Speaker:
    """添加说话人"""
    import uuid
    speakers = load_speakers()
    new_speaker = Speaker(
        speaker_id=str(uuid.uuid4()),
        name=name,
        role=role,
        note=note,
    )
    speakers.append(new_speaker)
    save_speakers(speakers)
    logger.info(f"添加说话人: {name}")
    return new_speaker


def update_speaker(speaker_id: str, name: str = None, role: str = None, note: str = None) -> Optional[Speaker]:
    """更新说话人信息"""
    speakers = load_speakers()
    for s in speakers:
        if s.speaker_id == speaker_id:
            if name is not None:
                s.name = name
            if role is not None:
                s.role = role
            if note is not None:
                s.note = note
            save_speakers(speakers)
            logger.info(f"更新说话人: {s.name}")
            return s
    return None


def delete_speaker(speaker_id: str) -> bool:
    """删除说话人"""
    speakers = load_speakers()
    new_speakers = [s for s in speakers if s.speaker_id != speaker_id]
    if len(new_speakers) < len(speakers):
        save_speakers(new_speakers)
        logger.info(f"删除说话人: {speaker_id}")
        return True
    return False


def get_speaker_by_id(speaker_id: str) -> Optional[Speaker]:
    """根据 speaker_id 获取说话人"""
    speakers = load_speakers()
    for s in speakers:
        if s.speaker_id == speaker_id:
            return s
    return None


def set_linked_user(speaker_id: str, user_id: str) -> Optional[Speaker]:
    """
    将说话人关联到系统用户。同一用户只能关联一个说话人。

    如果该 user_id 已关联其他说话人，先解除旧关联。
    """
    speakers = load_speakers()
    target = None
    for s in speakers:
        if s.speaker_id == speaker_id:
            target = s
        elif s.linked_user_id == user_id:
            s.linked_user_id = None
    if not target:
        return None
    target.linked_user_id = user_id
    save_speakers(speakers)
    logger.info(f"说话人关联用户: {target.name} → user={user_id}")
    return target


def clear_linked_user(speaker_id: str) -> Optional[Speaker]:
    """解除说话人的用户关联"""
    speakers = load_speakers()
    for s in speakers:
        if s.speaker_id == speaker_id:
            s.linked_user_id = None
            save_speakers(speakers)
            logger.info(f"解除说话人用户关联: {s.name}")
            return s
    return None


def find_speaker_by_name(name: str) -> Optional[Speaker]:
    """根据姓名查找说话人（精确匹配）"""
    speakers = load_speakers()
    for s in speakers:
        if s.name == name:
            return s
    return None


def get_speaker_name_map() -> dict[str, str]:
    """获取 speaker_id → name 的映射表"""
    speakers = load_speakers()
    return {s.speaker_id: s.name for s in speakers}


# ============================================================
# 会议映射管理
# ============================================================

def load_mappings() -> list[MeetingMapping]:
    """加载会议映射历史"""
    if not MAPPINGS_FILE.exists():
        return []
    try:
        with open(MAPPINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [MeetingMapping.from_dict(item) for item in data]
    except Exception as e:
        logger.error(f"加载会议映射失败: {e}")
        return []


def save_mappings(mappings: list[MeetingMapping]) -> None:
    """保存会议映射历史"""
    try:
        data = [m.to_dict() for m in mappings]
        with open(MAPPINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"会议映射已保存: {len(mappings)} 条")
    except Exception as e:
        logger.error(f"保存会议映射失败: {e}")


def save_meeting_mapping(
    meeting_id: str,
    meeting_name: str,
    mapping: dict[int, str],
) -> MeetingMapping:
    """保存一次会议的映射关系"""
    mappings = load_mappings()
    # 如果已存在则更新
    for m in mappings:
        if m.meeting_id == meeting_id:
            m.mapping = mapping
            m.created_at = datetime.now().isoformat()
            save_mappings(mappings)
            return m
    # 否则新增
    new_mapping = MeetingMapping(
        meeting_id=meeting_id,
        meeting_name=meeting_name,
        mapping=mapping,
    )
    mappings.append(new_mapping)
    save_mappings(mappings)
    logger.info(f"保存会议映射: {meeting_name}, {len(mapping)} 人")
    return new_mapping


def get_latest_mapping() -> Optional[MeetingMapping]:
    """获取最近一次会议映射（用于复用建议）"""
    mappings = load_mappings()
    if not mappings:
        return None
    # 按时间倒序
    mappings.sort(key=lambda x: x.created_at, reverse=True)
    return mappings[0]


def get_mapping_by_meeting_id(meeting_id: str) -> Optional[MeetingMapping]:
    """根据会议 ID 获取映射"""
    mappings = load_mappings()
    for m in mappings:
        if m.meeting_id == meeting_id:
            return m
    return None


# ============================================================
# 姓名映射应用
# ============================================================

def apply_speaker_names(
    dialogue: list[dict],
    mapping: dict[int, str],  # speaker_id → speaker.speaker_id (UUID)
) -> list[dict]:
    """
    将 speaker_id 映射为真实姓名，应用到对话稿。

    Args:
        dialogue: 原始对话稿（speaker_id 为数字）
        mapping: 映射关系 {0: "uuid1", 1: "uuid2"}

    Returns:
        应用姓名后的对话稿（新增 speaker_name 字段）
    """
    if not dialogue:
        return dialogue

    # 获取 speaker_id → name 的映射
    name_map = get_speaker_name_map()

    result = []
    for item in dialogue:
        sid = item.get("speaker_id", 0)
        speaker_uuid = mapping.get(sid)
        speaker_name = name_map.get(speaker_uuid, f"Speaker {sid + 1}") if speaker_uuid else f"Speaker {sid + 1}"

        new_item = dict(item)
        new_item["speaker_name"] = speaker_name
        result.append(new_item)

    logger.info(f"应用姓名映射: {len(mapping)} 人")
    return result


def build_speaker_prompt(dialogue: list[dict]) -> str:
    """Build speaker name description for summary prompt.

    Returns:
        e.g. "Speaker 1 = Alice, Speaker 2 = Bob"
    """
    parts = []
    for item in dialogue:
        sid = item.get("speaker_id", 0)
        name = item.get("speaker_name", f"Speaker {sid + 1}")
        parts.append(f"Speaker {sid + 1} = {name}")
    return ", ".join(parts)
