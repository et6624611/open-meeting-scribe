"""WP-D — 本地引擎替身冻结冒烟入口（Windows PyInstaller + FunASR CI 冒烟）。

验证目标（对齐 SPIKE-R8 §3 与 PRD R5 实施约束 ①–④、R8/AC-7）：
  1. 冻结态 torch / funasr import 可达（记录耗时；Spike 实测冻结首启 funasr import 最高 86s，
     Windows 杀软场景更差 —— CI step timeout 须留量）；
  2. multiprocessing 重执行坑：spawn 子进程必须经 __main__ guard + freeze_support 引导，
     本脚本即为 R5 约束②的示范实现（子进程内重新 import torch 并计算，验证冻结态可派生）；
  3. AutoModel 加载链：本地替身模型目录（config.yaml + 随机权重 model.pt）→ 注册表解析 →
     checkpoint 加载，全程零网络（MODELSCOPE_CACHE 指向 fixture 空目录，禁真实模型下载）；
  4. 推理代码路径：generate(input=3s 替身 wav) 走通音频加载 → 特征 → forward → 文本结果。

用法（冻结前后可执行同一脚本）：
    python stub_engine.py --fixtures <fixture 目录>
    local_engine_stub.exe --fixtures <fixture 目录>

退出码 0 且末行输出 "[STUB] PASS" 即冒烟通过。
"""
import argparse
import multiprocessing
import os
import sys
import time
from pathlib import Path

# Windows CI 控制台默认 cp1252：中文输出显式切 UTF-8（防 UnicodeEncodeError）
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

_T0 = time.time()


def _phase(msg: str) -> None:
    print(f"[STUB +{time.time() - _T0:7.1f}s] {msg}", flush=True)


# ── spawn 子进程 worker（必须为模块级函数，spawn 下需可被重新引导）──────────
def _child_worker(conn) -> None:
    """冻结态子进程：重新 import torch 并做一次张量计算。

    Spike 观察：无 __main__ guard + freeze_support 时，Windows/冻结态 spawn 会
    重复执行整个入口脚本（日志见 import 重复引导 5–6 次甚至无限递归）。
    """
    import torch

    payload = {
        "pid": os.getpid(),
        "torch": torch.__version__,
        "sum": float(torch.rand(64, 64).sum()),
        "frozen": bool(getattr(sys, "frozen", False)),
    }
    conn.send(payload)
    conn.close()


def run_multiprocessing_check(timeout_s: int = 900) -> None:
    """R5 约束② 示范：显式 spawn 上下文 + 父进程限时等待，验证子进程不重执行冒烟主体。"""
    ctx = multiprocessing.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child_worker, args=(child_conn,), name="stub-engine-child")
    t0 = time.time()
    proc.start()
    if not parent_conn.poll(timeout_s):
        proc.kill()
        raise TimeoutError(f"子进程 {timeout_s}s 内未返回（冻结态 spawn 引导失败？）")
    payload = parent_conn.recv()
    proc.join(60)
    parent_conn.close()
    if proc.exitcode != 0:
        raise RuntimeError(f"子进程退出码异常: {proc.exitcode}")
    _phase(
        f"multiprocessing spawn 子进程 OK ({time.time() - t0:.1f}s) "
        f"child_pid={payload['pid']} frozen={payload['frozen']} torch={payload['torch']}"
    )


# ── 替身模型类：注册进 funasr 注册表，顶替真实 ASR 架构 ─────────────────────
def build_stub_model_class():
    import torch
    from funasr.register import tables
    from funasr.utils.load_utils import load_audio_text_image_video

    class StubAsrModel(torch.nn.Module):
        """替身 ASR 模型：结构与真实模型加载契约一致（state_dict 加载 + inference 协议）。"""

        def __init__(self, feat_dim: int = 80, hidden_dim: int = 16, **kwargs):
            super().__init__()
            self.embed = torch.nn.Linear(feat_dim, hidden_dim)

        def inference(
            self,
            data_in,
            data_lengths=None,
            key=None,
            tokenizer=None,
            frontend=None,
            **cfg,
        ):
            # 走 funasr 音频加载链（torchaudio/soundfile 后端，冻结态数据文件依赖即在此暴露）
            path = data_in[0] if isinstance(data_in, (list, tuple)) else data_in
            speech = load_audio_text_image_video(path, fs=16000)
            if isinstance(speech, (list, tuple)):
                speech = speech[0]
            speech = speech.squeeze()
            n_samples = int(speech.shape[-1])
            dur_s = max(n_samples / 16000.0, 1e-6)

            # 80 维伪特征帧 → 替身权重 forward（随机张量，输出无语言学意义）
            flat = speech.reshape(-1).numpy().astype("float32")
            n = (flat.shape[0] // 80) * 80
            feats = torch.from_numpy(flat[:n].reshape(-1, 80))
            with torch.no_grad():
                out = self.embed(feats)
            score = float(out.mean())

            text = f"替身转写结果 frames={feats.shape[0]} score={score:.4f}"
            key0 = key[0] if isinstance(key, (list, tuple)) and key else (key or "stub")
            results = [
                {
                    "key": str(key0),
                    "text": text,
                    "timestamp": [[0, int(dur_s * 1000)]],
                }
            ]
            meta = {
                "batch_data_time": dur_s,
                "load_data": 0.0,
                "extract_feat": 0.0,
            }
            return results, meta

    # 注意：不用官方 @tables.register 装饰器 —— 其元信息记录调用
    # inspect.getsourcelines()，冻结态 __main__ 无源码会抛 OSError（本机冻结
    # 预验证实测踩坑）。直接写注册表字典，与 build_model 的查表逻辑等价。
    tables.model_classes["StubAsrModel"] = StubAsrModel
    return StubAsrModel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", required=True, help="make_fixtures.py 产出的 fixture 根目录")
    ap.add_argument("--skip-mp", action="store_true", help="跳过 spawn 子进程检查（调试用）")
    args = ap.parse_args()

    fixtures = Path(args.fixtures).resolve()
    model_dir = fixtures / "models" / "stub-asr"
    wav = fixtures / "audio" / "stub_3s.wav"
    ms_cache = fixtures / "ms_cache"
    for p in (model_dir, wav, ms_cache):
        if not p.exists():
            print(f"[STUB] FAIL: fixture 缺失 {p}", flush=True)
            return 2

    # 硬性禁令：CI 禁真实模型下载 —— MODELSCOPE_CACHE 指向 fixture 空目录，
    # 且模型以本地路径加载（funasr 对存在路径不会触达 hub）。
    os.environ["MODELSCOPE_CACHE"] = str(ms_cache)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    _phase(f"启动 frozen={bool(getattr(sys, 'frozen', False))} python={sys.version.split()[0]}")

    t0 = time.time()
    import torch

    _phase(f"torch {torch.__version__} import ok ({time.time() - t0:.1f}s)")

    t0 = time.time()
    from funasr import AutoModel

    _phase(f"funasr import ok ({time.time() - t0:.1f}s)")

    build_stub_model_class()

    # R5 约束②：冻结/Windows spawn 重执行坑验证（入口须在 __main__ guard + freeze_support 之后）
    if not args.skip_mp:
        run_multiprocessing_check()

    t0 = time.time()
    model = AutoModel(
        model=str(model_dir),  # 本地替身目录，零网络
        device="cpu",
        disable_update=True,
        disable_pbar=True,
        log_level="ERROR",
    )
    _phase(f"AutoModel 加载链 ok ({time.time() - t0:.1f}s) model_path={model.model_path}")

    t0 = time.time()
    res = model.generate(input=str(wav), batch_size_s=300)
    text = res[0].get("text", "") if res else ""
    if not text:
        print("[STUB] FAIL: 推理路径未产出文本", flush=True)
        return 3
    _phase(f"generate 推理路径 ok ({time.time() - t0:.1f}s) text={text!r}")

    _phase("PASS")
    # 契约末行（workflow 以字面 '[STUB] PASS' 断言；_phase 前缀含耗时不满足字面匹配）
    print("[STUB] PASS", flush=True)
    return 0


if __name__ == "__main__":
    # R5 约束②：Windows/冻结态 multiprocessing 以 spawn 重执行入口 exe，
    # freeze_support() 必须是 __main__ guard 内第一条语句，否则子进程会重跑整个冒烟。
    multiprocessing.freeze_support()
    sys.exit(main())
