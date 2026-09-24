"""AC-7 — 云精简主包体积回归检查（WP-D 守护）。

对 PyInstaller 产出的云精简主包 exe（dist/OpenMeetingScribe.exe，不含 ffmpeg/安装器）
做阈值对比：
  - 超出 hard_cap_mb            → fail（本地引擎组件侵入的兜底绊线）；
  - 已有基线且超 baseline+容差   → fail（云包零增长回归）；
  - 基线为空（首次运行 bootstrap）→ 仅按 hard_cap 判定，并把建议基线写入报告，
    由项目方确认后回填 cloud-size-baseline.json 的 baseline_mb。

用法：
    python cloud_size_check.py --exe <exe 路径> --baseline <baseline.json> --report <report.json>
"""
import argparse
import json
import math
import sys
from pathlib import Path

# Windows CI 控制台默认 cp1252：中文输出显式切 UTF-8（防 UnicodeEncodeError）
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    exe = Path(args.exe)
    if not exe.is_file():
        print(f"[SIZE] FAIL: 主包不存在 {exe}")
        return 2

    cfg = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    baseline_mb = cfg.get("baseline_mb")
    tolerance_pct = float(cfg.get("tolerance_pct", 10))
    hard_cap_mb = float(cfg["hard_cap_mb"])

    measured_mb = exe.stat().st_size / (1024 * 1024)
    limit_by_baseline = (
        baseline_mb * (1 + tolerance_pct / 100.0) if baseline_mb else None
    )

    print(f"[SIZE] 实测主包体积: {measured_mb:.1f} MB ({exe})")
    print(f"[SIZE] 基线: {baseline_mb if baseline_mb else '未设定（bootstrap 模式）'} MB, "
          f"容差: {tolerance_pct}%, 硬上限: {hard_cap_mb:.0f} MB")

    passed = True
    reasons = []
    if measured_mb > hard_cap_mb:
        passed = False
        reasons.append(
            f"超出硬上限 {hard_cap_mb:.0f}MB —— 疑似本地引擎组件（torch/funasr/modelscope）侵入云包"
        )
    if limit_by_baseline is not None and measured_mb > limit_by_baseline:
        passed = False
        reasons.append(
            f"超出基线容差 {limit_by_baseline:.1f}MB（baseline {baseline_mb}MB + {tolerance_pct}%）"
            " —— 违反 AC-7 云包零增长"
        )

    report = {
        "exe": str(exe),
        "measured_mb": round(measured_mb, 1),
        "baseline_mb": baseline_mb,
        "tolerance_pct": tolerance_pct,
        "hard_cap_mb": hard_cap_mb,
        "passed": passed,
        "reasons": reasons,
    }
    if baseline_mb is None:
        # 建议基线：实测值向上取整到 5MB，留正常波动空间
        report["suggested_baseline_mb"] = int(math.ceil(measured_mb / 5.0) * 5)
        print(f"[SIZE] bootstrap：请将建议基线 {report['suggested_baseline_mb']}MB "
              f"回填到 {args.baseline} 的 baseline_mb 字段")

    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if not passed:
        for r in reasons:
            print(f"[SIZE] FAIL: {r}")
        return 1
    print("[SIZE] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
