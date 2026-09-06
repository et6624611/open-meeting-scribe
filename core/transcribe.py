"""
core/transcribe.py — 提交 paraformer-v2 转写任务 + 轮询 + 下载结果 + 组装对话稿

职责：
  1. 提交异步转写任务（开说话人分离）
  2. 轮询任务状态直到 SUCCEEDED
  3. 下载转写结果 JSON
  4. 碎片句子合并 + 说话人修正 → 按 speaker_id 归并 → 组装发言人对话稿

硬约束（详见 docs/API_CONTRACTS.md §2-4）：
  - oss:// URL 必须走 RESTful API + X-DashScope-OssResourceResolve: enable
  - 必须带 X-DashScope-Async: enable
  - 分离仅单声道生效
"""

import os
import re
import time
import json
import logging
import requests
from pathlib import Path

logger = logging.getLogger(__name__)

DASHSCOPE_BASE = "https://dashscope.aliyuncs.com"

# 轮询配置
POLL_INTERVAL = 3  # 秒
POLL_TIMEOUT = 600  # 10 分钟超时

# ── 碎片合并参数 ──
# 时间间隔阈值（毫秒）：相邻两句间隔小于此值时考虑合并
MERGE_GAP_MS = 2000
# 短句阈值：去标点后字符数低于此值视为碎片
FRAGMENT_CHARS = 12
# 说话人修正：夹心修正的最大间隔（毫秒）
# 仅当前后同说话人两句的间隔都小于此值时才修正（避免误合并真正的说话人切换）
SPEAKER_FIX_GAP_MS = 800
# 说话人修正：碎片短句跟随前句的最大间隔（毫秒）
# 比夹心修正更严格，避免交替短答时被错误合并
FRAGMENT_SPEAKER_FIX_GAP_MS = 500
# 中文句末标点
SENTENCE_END_PUNCTS = set("。！？…")
# 中文句中停顿标点（不算完整断句）
CLAUSE_PUNCTS = set("，、；：")
# 常见双字词（用于检测跨句拆词）
COMMON_BIGRAMS = {
    "智能", "企业", "客户", "服务", "系统", "数据", "分析", "报告",
    "预算", "财务", "管理", "流程", "优化", "方案", "技术", "平台",
    "产品", "项目", "需求", "功能", "模块", "接口", "部署", "开发",
    "测试", "上线", "运行", "维护", "安全", "性能", "效率", "成本",
    "定位", "转出", "营销", "文案", "客服", "人力", "资源", "配置",
    "设计", "实现", "支持", "提供", "使用", "操作", "控制", "处理",
}


def _get_api_key() -> str:
    from app.store import get_asr_config
    key = get_asr_config()["api_key"]
    if not key:
        raise RuntimeError("未设置 ASR API Key，请在设置页面配置语音转写服务或通过 .env 配置 DASHSCOPE_API_KEY")
    return key


def submit_transcription(
    file_url: str,
    model: str = "paraformer-v2",
    diarization_enabled: bool = True,
    language_hints: list[str] | None = None,
    speaker_count: int | None = None,
    vocabulary_id: str | None = None,
    disfluency_removal_enabled: bool = False,
) -> str:
    """
    提交转写任务。

    Args:
        file_url: 音频 URL（oss:// 或公网 URL）
        model: 模型名
        diarization_enabled: 是否开启说话人分离
        language_hints: 语言提示（如 ["zh", "en"]）
        speaker_count: 说话人数量（2-100，可选，仅辅助）
        vocabulary_id: 热词表 ID
        disfluency_removal_enabled: 是否过滤语气词

    Returns:
        task_id
    """
    api_key = _get_api_key()
    url = f"{DASHSCOPE_BASE}/api/v1/services/audio/asr/transcription"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",  # 必带，否则无法提交
    }

    # oss:// URL 需要加此 header
    if file_url.startswith("oss://"):
        headers["X-DashScope-OssResourceResolve"] = "enable"

    # 构造参数
    parameters = {}
    if diarization_enabled:
        parameters["diarization_enabled"] = True
    if language_hints:
        parameters["language_hints"] = language_hints
    if speaker_count:
        parameters["speaker_count"] = speaker_count
    if vocabulary_id:
        parameters["vocabulary_id"] = vocabulary_id
    if disfluency_removal_enabled:
        parameters["disfluency_removal_enabled"] = True

    body = {
        "model": model,
        "input": {
            "file_urls": [file_url],  # 单次仅 1 个 URL
        },
        "parameters": parameters,
    }

    logger.info(f"提交转写任务: model={model}, url={file_url[:50]}..., "
                f"分离={diarization_enabled}")

    resp = requests.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    if "output" not in data or "task_id" not in data["output"]:
        raise RuntimeError(f"提交任务失败: {data}")

    task_id = data["output"]["task_id"]
    logger.info(f"任务已提交: task_id={task_id}")
    return task_id


def poll_task(task_id: str, interval: int = POLL_INTERVAL, timeout: int = POLL_TIMEOUT) -> dict:
    """
    轮询任务状态直到完成。

    Returns:
        任务结果 dict（含 transcription_url 等）

    Raises:
        TimeoutError: 超时
        RuntimeError: 任务失败
    """
    api_key = _get_api_key()
    url = f"{DASHSCOPE_BASE}/api/v1/tasks/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    start_time = time.time()
    last_status = ""

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise TimeoutError(f"任务超时（>{timeout}s）: task_id={task_id}")

        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        output = data.get("output", {})
        status = output.get("task_status", "UNKNOWN")

        # 状态变化时打印日志
        if status != last_status:
            logger.info(f"任务状态: {status} ({elapsed:.0f}s)")
            last_status = status

        if status == "SUCCEEDED":
            return output
        elif status == "FAILED":
            error_msg = output.get("message", "未知错误")
            if "SUCCESS_WITH_NO_VALID_FRAGMENT" in error_msg:
                raise RuntimeError(f"转写任务失败: 未检测到有效语音片段 (SUCCESS_WITH_NO_VALID_FRAGMENT)")
            raise RuntimeError(f"转写任务失败: {error_msg}")

        time.sleep(interval)


def download_transcription(transcription_url: str) -> dict:
    """
    下载转写结果 JSON。

    transcription_url 有效期 24h。
    """
    logger.info(f"下载转写结果: {transcription_url[:80]}...")
    resp = requests.get(transcription_url, timeout=60)
    resp.raise_for_status()
    return resp.json()


from .hotwords import apply_hotword_mappings


def _sentence_ends_complete(text: str) -> bool:
    """判断句子是否以完整句末标点结尾（而非被截断）"""
    if not text:
        return False
    last_char = text[-1]
    return last_char in SENTENCE_END_PUNCTS


def _is_fragment(text: str) -> bool:
    """判断是否为碎片短句（去标点后字符数过少）"""
    stripped = re.sub(r"[，。！？、；：…？！\s]", "", text)
    return len(stripped) < FRAGMENT_CHARS


def _detect_word_split(curr_text: str, next_text: str) -> bool:
    """
    检测跨句拆词：当前句末字 + 下句首字是否构成常见双字词。
    这是 ASR 在词中间误切分的强信号。
    """
    if not curr_text or not next_text:
        return False
    # 去掉当前句末标点后取最后一个字
    last_char = curr_text.rstrip("，。！？、；：…？！")[-1:] if curr_text else ""
    first_char = next_text.lstrip("，。！？、；：…？！")[:1] if next_text else ""
    if not last_char or not first_char:
        return False
    return (last_char + first_char) in COMMON_BIGRAMS


def merge_fragments(sentences: list[dict]) -> list[dict]:
    """
    合并碎片化句子。

    合并条件（满足任一即合并）：
    1. 跨句拆词：当前句末字 + 下句首字构成常见双字词（如"智"+"能"）
    2. 当前句为碎片（去标点 < FRAGMENT_CHARS 字符）
    3. 当前句不以句末标点结尾（明显被截断）

    停止条件：
    - 时间间隔 > MERGE_GAP_MS
    - 当前句完整（有句末标点 + 非碎片长度）且无拆词信号

    Returns:
        合并后的句子列表（结构同输入 sentences）
    """
    if not sentences:
        return []

    merged: list[dict] = []
    i = 0

    while i < len(sentences):
        current = dict(sentences[i])  # 浅拷贝，避免修改原始数据
        current_text = current.get("text", "")
        current_begin = current.get("begin_time", 0)
        current_end = current.get("end_time", 0)
        current_words = list(current.get("words", []))
        current_sid = current.get("sentence_id", 0)

        # 尝试向后合并
        j = i + 1
        while j < len(sentences):
            next_sent = sentences[j]
            next_text = next_sent.get("text", "")
            next_begin = next_sent.get("begin_time", 0)
            gap = next_begin - current_end

            # 硬约束：时间间隔过大，停止合并
            if gap > MERGE_GAP_MS:
                break

            # 判断是否应该合并
            should_merge = False

            # 信号1：跨句拆词（最强信号，无视其他条件）
            if _detect_word_split(current_text, next_text):
                should_merge = True

            # 信号2：当前句是碎片（过短）
            elif _is_fragment(current_text):
                should_merge = True

            # 信号3：当前句无句末标点（明显被截断）
            elif not _sentence_ends_complete(current_text):
                should_merge = True

            if not should_merge:
                break

            # 拼接文本，处理连接标点
            connector = ""
            if current_text and next_text:
                last_c = current_text[-1]
                # 前句无句末/句中标点时，用逗号连接
                if last_c not in SENTENCE_END_PUNCTS and last_c not in CLAUSE_PUNCTS:
                    connector = "，"

            current_text = current_text + connector + next_text
            current_end = next_sent.get("end_time", current_end)
            current_words.extend(next_sent.get("words", []))
            j += 1

        current["text"] = current_text
        current["begin_time"] = current_begin
        current["end_time"] = current_end
        current["words"] = current_words
        current["sentence_id"] = current_sid
        merged.append(current)
        i = j

    logger.info(f"碎片合并: {len(sentences)} → {len(merged)} 句")
    return merged


def correct_speaker_ids(sentences: list[dict]) -> list[dict]:
    """
    修正说话人分离过度切分。

    策略：
    1. 夹心修正：如果一句被前后相同 speaker_id 包围，且时间间隔小，
       修正为同一说话人（ASR 短暂误判场景）
    2. 连续短句统一：相邻碎片短句如果说话人不同，
       且时间间隔很小，归入前句的说话人

    Returns:
        修正后的句子列表（原地修改 speaker_id）
    """
    if len(sentences) < 3:
        return sentences

    fix_count = 0

    # 第一遍：夹心修正（A-B-A 模式 → 全部归为 A）
    for i in range(1, len(sentences) - 1):
        prev_sid = sentences[i - 1].get("speaker_id", 0)
        curr_sid = sentences[i].get("speaker_id", 0)
        next_sid = sentences[i + 1].get("speaker_id", 0)

        if prev_sid == next_sid and prev_sid != curr_sid:
            gap_before = sentences[i].get("begin_time", 0) - sentences[i - 1].get("end_time", 0)
            gap_after = sentences[i + 1].get("begin_time", 0) - sentences[i].get("end_time", 0)

            if gap_before < SPEAKER_FIX_GAP_MS and gap_after < SPEAKER_FIX_GAP_MS:
                sentences[i]["speaker_id"] = prev_sid
                fix_count += 1

    # 第二遍：碎片短句跟随前句说话人（使用更严格的间隔阈值）
    for i in range(1, len(sentences)):
        curr_text = sentences[i].get("text", "")
        curr_sid = sentences[i].get("speaker_id", 0)
        prev_sid = sentences[i - 1].get("speaker_id", 0)

        if curr_sid != prev_sid and _is_fragment(curr_text):
            gap = sentences[i].get("begin_time", 0) - sentences[i - 1].get("end_time", 0)
            if gap < FRAGMENT_SPEAKER_FIX_GAP_MS:
                sentences[i]["speaker_id"] = prev_sid
                fix_count += 1

    logger.info(f"说话人修正: 修正了 {fix_count} 句")
    return sentences


def assemble_dialogue(transcription: dict) -> list[dict]:
    """
    碎片合并 → 说话人修正 → 按 speaker_id 归并句子，组装发言人对话稿。

    Returns:
        [
            {"speaker_id": 0, "text": "说话人0的完整文本", "sentences": [...]},
            {"speaker_id": 1, "text": "说话人1的完整文本", "sentences": [...]},
            ...
        ]
    """
    transcripts = transcription.get("transcripts", [])
    if not transcripts:
        logger.warning("转写结果为空")
        return []

    # 收集所有句子（多 transcript 时合并）
    all_sentences = []
    for t in transcripts:
        sentences = t.get("sentences", [])
        all_sentences.extend(sentences)

    if not all_sentences:
        logger.warning("无句子数据")
        return []

    # 后处理管线：碎片合并 → 说话人修正 → 热词映射纠正
    merged = merge_fragments(all_sentences)
    corrected = correct_speaker_ids(merged)

    # 热词映射：纠正 ASR 识别结果（如 ES→EAS系统）
    for sent in corrected:
        sent["text"] = apply_hotword_mappings(sent["text"])

    # 按说话人轮次归并（连续同说话人合并，换人时开新条目）
    result: list[dict] = []
    for sent in corrected:
        sid = sent.get("speaker_id", 0)
        if result and result[-1]["speaker_id"] == sid:
            # 同一说话人连续发言，追加到上一条
            result[-1]["sentences"].append(sent)
            result[-1]["text"] += sent.get("text", "")
        else:
            # 换人或首条，新建条目
            result.append({"speaker_id": sid, "text": sent.get("text", ""), "sentences": [sent]})

    logger.info(f"组装对话稿: {len(result)} 条对话（{len(set(s.get('speaker_id', 0) for s in corrected))} 位说话人, "
                f"共 {len(corrected)} 句合并后）")
    return result


def transcribe_audio(
    file_url: str,
    model: str = "paraformer-v2",
    diarization_enabled: bool = True,
    language_hints: list[str] | None = None,
    vocabulary_id: str | None = None,
    speaker_count: int | None = None,
) -> tuple[list[dict], dict]:
    """
    一站式转写：提交 → 轮询 → 下载 → 组装。

    Args:
        speaker_count: 说话人数量提示（2-100），来自实时声纹聚类估算

    Returns:
        (dialogue, raw_transcription)
        dialogue: 组装后的对话稿
        raw_transcription: 原始转写结果 JSON
    """
    task_id = submit_transcription(
        file_url=file_url,
        model=model,
        diarization_enabled=diarization_enabled,
        language_hints=language_hints,
        vocabulary_id=vocabulary_id,
        speaker_count=speaker_count,
    )

    output = poll_task(task_id)
    results = output.get("results", [])
    if not results:
        raise RuntimeError("转写结果为空")

    transcription_url = results[0].get("transcription_url")
    if not transcription_url:
        raise RuntimeError("未获取到 transcription_url")

    transcription = download_transcription(transcription_url)
    dialogue = assemble_dialogue(transcription)

    return dialogue, transcription
