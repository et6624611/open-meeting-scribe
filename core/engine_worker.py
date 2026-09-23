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

推理命令（cmd="infer"）当前返回 not_implemented —— 本地 FunASR 推理体
由主干 R1/R2（QoderIDE 侧）在本工作端内接入；本模块交付常驻架构与
模型完整性预检（篡改拒载），管线接入口即 _handle_infer。

重依赖（funasr/torch）必须只在子进程内、且按需惰性 import，
保证云端精简包（无 torch）下本模块可被安全引用。
"""

import json
import logging
import multiprocessing
import os
import sys

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1


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


def _handle_infer(params: dict) -> dict:
    """本地推理接入口（主干 R2 在此接入 FunASR 管线）。

    当前为显式未实现：常驻架构、环境（MODELSCOPE_CACHE）与完整性预检已就绪，
    推理体属主干 R1/R2 范围。
    """
    return {
        "error_code": "not_implemented",
        "error": "本地推理管线尚未接入（主干 R1/R2 范围）；常驻子进程与模型完整性架构已就绪",
    }


def main():
    """子进程主循环：逐行读取 stdin JSON 请求并应答。"""
    # 引擎子进程内设置 MODELSCOPE_CACHE，使 modelscope/funasr 按外置权重目录定位模型
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
                _reply(out, req_id, False, **result)
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
