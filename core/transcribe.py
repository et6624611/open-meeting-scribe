"""
core/transcribe.py — 通过 ASR 代理提交转写任务 + 组装对话稿

作者：王永亮
创建：2026-09-03
版本：2.0.0（代理模式）

职责：
  1. 通过 ASR 代理提交音频文件进行转写（代理负责上传 + 提交 + 轮询 + 下载）
  2. 碎片句子合并 + 说话人修正 → 按 speaker_id 归并 → 组装发言人对话稿

架构（详见 docs/adr/0012-ASR转写走云端代理.md）：
  - 客户端不再直连 DashScope，所有 ASR 请求通过代理服务器中转
  - 代理持有 DashScope API Key，客户端仅持有代理地址和共享密钥
  - 通信协议：HTTP POST + HMAC-SHA256 签名

硬约束（详见 docs/API_CONTRACTS.md §2-4）：
  - 分离仅单声道生效
  - 音频格式：PCM 16bit / 16kHz / 单声道
"""

import os
import re
import json
import time
import hmac
import hashlib
import logging
import urllib.request
import urllib.error
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 代理配置 ──
ASR_PROXY_URL = os.getenv("ASR_PROXY_URL", "http://47.116.10.194:8200").rstrip("/")
ASR_PROXY_TOKEN = os.getenv("ASR_PROXY_TOKEN", "")
ASR_SIGN_TTL = 300

# ── 碎片合并参数 ──
MERGE_GAP_MS = 2000
FRAGMENT_CHARS = 12
SPEAKER_FIX_GAP_MS = 800
FRAGMENT_SPEAKER_FIX_GAP_MS = 500
SENTENCE_END_PUNCTS = set("。！？…")
CLAUSE_PUNCTS = set("，、；：")
COMMON_BIGRAMS = {
    "智能", "企业", "客户", "服务", "系统", "数据", "分析", "报告",
    "预算", "财务", "管理", "流程", "优化", "方案", "技术", "平台",
    "产品", "项目", "需求", "功能", "模块", "接口", "部署", "开发",
    "测试", "上线", "运行", "维护", "安全", "性能", "效率", "成本",
    "定位", "转出", "营销", "文案", "客服", "人力", "资源", "配置",
    "设计", "实现", "支持", "提供", "使用", "操作", "控制", "处理",
}


def _make_sign(timestamp: str) -> str:
    """生成请求签名：HMAC-SHA256(token, timestamp)"""
    if not ASR_PROXY_TOKEN:
        raise RuntimeError("未配置 ASR_PROXY_TOKEN，无法调用 ASR 代理")
    return hmac.new(
        ASR_PROXY_TOKEN.encode(),
        timestamp.encode(),
        hashlib.sha256,
    ).hexdigest()


def _proxy_request(path: str, data: bytes, content_type: str, timeout: int = 600) -> dict:
    """
    向 ASR 代理发送 POST 请求。

    Args:
        path: 代理端点路径
        data: 请求体
        content_type: Content-Type
        timeout: 超时时间（秒）

    Returns:
        代理返回的 JSON dict
    """
    url = f"{ASR_PROXY_URL}{path}"
    timestamp = str(int(time.time()))
    sign = _make_sign(timestamp)

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": content_type,
            "X-ASR-Timestamp": timestamp,
            "X-ASR-Sign": sign,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode())
            # FastAPI HTTPException 默认字段名为 "detail"，兼容 "message"
            msg = err_body.get("detail") or err_body.get("message") or str(e)
        except Exception:
            msg = f"HTTP {e.code}"
        logger.error(f"ASR 代理请求失败: {path} → {msg}")
        raise RuntimeError(f"ASR 代理返回错误: {msg}")
    except urllib.error.URLError as e:
        logger.error(f"ASR 代理连接失败: {path} → {e.reason}")
        raise RuntimeError(f"ASR 代理连接失败: {e.reason}")
    except Exception as e:
        logger.error(f"ASR 代理请求异常: {path} → {e}")
        raise RuntimeError(f"ASR 服务异常: {e}")


def transcribe_audio(
    file_path: str | Path,
    model: str = "paraformer-v2",
    diarization_enabled: bool = True,
    language_hints: list[str] | None = None,
    vocabulary_id: str | None = None,
    speaker_count: int | None = None,
) -> tuple[list[dict], dict]:
    """
    一站式转写：通过代理提交音频 → 等待结果 → 组装对话稿。

    Args:
        file_path: 本地音频文件路径
        model: 模型名
        diarization_enabled: 是否开启说话人分离
        language_hints: 语言提示（如 ["zh", "en"]）
        vocabulary_id: 热词表 ID
        speaker_count: 说话人数量提示（2-100）

    Returns:
        (dialogue, raw_transcription)
        dialogue: 组装后的对话稿
        raw_transcription: 原始转写结果 JSON
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    file_size = file_path.stat().st_size
    if file_size > 1024 * 1024 * 1024:
        raise RuntimeError(f"文件过大: {file_size / 1024 / 1024:.0f}MB > 1GB 上限")

    logger.info(f"提交转写: {file_path.name} ({file_size / 1024 / 1024:.1f} MB), model={model}")

    # 构造 multipart/form-data
    boundary = f"----ASRProxyBoundary{int(time.time() * 1000)}"
    body_parts = []

    # file 字段
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode())
    body_parts.append(b"Content-Type: application/octet-stream\r\n\r\n")
    with open(file_path, "rb") as f:
        body_parts.append(f.read())
    body_parts.append(b"\r\n")

    # model 字段
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(b'Content-Disposition: form-data; name="model"\r\n\r\n')
    body_parts.append(f"{model}\r\n".encode())

    # diarization_enabled 字段
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(b'Content-Disposition: form-data; name="diarization_enabled"\r\n\r\n')
    body_parts.append(f"{'true' if diarization_enabled else 'false'}\r\n".encode())

    # 可选字段
    if language_hints:
        body_parts.append(f"--{boundary}\r\n".encode())
        body_parts.append(b'Content-Disposition: form-data; name="language_hints"\r\n\r\n')
        body_parts.append(f"{json.dumps(language_hints)}\r\n".encode())

    if speaker_count:
        body_parts.append(f"--{boundary}\r\n".encode())
        body_parts.append(b'Content-Disposition: form-data; name="speaker_count"\r\n\r\n')
        body_parts.append(f"{speaker_count}\r\n".encode())

    if vocabulary_id:
        body_parts.append(f"--{boundary}\r\n".encode())
        body_parts.append(b'Content-Disposition: form-data; name="vocabulary_id"\r\n\r\n')
        body_parts.append(f"{vocabulary_id}\r\n".encode())

    body_parts.append(f"--{boundary}--\r\n".encode())

    body = b"".join(body_parts)
    content_type = f"multipart/form-data; boundary={boundary}"

    # 调用代理（长时间超时，因为代理内部轮询）
    start = time.perf_counter()
    result = _proxy_request("/asr/transcribe", body, content_type, timeout=600)
    elapsed = time.perf_counter() - start

    task_id = result.get("task_id", "")
    transcription = result.get("transcription", {})

    if not transcription:
        raise RuntimeError("转写结果为空")

    logger.info(f"[PERF] 转写完成: {elapsed:.3f}s, task_id={task_id}")

    dialogue = assemble_dialogue(transcription)
    return dialogue, transcription


def _sentence_ends_complete(text: str) -> bool:
    """判断句子是否以完整句末标点结尾"""
    if not text:
        return False
    return text[-1] in SENTENCE_END_PUNCTS


def _is_fragment(text: str) -> bool:
    """判断是否为碎片短句"""
    stripped = re.sub(r"[，。！？、；：…？！\s]", "", text)
    return len(stripped) < FRAGMENT_CHARS


def _detect_word_split(curr_text: str, next_text: str) -> bool:
    """检测跨句拆词"""
    if not curr_text or not next_text:
        return False
    last_char = curr_text.rstrip("，。！？、；：…？！")[-1:] if curr_text else ""
    first_char = next_text.lstrip("，。！？、；：…？！")[:1] if next_text else ""
    if not last_char or not first_char:
        return False
    return (last_char + first_char) in COMMON_BIGRAMS


def merge_fragments(sentences: list[dict]) -> list[dict]:
    """合并碎片化句子"""
    if not sentences:
        return []

    merged: list[dict] = []
    i = 0

    while i < len(sentences):
        current = dict(sentences[i])
        current_text = current.get("text", "")
        current_begin = current.get("begin_time", 0)
        current_end = current.get("end_time", 0)
        current_words = list(current.get("words", []))
        current_sid = current.get("sentence_id", 0)

        j = i + 1
        while j < len(sentences):
            next_sent = sentences[j]
            next_text = next_sent.get("text", "")
            next_begin = next_sent.get("begin_time", 0)
            gap = next_begin - current_end

            if gap > MERGE_GAP_MS:
                break

            should_merge = False
            if _detect_word_split(current_text, next_text):
                should_merge = True
            elif _is_fragment(current_text):
                should_merge = True
            elif not _sentence_ends_complete(current_text):
                should_merge = True

            if not should_merge:
                break

            connector = ""
            if current_text and next_text:
                last_c = current_text[-1]
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
    """修正说话人分离过度切分"""
    if len(sentences) < 3:
        return sentences

    fix_count = 0

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


from .hotwords import apply_hotword_mappings


def assemble_dialogue(transcription: dict) -> list[dict]:
    """碎片合并 → 说话人修正 → 按 speaker_id 归并句子，组装发言人对话稿"""
    transcripts = transcription.get("transcripts", [])
    if not transcripts:
        logger.warning("转写结果为空")
        return []

    all_sentences = []
    for t in transcripts:
        sentences = t.get("sentences", [])
        all_sentences.extend(sentences)

    if not all_sentences:
        logger.warning("无句子数据")
        return []

    merged = merge_fragments(all_sentences)
    corrected = correct_speaker_ids(merged)

    for sent in corrected:
        sent["text"] = apply_hotword_mappings(sent["text"])

    result: list[dict] = []
    for sent in corrected:
        sid = sent.get("speaker_id", 0)
        if result and result[-1]["speaker_id"] == sid:
            result[-1]["sentences"].append(sent)
            result[-1]["text"] += sent.get("text", "")
        else:
            result.append({"speaker_id": sid, "text": sent.get("text", ""), "sentences": [sent]})

    logger.info(f"组装对话稿: {len(result)} 条对话（{len(set(s.get('speaker_id', 0) for s in corrected))} 位说话人, "
                f"共 {len(corrected)} 句合并后）")
    return result
