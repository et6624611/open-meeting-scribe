"""
core/engine_worker.py — 本地引擎常驻子进程工作端（R5 / WP-B）

架构约束（Spike §3.2）：
  1. 冻结态 funasr 冷 import 最高 86s —— 引擎必须以常驻子进程运行（启动一次复用），
     禁止每任务冷启动；进程生命周期由 core.engine_host.EngineHost 管理。
  2. 多进程必须 `if __name__ == "__main__"` 保护 + 显式 multiprocessing.freeze_support()，
     防止冻结包被子进程重复引导（Spike 观察到 import 重复 5–6 次）。

协议：stdin/stdout JSON Lines（每行一个 JSON 对象）。
  请求:  {"id": <any>, "cmd": "ping" | "verify_models" | "warmup" | "infer" | "stop", ...}
  响应:  {"id": <any>, "ok": true/false, ...}

推理命令（cmd="infer"）由主干 R1/R2/R3（WP-E）接入 FunASR 离线管线：
  - params.task="asr"       → seaco-paraformer + fsmn-vad + ct-punc(可选) + cam++ 分离，
                              回传 sentence_info（时间戳/说话人/文本）+ 全文；
  - params.task="embedding" → cam++ 声纹 192 维嵌入（R3，与说话人分离共用同一份权重）。
FunASR AutoModel 进程内惰性加载并缓存为单例（常驻复用，禁每请求冷启动）。

重依赖（funasr/torch）必须只在子进程内、且按需惰性 import，
保证云端精简包（无 torch）下本模块可被安全引用。
"""

import contextlib
import json
import logging
import multiprocessing
import os
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1


@contextlib.contextmanager
def _quiet_stdout():
    """模型加载期把 fd 1 指到 stderr（宿主以 DEVNULL 丢弃），保护 JSON Lines 协议。

    funasr/modelscope 加载路径存在向 stdout 的直接 print（QA-R1 修复回归实证：
    预热响应被非 JSON 行打断 → 'Expecting value'）。仅包住惰性加载段，
    正常请求应答仍走 main() 捕获的 out 句柄。
    """
    sys.stdout.flush()
    saved = os.dup(1)
    try:
        os.dup2(2, 1)
        yield
    finally:
        try:
            sys.stdout.flush()
        except Exception:
            pass
        os.dup2(saved, 1)
        os.close(saved)

# ── FunASR 模型进程内单例（常驻复用，R5 约束①：禁每任务冷启动）──
# Resident in-process FunASR model singletons (reuse across requests; never cold-start per task)
_ASR_MODEL = None
_SPK_MODEL = None


class ModelsNotReadyError(RuntimeError):
    """DEF-QA-R1-01：本地权重缺失时的可行动错误（引导下载，绝不隐式回连网络）。"""


def _local_model_path(model_key: str) -> str:
    """解析模型权重的本地文件系统绝对路径（DEF-QA-R1-01 核心修复）。

    ModelScope ID 直传 AutoModel 会强制出网取元数据（disable_update=True 并不能阻止
    GET modelscope.cn/api/v1/models/<id>/repo/files），断网下加载即失败（QA-R1 T1 实证）。
    此处经 core.model_registry 同源解析到本地目录 {model_dir}/hub/{modelscope_id}，
    并以绝对路径锚点返回（QA probe T3 验证本地路径加载全程零网络）。

    相对 model_dir 的绝对化锚定到 MODELSCOPE_CACHE（engine_host.build_engine_env 已
    resolve 为绝对路径）；冻结包形态的相对路径缺陷（WP-G B-2）由该锚点统一承接。
    """
    from core.model_registry import MODEL_BY_KEY, get_model_dir

    meta = MODEL_BY_KEY[model_key]
    model_dir = Path(get_model_dir()).expanduser()
    if not model_dir.is_absolute():
        cache = os.environ.get("MODELSCOPE_CACHE")
        if cache:
            model_dir = Path(cache).expanduser()
    root = (model_dir / "hub" / meta["modelscope_id"]).resolve()
    if not (root / "config.yaml").is_file():
        raise ModelsNotReadyError(
            f"本地模型权重缺失或损坏: {model_key}（预期目录 {root}）。"
            "请在 设置 → 本地引擎 中下载模型（仅首次获取需联网；运行期不隐式回连）。"
        )
    return str(root)


def _optional_local_model_path(model_key: str) -> str | None:
    """可选模型（ct-punc）：本地权重存在才返回路径，缺失静默跳过（裁剪档语义不变）。"""
    try:
        return _local_model_path(model_key)
    except ModelsNotReadyError:
        return None


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
    DEF-QA-R1-01：AutoModel 入参一律为本地文件系统绝对路径（经 model_registry 同源解析），
    禁止直传 ModelScope ID——后者会强制出网取仓库元数据，断网闭环第一步即断裂。
    """
    global _ASR_MODEL
    if _ASR_MODEL is not None:
        return _ASR_MODEL

    from core.model_registry import MODEL_BY_KEY

    # 权重校验先行：缺失 → models_missing 可行动错误（早于任何 funasr 触达）
    models = {
        "model": _local_model_path("seaco-paraformer-zh"),
        "vad_model": _local_model_path("fsmn-vad"),
        "spk_model": _local_model_path("cam-plus"),
    }
    # 标点可选：本地权重存在才挂入（省 1.0GB 的裁剪档不带标点）
    punc_path = _optional_local_model_path("ct-punc")
    if punc_path:
        models["punc_model"] = punc_path

    logger.info(f"[引擎] 加载 ASR 管线: {sorted(models.keys())}")
    with _quiet_stdout():
        # 冷 import 本身也可能向 stdout 输出（冻结态首启）→ 一并包住
        from funasr import AutoModel

        _ASR_MODEL = AutoModel(**models, disable_update=True, disable_pbar=True, log_level="ERROR")
    # 观测：记录实际挂载的模型（PRD §9 任务日志）。键保持 ModelScope ID（人类可读），
    # 实际入参路径仅在本函数内使用，不外泄为观测值。
    mounted_keys = {
        "model": "seaco-paraformer-zh",
        "vad_model": "fsmn-vad",
        "spk_model": "cam-plus",
    }
    if "punc_model" in models:
        mounted_keys["punc_model"] = "ct-punc"
    _ASR_MODEL._oms_model_ids = {
        role: MODEL_BY_KEY[key]["modelscope_id"] for role, key in mounted_keys.items()
    }
    return _ASR_MODEL


def _get_spk_model():
    """惰性加载并缓存 CAM++ 声纹模型（R3，与说话人分离共用同一份权重）。

    DEF-QA-R1-01：同 _get_asr_model，入参为本地绝对路径，杜绝运行期出网。
    """
    global _SPK_MODEL
    if _SPK_MODEL is not None:
        return _SPK_MODEL

    model_path = _local_model_path("cam-plus")

    logger.info(f"[引擎] 加载 CAM++ 声纹模型: {model_path}")
    with _quiet_stdout():
        # 冷 import 同样包进静默段（与 _get_asr_model 对齐，防冻结态首启污染 stdout）
        from funasr import AutoModel

        _SPK_MODEL = AutoModel(model=model_path, disable_update=True, disable_pbar=True, log_level="ERROR")
    return _SPK_MODEL


def _handle_warmup() -> dict:
    """引擎预热（DEF-QA-R1-03 方案①）：把模型惰性加载移出首个推理请求。

    在常驻子进程事件循环内同步执行——预热期间后续请求按序排队（stdin 缓冲），
    首个业务请求不再叠加「冷加载 ≈16s（冻结态冷 import 另可达 86s）」的耗时。
    失败不杀进程：回包给宿主仅记日志，真正使用仍走请求级错误分类。
    """
    t0 = time.time()
    _get_asr_model()
    _get_spk_model()
    return {
        "ok": True,
        "warmed": ["asr", "spk"],
        "seconds": round(time.time() - t0, 2),
    }


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
            elif cmd == "warmup":
                result = _handle_warmup()
                ok = bool(result.pop("ok", False))
                _reply(out, req_id, ok, **result)
            elif cmd == "infer":
                result = _handle_infer(req.get("params", {}) or {})
                ok = bool(result.pop("ok", False))
                _reply(out, req_id, ok, **result)
            elif cmd == "stop":
                _reply(out, req_id, True, bye=True)
                break
            else:
                _reply(out, req_id, False, error_code="unknown_cmd", error=f"unknown cmd: {cmd}")
        except ModelsNotReadyError as e:  # DEF-QA-R1-01：权重缺失 → 可行动错误，不隐式回连
            _reply(out, req_id, False, error_code="models_missing", error=str(e)[:300])
        except Exception as e:  # 单请求失败不拖垮常驻进程
            logger.exception("engine worker 请求处理失败")
            _reply(out, req_id, False, error_code="worker_error", error=str(e)[:300])

    return 0


if __name__ == "__main__":
    # Spike §3.2：冻结包多进程必须显式 freeze_support，防止子进程重复引导主程序
    multiprocessing.freeze_support()
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    sys.exit(main())
