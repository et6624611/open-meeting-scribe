"""
core/engine_worker.py — 本地引擎常驻子进程工作端（R5 / WP-B）

架构约束（Spike §3.2）：
  1. 冻结态 funasr 冷 import 最高 86s —— 引擎必须以常驻子进程运行（启动一次复用），
     禁止每任务冷启动；进程生命周期由 core.engine_host.EngineHost 管理。
  2. 多进程必须 `if __name__ == "__main__"` 保护 + 显式 multiprocessing.freeze_support()，
     防止冻结包被子进程重复引导（Spike 观察到 import 重复 5–6 次）。

协议：stdin/stdout JSON Lines（每行一个 JSON 对象）。
  请求:  {"id": <any>, "cmd": "ping" | "verify_models" | "infer" | "stop", ...}
  响应:  {"id": <any>, "ok": true/false, ...}

推理命令（cmd="infer"）由主干 R1/R2/R3（WP-E）接入 FunASR 离线管线：
  - params.task="asr"       → seaco-paraformer + fsmn-vad + ct-punc(可选) + cam++ 分离，
                              回传 sentence_info（时间戳/说话人/文本）+ 全文；
  - params.task="embedding" → cam++ 声纹 192 维嵌入（R3，与说话人分离共用同一份权重）。
FunASR AutoModel 进程内惰性加载并缓存为单例（常驻复用，禁每请求冷启动）。

重依赖（funasr/torch）必须只在子进程内、且按需惰性 import，
保证云端精简包（无 torch）下本模块可被安全引用。
"""

import json
import logging
import multiprocessing
import os
import sys
import time

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1

# ── FunASR 模型进程内单例（常驻复用，R5 约束①：禁每任务冷启动）──
# Resident in-process FunASR model singletons (reuse across requests; never cold-start per task)
_ASR_MODEL = None
_SPK_MODEL = None


def _reply(out, req_id, ok: bool, **payload):
    payload.update({"id": req_id, "ok": ok, "protocol": PROTOCOL_VERSION})
    out.write(json.dumps(payload, ensure_ascii=False) + "\n")
    out.flush()


def _handle_verify_models():
    """校验全部已安装模型完整性（篡改拒载入口）。"""
    from core.model_downloader import verify_model
    from core.model_registry import MODEL_BY_KEY

    results = {}
    for key in MODEL_BY_KEY:
        results[key] = verify_model(key)
    tampered = [k for k, v in results.items() if v["status"] == "tampered"]
    return {
        "models": results,
        "tampered": tampered,
        "all_clean": not tampered,
    }


def _get_asr_model():
    """惰性加载并缓存 ASR 全管线模型（seaco-paraformer + fsmn-vad + cam++ 分离，标点可选）。

    ct-punc（1.0GB）为唯一可裁剪大件（model_registry optional=True）：仅当本地权重
    已存在时挂入 punc_model，避免离线态触发 ModelScope 下载（PRD R5「不内置分发」）。
    模型 ID 统一取自 core.model_registry，与下载器/完整性校验同源。
    """
    global _ASR_MODEL
    if _ASR_MODEL is not None:
        return _ASR_MODEL

    from funasr import AutoModel

    from core.model_registry import MODEL_BY_KEY, get_model_root

    models = {
        "model": MODEL_BY_KEY["seaco-paraformer-zh"]["modelscope_id"],
        "vad_model": MODEL_BY_KEY["fsmn-vad"]["modelscope_id"],
        "spk_model": MODEL_BY_KEY["cam-plus"]["modelscope_id"],
    }
    # 标点可选：本地权重存在才挂入（省 1.0GB 的裁剪档不带标点）
    if get_model_root("ct-punc").exists():
        models["punc_model"] = MODEL_BY_KEY["ct-punc"]["modelscope_id"]

    logger.info(f"[引擎] 加载 ASR 管线: {sorted(models.keys())}")
    _ASR_MODEL = AutoModel(**models, disable_update=True, disable_pbar=True, log_level="ERROR")
    _ASR_MODEL._oms_model_ids = models  # 观测：记录实际挂载的模型 ID（PRD §9 任务日志）
    return _ASR_MODEL


def _get_spk_model():
    """惰性加载并缓存 CAM++ 声纹模型（R3，与说话人分离共用同一份权重）。"""
    global _SPK_MODEL
    if _SPK_MODEL is not None:
        return _SPK_MODEL

    from funasr import AutoModel

    from core.model_registry import MODEL_BY_KEY

    model_id = MODEL_BY_KEY["cam-plus"]["modelscope_id"]
    logger.info(f"[引擎] 加载 CAM++ 声纹模型: {model_id}")
    _SPK_MODEL = AutoModel(model=model_id, disable_update=True, disable_pbar=True, log_level="ERROR")
    return _SPK_MODEL


def _infer_asr(params: dict) -> dict:
    """R1/R2：FunASR 离线全管线转写（含 VAD/标点/说话人分离）。

    输入 params: {"audio_path": str, "batch_size_s"?: int, "hotwords"?: str}
    输出（成功）: {"ok": True, "task": "asr", "text": str,
                  "sentence_info": [{"start","end","spk","text"}, ...],  # ms，FunASR 原生字段
                  "models": {...}, "infer_seconds": float}
    sentence_info → API_CONTRACTS 转写结构的映射在调用方（core/transcribe.py）完成。
    """
    audio_path = params.get("audio_path") or params.get("input")
    if not audio_path:
        return {"ok": False, "error_code": "bad_request", "error": "缺少 audio_path"}
    if not os.path.exists(audio_path):
        return {"ok": False, "error_code": "audio_not_found", "error": f"音频文件不存在: {audio_path}"}

    model = _get_asr_model()
    gen_kwargs = {
        "input": str(audio_path),
        "batch_size_s": int(params.get("batch_size_s", 300)),
        "merge_vad": True,
        "merge_length_s": int(params.get("merge_length_s", 15)),
    }
    # seaco-paraformer 为语义增强上下文模型，支持原生热词；此处仅在调用方显式传入时透传，
    # 与 R2「转写后替换为必配项」并存（差距说明见 core/transcribe.py 本地路径文档）。
    hotwords = params.get("hotwords")
    if hotwords:
        gen_kwargs["hotword"] = hotwords

    t0 = time.time()
    res = model.generate(**gen_kwargs)
    infer_seconds = round(time.time() - t0, 2)

    payload = res[0] if isinstance(res, (list, tuple)) and res else (res or {})
    sentence_info = payload.get("sentence_info", []) or []
    return {
        "ok": True,
        "task": "asr",
        "engine": "local-funasr",
        "text": payload.get("text", "") or "",
        "sentence_info": [
            {
                "start": s.get("start"),
                "end": s.get("end"),
                "spk": s.get("spk", 0),
                "text": s.get("text", "") or "",
            }
            for s in sentence_info
        ],
        "models": getattr(model, "_oms_model_ids", {}),
        "infer_seconds": infer_seconds,
    }


def _infer_embedding(params: dict) -> dict:
    """R3：CAM++ 声纹 192 维嵌入提取（FunASR 内建 CMN，口径与 fix(ac6-cmn) 后云侧一致）。

    输入 params: {"audio_path": str}
    输出（成功）: {"ok": True, "task": "embedding", "embedding": [float×192],
                  "dim": 192, "model_version": "cam++-v1"}
    """
    audio_path = params.get("audio_path") or params.get("input")
    if not audio_path:
        return {"ok": False, "error_code": "bad_request", "error": "缺少 audio_path"}
    if not os.path.exists(audio_path):
        return {"ok": False, "error_code": "audio_not_found", "error": f"音频文件不存在: {audio_path}"}

    model = _get_spk_model()
    res = model.generate(input=str(audio_path))
    payload = res[0] if isinstance(res, (list, tuple)) and res else (res or {})

    emb = None
    for key in ("spk_embedding", "embedding"):
        if key in payload:
            emb = payload[key]
            break
    if emb is None:
        return {
            "ok": False,
            "error_code": "no_embedding",
            "error": f"CAM++ 未返回 spk_embedding，keys={list(payload.keys())}",
        }

    vec = emb.squeeze().tolist() if hasattr(emb, "squeeze") else list(emb)
    return {
        "ok": True,
        "task": "embedding",
        "engine": "local-funasr",
        "embedding": [float(x) for x in vec],
        "dim": len(vec),
        "model_version": "cam++-v1",
    }


def _handle_infer(params: dict) -> dict:
    """本地推理接入口（主干 R1/R2/R3 已接入 FunASR 管线）。

    按 params["task"] 分派：asr（转写全管线）/ embedding（CAM++ 声纹）。
    返回 dict 必含 "ok"；main() 据此设置 JSON Lines 响应的 ok 字段。
    """
    task = (params.get("task") or "").strip()
    if task == "asr":
        return _infer_asr(params)
    if task == "embedding":
        return _infer_embedding(params)
    return {
        "ok": False,
        "error_code": "unsupported_task",
        "error": f"不支持的推理任务: {task!r}（可选 asr / embedding）",
    }


def main():
    """子进程主循环：逐行读取 stdin JSON 请求并应答。"""
    # MODELSCOPE_CACHE：宿主（core/engine_host.py build_worker_env）已注入则直接沿用——
    # 独立引擎包（D-G1 方案 A）内没有主应用 settings 可读，不得再走 build_engine_env 推导；
    # 开发态（python -m core.engine_worker 直跑）无该环境变量时才回退推导。
    if not os.environ.get("MODELSCOPE_CACHE"):
        from core.engine_host import build_engine_env
        for k, v in build_engine_env().items():
            os.environ[k] = v

    inp = sys.stdin
    out = sys.stdout
    for line in inp:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            _reply(out, None, False, error_code="bad_request", error="invalid JSON line")
            continue

        req_id = req.get("id")
        cmd = req.get("cmd", "")
        try:
            if cmd == "ping":
                _reply(out, req_id, True, engine="local-stub", pid=__import__("os").getpid())
            elif cmd == "verify_models":
                _reply(out, req_id, True, **_handle_verify_models())
            elif cmd == "infer":
                result = _handle_infer(req.get("params", {}) or {})
                ok = bool(result.pop("ok", False))
                _reply(out, req_id, ok, **result)
            elif cmd == "stop":
                _reply(out, req_id, True, bye=True)
                break
            else:
                _reply(out, req_id, False, error_code="unknown_cmd", error=f"unknown cmd: {cmd}")
        except Exception as e:  # 单请求失败不拖垮常驻进程
            logger.exception("engine worker 请求处理失败")
            _reply(out, req_id, False, error_code="worker_error", error=str(e)[:300])

    return 0


if __name__ == "__main__":
    # Spike §3.2：冻结包多进程必须显式 freeze_support，防止子进程重复引导主程序
    multiprocessing.freeze_support()
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    sys.exit(main())
