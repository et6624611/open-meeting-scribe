"""说话人发言时长统计 / Speaker talk-time aggregation.

列表轻量视图（view=list）不携带 dialogue，卡片/会议库的说话人占比改由后端下发
speaker_share（按 speaker_id 累计秒数）；只放内存缓存，不落盘。
The `view=list` payload drops dialogue, so speaker percentages are computed here and
cached in memory (never persisted).
"""

_CACHE: dict[str, tuple[tuple, dict[str, float]]] = {}


def compute_speaker_share(dialogue: list) -> dict[str, float]:
    """按 block 级 speaker_id 累计发言秒数（含占位/未识别 speaker）。

    句级 begin_time / end_time 为毫秒，此处统一换算成秒，与前端 formatDuration 口径一致。
    """
    share: dict[str, float] = {}
    for block in dialogue or []:
        if not isinstance(block, dict):
            continue
        sid = block.get("speaker_id")
        if sid is None:
            continue
        key = str(sid)
        total = 0.0
        for sentence in block.get("sentences") or []:
            if not isinstance(sentence, dict):
                continue
            begin = sentence.get("begin_time")
            end = sentence.get("end_time")
            if begin is None or end is None:
                continue
            total += (float(end) - float(begin)) / 1000.0
        share[key] = share.get(key, 0.0) + total
    return {sid: round(sec, 2) for sid, sec in share.items()}


def _fingerprint(dialogue: list) -> tuple:
    """缓存指纹：块数 + 末块末句结束时间（转写被整体替换时会变化）。"""
    if not dialogue:
        return (0, None)
    last = dialogue[-1]
    last_end = None
    if isinstance(last, dict):
        sentences = last.get("sentences") or []
        if sentences and isinstance(sentences[-1], dict):
            last_end = sentences[-1].get("end_time")
    return (len(dialogue), last_end)


def get_speaker_share(task: dict) -> dict[str, float]:
    """读取（或计算并缓存）一个任务的 speaker_share。"""
    task_id = task.get("task_id") or ""
    dialogue = task.get("dialogue") or []
    fingerprint = _fingerprint(dialogue)
    cached = _CACHE.get(task_id)
    if cached and cached[0] == fingerprint:
        return cached[1]
    share = compute_speaker_share(dialogue)
    if task_id:
        _CACHE[task_id] = (fingerprint, share)
    return share
