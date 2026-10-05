"""WP-D — 生成冻结冒烟用替身 fixture（禁真实模型下载）。

产出目录结构（模拟 R5 外置模型目录布局，MODELSCOPE_CACHE 亦指向其中）：
    <out>/models/stub-asr/config.yaml   # model: StubAsrModel（冒烟脚本内注册的替身类）
    <out>/models/stub-asr/model.pt      # 随机张量替身权重（torch.save state_dict）
    <out>/audio/stub_3s.wav             # 3 秒 16kHz 单声道噪声 wav
    <out>/ms_cache/                     # 空 ModelScope 缓存目录（MODELSCOPE_CACHE 指向此处）

用法：
    python make_fixtures.py --out <dir>
"""
import argparse
import math
import struct
import sys
import wave
from pathlib import Path

# Windows CI 控制台默认 cp1252：中文输出显式切 UTF-8
#（实测缺陷：UnicodeEncodeError 'charmap' codec can't encode）
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

CONFIG_YAML = """\
# WP-D 替身模型配置：结构与 ModelScope 真实模型目录一致（config.yaml + model.pt），
# 但 model 类为冒烟脚本注册的 StubAsrModel，权重为随机张量，不含任何真实模型资产。
model: StubAsrModel
model_conf:
  feat_dim: 80
  hidden_dim: 16
frontend: null
tokenizer: null
"""


def write_wav(path: Path, seconds: float = 3.0, sr: int = 16000) -> None:
    """生成确定性伪语音噪声（正弦叠加 + 轻噪声），不依赖 numpy。"""
    n = int(seconds * sr)
    frames = bytearray()
    for i in range(n):
        t = i / sr
        v = (
            0.4 * math.sin(2 * math.pi * 220.0 * t)
            + 0.2 * math.sin(2 * math.pi * 640.0 * t + 0.7)
            + 0.05 * math.sin(2 * math.pi * 3700.0 * t)
        )
        # 4Hz 幅度包络，模拟语音节奏
        v *= 0.6 + 0.4 * math.sin(2 * math.pi * 4.0 * t)
        sample = max(-32767, min(32767, int(v * 32767)))
        frames += struct.pack("<h", sample)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(frames))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="fixture 输出根目录")
    args = ap.parse_args()

    out = Path(args.out).resolve()
    model_dir = out / "models" / "stub-asr"
    audio_dir = out / "audio"
    ms_cache = out / "ms_cache"
    for d in (model_dir, audio_dir, ms_cache):
        d.mkdir(parents=True, exist_ok=True)

    (model_dir / "config.yaml").write_text(CONFIG_YAML, encoding="utf-8")
    # 注意：目录内不放 tokens.txt/am.mvn 等可选资产 —— funasr 会据其存在性走
    # tokenizer_conf/frontend_conf 分支，替身模型 tokenizer/frontend 均为 null。

    # 替身权重：随机张量 state_dict，与 StubAsrModel 参数结构一致
    import torch

    torch.manual_seed(20260923)
    state = {
        "embed.weight": torch.randn(16, 80) * 0.1,
        "embed.bias": torch.zeros(16),
    }
    torch.save(state, str(model_dir / "model.pt"))

    write_wav(audio_dir / "stub_3s.wav")

    print(f"[FIXTURE] 替身 fixture 就绪: {out}")
    print(f"[FIXTURE] model_dir={model_dir}")
    print(f"[FIXTURE] wav={audio_dir / 'stub_3s.wav'}")
    print(f"[FIXTURE] ms_cache={ms_cache}")


if __name__ == "__main__":
    main()
