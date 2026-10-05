"""
core/transcribe.py — 语音转写引擎（代理模式 + 直连模式）

作者：Yongliang Wang
创建：2026-09-03
版本：2.1.0（双模式）

职责：
  1. 代理模式：通过 ASR 代理提交音频文件进行转写（代理负责上传 + 提交 + 轮询 + 下载）
  2. 直连模式：用户自持 API Key，主服务直连 DashScope API（上传 + 提交 + 轮询 + 下载）
  3. 碎片句子合并 + 说话人修正 → 按 speaker_id 归并 → 组装发言人对话稿

架构：
  - 代理模式：客户端 → ASR 代理 → DashScope（详见 docs/adr/0012-ASR转写走云端代理.md）
  - 直连模式：客户端 → DashScope RESTful API（用户自持 Key）

硬约束（详见 docs/API_CONTRACTS.md §2-4）：
  - 分离仅单声道生效
  - 音频格式：PCM 16bit / 16kHz / 单声道
"""

import hashlib
import hmac
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# ── 代理配置 ──
ASR_PROXY_URL = os.getenv("ASR_PROXY_URL", "").rstrip("/")
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


def _get_asr_mode() -> str:
    """获取当前 ASR 接入模式（local / proxy / direct / cloud）。

    路由判定唯一入口为 `core/routing.get_routing_decision("asr")["route"]`，
    真相源 = 逐能力来源 capability_source.asr（trial/byok/local）。
    未设置时 route 为空串 ""（由 transcribe_audio 拦截并提示去设置）。
    """
    from core.routing import get_routing_decision
    return get_routing_decision("asr")["route"]


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
    engine_override: str | None = None,
) -> tuple[list[dict], dict]:
    """
    一站式转写：根据 ASR 模式选择本地 / 代理 / 直连 / 云端路径。

    Args:
        file_path: 本地音频文件路径
        model: 模型名
        diarization_enabled: 是否开启说话人分离
        language_hints: 语言提示（如 ["zh", "en"]）
        vocabulary_id: 热词表 ID
        speaker_count: 说话人数量提示（2-100）
        engine_override: 显式指定引擎模式（"local"/"cloud"/"proxy"/"direct"），覆盖
            _get_asr_mode() 的自动判定。**AC-4 回退专用**：本地转写失败抛
            LocalEngineError(can_fallback_cloud=True) 后，由上层在**用户显式确认**后
            以 engine_override="cloud" 重跑该任务（PRD R7：绝不静默上云）。任务音频与
            笔记状态由既有任务存储独立持久化，回退重跑不丢失（AC-4）。

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

    mode = engine_override or _get_asr_mode()
    if not mode:
        # 逐能力未设置：不静默兜底走 proxy，明示去设置（classify_error 归为 api_config）
        raise RuntimeError("ASR 转写来源未设置，请在「设置 > ASR 配置」选择算力来源")
    logger.info(f"提交转写: {file_path.name} ({file_size / 1024 / 1024:.1f} MB), model={model}, mode={mode}")

    if mode == "local":
        # R1 边界：local 模式下绝不触达任何云端转写端点（防误配），全程本机 FunASR 子进程
        return _transcribe_local(file_path, model, diarization_enabled, language_hints, vocabulary_id, speaker_count)
    elif mode == "cloud":
        return _transcribe_cloud(file_path, model, diarization_enabled, language_hints, vocabulary_id, speaker_count)
    elif mode == "direct":
        return _transcribe_direct(file_path, model, diarization_enabled, language_hints, vocabulary_id, speaker_count)
    else:
        return _transcribe_proxy(file_path, model, diarization_enabled, language_hints, vocabulary_id, speaker_count)


def _local_sentence_info_to_transcription(
    sentence_info: list[dict],
    diarization_enabled: bool = True,
) -> dict:
    """将 FunASR sentence_info 映射为 DashScope 转写结构（严格对齐 docs/API_CONTRACTS.md §4）。

    FunASR 原生字段 {start, end, spk, text}（时间单位 ms）→ 契约字段
    {begin_time, end_time, speaker_id, text, sentence_id, words[]}，使本地与
    proxy/direct/cloud 模式共用同一 assemble_dialogue 组装逻辑（R1 契约一致性）。

    diarization_enabled=False 时统一 speaker_id=0（契约：speaker_id 仅分离开启时出现）。
    words[] 本地管线不产出词级时间戳，置空列表（assemble_dialogue 对空 words 安全）。
    """
    sentences = []
    max_end = 0
    for i, s in enumerate(sentence_info):
        begin = s.get("start")
        end = s.get("end")
        if isinstance(end, (int, float)):
            max_end = max(max_end, int(end))
        sentences.append({
            "begin_time": begin,
            "end_time": end,
            "text": s.get("text", "") or "",
            "sentence_id": i,
            "speaker_id": int(s.get("spk", 0) or 0) if diarization_enabled else 0,
            "words": [],
        })

    return {
        "transcripts": [{"sentences": sentences}],
        "properties": {
            "audio_format": "wav",
            "channels": 1,
            "original_sampling_rate": 16000,
            "original_duration_in_milliseconds": max_end,
        },
    }


def _apply_local_hotword_mappings(dialogue: list[dict]) -> int:
    """R2：本地引擎热词映射（转写后替换）——必配项，非降级选项。

    复用 core/hotwords.py 的映射语义（data/hotword_mappings.txt，`错误识别→正确文本`，
    长匹配优先 + 英文词边界）。assemble_dialogue 内部已施加一次；此处对本地路径显式
    再施加一遍（幂等），使「本地必配热词」成为可见、可观测的独立步骤，并返回生效条数。

    与云端热词加权的差距（显性声明，PRD R2 / SPIKE-R8 §2.3）：
      - 云端 paraformer-v2 走 vocabulary_id **识别期加权**（热词表在解码时提升专名召回，
        从源头减少「云端科技→其他科技/吉达科技」「交付→提付」类错误）；
      - 本地 FunASR 管线**不做识别期加权**，仅能**转写后按已知映射表替换**——
        只能纠正映射表中已登记的「错误串→正确串」，对未登记的新错误无能为力，
        召回率低于云端加权。此为本地模式相对云端的已知质量差距，UI/文档需显性标注。
    """
    from core.hotwords import apply_hotword_mappings, load_hotword_mappings

    try:
        mapping_count = len(load_hotword_mappings())
    except Exception:
        mapping_count = 0
    for block in dialogue:
        block["text"] = apply_hotword_mappings(block.get("text", ""))
        for sent in block.get("sentences", []) or []:
            sent["text"] = apply_hotword_mappings(sent.get("text", ""))
    if mapping_count:
        logger.info(f"[本地热词] 转写后替换生效（映射表 {mapping_count} 条；识别期加权为云端专有，见差距声明）")
    else:
        logger.info("[本地热词] 映射表为空（data/hotword_mappings.txt）；本地无云端识别期加权，专名纠正依赖映射表")
    return mapping_count


def _transcribe_local(
    file_path: Path,
    model: str,
    diarization_enabled: bool,
    language_hints: list[str] | None,
    vocabulary_id: str | None,
    speaker_count: int | None,
) -> tuple[list[dict], dict]:
    """本地模式（R1/R2）：经引擎常驻子进程跑 FunASR 离线全管线转写。

    - 引擎选择/拉起/失败分类统一走 EngineHost.infer（失败抛 LocalEngineError，
      携带 can_fallback_cloud 供 AC-4 显式确认后回退，绝不静默上云）。
    - 实时链路在本地模式下降级为分段批处理（PRD Non-Goal，显性声明见 core/realtime_asr.py）；
      本函数即批处理链路的本地实现。
    - WP-H 超时口径：单请求超时按音频时长动态估算（estimate_local_asr_timeout，
      RTF 预算 0.5 s/s），长文件不再被固定 180s 上限整场判死；超过支持上限
      （LOCAL_ASR_MAX_SUPPORTED_SECONDS，4 小时）时报 audio_too_long 分类错误，
      不发起引擎请求，音频文件保留（失败可恢复不丢录音）。
    - 已知差距（相对云端 paraformer-v2）：
        * speaker_count 提示不强制（CAM++ 自动聚类，无法钉死人数）；
        * language_hints 不适用（seaco-paraformer-zh 为中文模型）；
        * 无词级时间戳（words[] 为空）。
    - R2 热词：本地无云端识别期 vocabulary_id 加权；热词以「转写后替换」为必配项，
      由 assemble_dialogue → apply_hotword_mappings 统一施加（详见该处文档）。
    """
    from core.engine_host import (
        ENGINE_REQUEST_TIMEOUT,
        LOCAL_ASR_MAX_SUPPORTED_SECONDS,
        _cloud_fallback_available,
        estimate_local_asr_timeout,
        get_engine_host,
    )
    from core.errors import LocalEngineError
    from core.i18n import _

    start = time.perf_counter()
    logger.info(f"本地 ASR 转写开始（FunASR 常驻子进程）: {file_path.name}")

    # WP-H：时长探测 → 动态超时；超支持上限直接分类报错（不发引擎请求，文件保留）
    timeout = float(ENGINE_REQUEST_TIMEOUT)
    try:
        from core.audio import get_audio_duration
        duration_s = get_audio_duration(file_path)
    except Exception as e:
        duration_s = None
        logger.warning(f"本地 ASR 时长探测失败（退回默认超时 {timeout:.0f}s）: {e}")
    if duration_s:
        if duration_s > LOCAL_ASR_MAX_SUPPORTED_SECONDS:
            max_h = LOCAL_ASR_MAX_SUPPORTED_SECONDS / 3600
            raise LocalEngineError(
                _(
                    "Audio duration {dur:.1f}h exceeds the local engine limit of {max:.0f}h "
                    "per file. Split the file, or switch back to cloud and retry."
                ).format(dur=duration_s / 3600, max=max_h),
                error_code="audio_too_long",
                can_fallback_cloud=_cloud_fallback_available(),
                detail={"duration_s": duration_s, "max_supported_s": LOCAL_ASR_MAX_SUPPORTED_SECONDS},
            )
        timeout = estimate_local_asr_timeout(duration_s)
        logger.info(f"本地 ASR 超时口径: 音频 {duration_s / 60:.1f}min → 单请求超时 {timeout:.0f}s")

    resp = get_engine_host().infer("asr", {"audio_path": str(file_path)}, timeout=timeout)

    sentence_info = resp.get("sentence_info", []) or []
    transcription = _local_sentence_info_to_transcription(sentence_info, diarization_enabled)
    dialogue = assemble_dialogue(transcription)

    # R2：本地热词映射（转写后替换）为必配步骤（差距声明见 _apply_local_hotword_mappings）
    _apply_local_hotword_mappings(dialogue)

    elapsed = time.perf_counter() - start
    logger.info(
        f"[PERF] 本地 ASR 转写完成: {elapsed:.1f}s, engine={resp.get('engine')}, "
        f"sentences={len(sentence_info)}, infer={resp.get('infer_seconds')}s"
    )
    return dialogue, transcription


def _transcribe_cloud(
    file_path: Path,
    model: str,
    diarization_enabled: bool,
    language_hints: list[str] | None,
    vocabulary_id: str | None,
    speaker_count: int | None,
) -> tuple[list[dict], dict]:
    """云端模式：通过云端服务器代理提交转写（桌面端无需本地 API Key）。
    Cloud mode: submit transcription via cloud server proxy (desktop client needs no local API key).
    """
    from core.cloud_client import cloud_transcribe, is_cloud_enabled

    if not is_cloud_enabled():
        raise RuntimeError("云端服务未启用，无法提交转写。请在设置中配置 API Key 或连接云端服务器。")

    # 获取当前用户 ID / Get current user ID
    user_id = ""
    try:
        from core.users import get_current_user
        user = get_current_user()
        if user:
            user_id = user.get("id", "")
    except Exception:
        pass

    start = time.perf_counter()
    logger.info(f"云端 ASR 转写开始: {file_path.name}, user={user_id[:8] if user_id else 'anon'}")

    result = cloud_transcribe(str(file_path), user_id=user_id, model=model)

    if result is None:
        raise RuntimeError(
            "云端 ASR 转写失败。请检查：\n"
            "1. 网络连接是否正常\n"
            "2. 云端服务是否可用\n"
            "3. 或在设置中配置自己的 ASR API Key"
        )

    elapsed = time.perf_counter() - start
    logger.info(f"[PERF] 云端 ASR 转写完成: {elapsed:.1f}s")

    # 提取原始转写结果 / Extract raw transcription
    raw_transcription = result.get("transcription", result)

    # 组装对话稿：云端 ASR 代理返回的是 DashScope 原始 transcription（transcripts[].sentences[]），
    # 与 proxy/direct 模式一致，需在本地调用 assemble_dialogue 解析为 dialogue；
    # 兼容：若云端将来直接返回 dialogue 字段则优先使用。
    # Assemble dialogue locally from raw transcription (consistent with proxy/direct modes);
    # prefer a cloud-provided dialogue field if present in the future.
    dialogue = result.get("dialogue") or assemble_dialogue(raw_transcription)

    # 应用热词替换（兜底：assemble_dialogue 内部已替换，此处覆盖云端直返 dialogue 的情况）
    # Apply hotword mappings (fallback: assemble_dialogue already applies; covers cloud-provided dialogue)
    try:
        from core.hotwords import apply_hotword_mappings
        for block in dialogue:
            block["text"] = apply_hotword_mappings(block.get("text", ""))
    except Exception:
        pass

    return dialogue, raw_transcription


def _transcribe_direct(
    file_path: Path,
    model: str,
    diarization_enabled: bool,
    language_hints: list[str] | None,
    vocabulary_id: str | None,
    speaker_count: int | None,
) -> tuple[list[dict], dict]:
    """直连模式：用户自持 API Key，主服务直连 DashScope API"""
    from app.store import get_asr_config
    cfg = get_asr_config()
    api_key = cfg.get("api_key", "")
    base_url = cfg.get("base_url", "https://dashscope.aliyuncs.com").rstrip("/")

    if not api_key:
        raise RuntimeError("未配置 ASR API Key，请在设置页面配置语音转写服务或通过 .env 配置 DASHSCOPE_API_KEY")

    start = time.perf_counter()

    # 1. 上传到 DashScope 临时存储
    from core.upload import upload_file
    oss_url = upload_file(file_path, model=model)

    # 2. 提交转写任务
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
        "X-DashScope-OssResourceResolve": "enable",
    }
    parameters = {}
    if diarization_enabled:
        parameters["diarization_enabled"] = True
    if language_hints:
        parameters["language_hints"] = language_hints
    if speaker_count:
        parameters["speaker_count"] = speaker_count
    if vocabulary_id:
        parameters["vocabulary_id"] = vocabulary_id

    body = {
        "model": model,
        "input": {"file_urls": [oss_url]},
        "parameters": parameters,
    }

    submit_url = f"{base_url}/api/v1/services/audio/asr/transcription"
    resp = requests.post(submit_url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    submit_data = resp.json()

    if "output" not in submit_data or "task_id" not in submit_data["output"]:
        raise RuntimeError(f"提交转写任务失败: {submit_data}")
    task_id = submit_data["output"]["task_id"]
    logger.info(f"[直连模式] 任务已提交: task_id={task_id}")

    # 3. 轮询任务状态
    poll_url = f"{base_url}/api/v1/tasks/{task_id}"
    poll_headers = {"Authorization": f"Bearer {api_key}"}
    poll_interval = 3
    poll_timeout = 600
    start_poll = time.time()

    while True:
        if time.time() - start_poll > poll_timeout:
            raise TimeoutError(f"转写任务超时（>{poll_timeout}s）: task_id={task_id}")

        poll_resp = requests.get(poll_url, headers=poll_headers, timeout=30)
        poll_resp.raise_for_status()
        poll_data = poll_resp.json()
        status = poll_data.get("output", {}).get("task_status", "UNKNOWN")

        if status == "SUCCEEDED":
            results = poll_data["output"].get("results", [])
            if not results:
                raise RuntimeError("转写结果为空")
            transcription_url = results[0].get("transcription_url")
            if not transcription_url:
                raise RuntimeError("未获取到 transcription_url")
            break
        elif status == "FAILED":
            error_msg = poll_data.get("output", {}).get("message", "未知错误")
            raise RuntimeError(f"转写任务失败: {error_msg}")

        time.sleep(poll_interval)

    # 4. 下载转写结果
    dl_resp = requests.get(transcription_url, timeout=60)
    dl_resp.raise_for_status()
    transcription = dl_resp.json()

    elapsed = time.perf_counter() - start
    logger.info(f"[PERF] 直连转写完成: {elapsed:.3f}s, task_id={task_id}")

    dialogue = assemble_dialogue(transcription)
    return dialogue, transcription


def _transcribe_proxy(
    file_path: Path,
    model: str,
    diarization_enabled: bool,
    language_hints: list[str] | None,
    vocabulary_id: str | None,
    speaker_count: int | None,
) -> tuple[list[dict], dict]:
    """代理模式：通过 ASR 代理提交转写"""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    file_size = file_path.stat().st_size
    if file_size > 1024 * 1024 * 1024:
        raise RuntimeError(f"文件过大: {file_size / 1024 / 1024:.0f}MB > 1GB 上限")

    logger.info(f"提交转写（代理模式）: {file_path.name} ({file_size / 1024 / 1024:.1f} MB), model={model}")

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
