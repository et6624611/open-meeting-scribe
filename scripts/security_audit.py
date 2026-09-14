#!/usr/bin/env python3
"""
scripts/security_audit.py — 开发阶段安全审计日志扫描

职责：
  扫描 server.log，检测潜在安全隐患并输出到 audit.log。

检测规则：
  1. API Key 泄露 — 日志中出现 sk- 开头的明文密钥
  2. 路径遍历 — 请求路径含 ../ 或编码变体
  3. 堆栈暴露 — Traceback 或完整异常堆栈出现在响应中
  4. 异常访问频率 — 同一 IP 短时间内大量 4xx 错误
  5. 敏感文件访问 — 尝试访问 .env / .git / 密钥文件
  6. 错误激增 — 单位时间内 ERROR/CRITICAL 数量异常

用法：
  python scripts/security_audit.py              # 扫描一次，输出到终端 + audit.log
  python scripts/security_audit.py --watch      # 持续监控（每 5 秒扫描新增内容）
  python scripts/security_audit.py --since 1h   # 只扫描最近 1 小时的日志
"""

import argparse
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# ── 路径 ──
PROJECT_ROOT = Path(__file__).parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
SERVER_LOG = LOG_DIR / "server.log"
AUDIT_LOG = LOG_DIR / "audit.log"

# ── 检测规则 ──

# 1. API Key 泄露：匹配 sk- 开头的长字符串（DashScope / OpenAI 风格）
API_KEY_PATTERN = re.compile(r'sk-[A-Za-z0-9_\-]{20,}')

# 2. 路径遍历
PATH_TRAVERSAL_PATTERN = re.compile(
    r'(\.\./|\.\.\\|%2e%2e%2f|%2e%2e/|\.\.%2f|%2e%2e%5c)',
    re.IGNORECASE
)

# 3. 堆栈暴露（日志中记录完整 traceback 且可能被返回给前端）
TRACEBACK_PATTERN = re.compile(r'(Traceback \(most recent call last\)|File ".*?", line \d+)')

# 4. 敏感文件访问
SENSITIVE_FILE_PATTERN = re.compile(
    r'(GET|POST|PUT|DELETE|PATCH)\s+(/\.(env|git|ssh|aws)|/data/users\.json|/data/speakers\.json)',
    re.IGNORECASE
)

# 5. HTTP 错误状态码（4xx 客户端错误）
HTTP_ERROR_PATTERN = re.compile(r'"(?:GET|POST|PUT|DELETE|PATCH)\s+[^"]*\s+HTTP/[^"]*"\s+(4\d{2})')

# 6. 日志级别标记
LOG_LEVEL_PATTERN = re.compile(r'\[(ERROR|CRITICAL)\]')

# ── 告警级别 ──
LEVEL_HIGH = "🔴 高危"
LEVEL_MEDIUM = "🟡 中危"
LEVEL_LOW = "🟢 低危"


class AuditScanner:
    """安全审计扫描器"""

    def __init__(self):
        self.findings = []          # 本次扫描发现
        self.last_position = 0      # 文件读取位置（用于增量扫描）
        self.ip_error_counts = defaultdict(list)  # IP → [timestamp, ...]
        self.error_timeline = []    # [(timestamp, level), ...]

    def scan_line(self, line: str, line_no: int):
        """扫描单行日志"""

        # 提取时间戳（格式：2026-09-04 20:12:21）
        ts_match = re.match(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', line)
        timestamp = ts_match.group(1) if ts_match else "unknown"

        # 规则 1: API Key 泄露
        if API_KEY_PATTERN.search(line):
            self.findings.append({
                "level": LEVEL_HIGH,
                "rule": "API_KEY_LEAK",
                "line": line_no,
                "time": timestamp,
                "detail": "日志中出现明文 API Key（sk-...）",
                "snippet": self._mask_key(line),
            })

        # 规则 2: 路径遍历
        if PATH_TRAVERSAL_PATTERN.search(line):
            self.findings.append({
                "level": LEVEL_HIGH,
                "rule": "PATH_TRAVERSAL",
                "line": line_no,
                "time": timestamp,
                "detail": "检测到路径遍历尝试",
                "snippet": line.strip()[:200],
            })

        # 规则 3: 堆栈暴露
        if TRACEBACK_PATTERN.search(line):
            self.findings.append({
                "level": LEVEL_MEDIUM,
                "rule": "STACK_EXPOSURE",
                "line": line_no,
                "time": timestamp,
                "detail": "日志中包含完整异常堆栈",
                "snippet": line.strip()[:200],
            })

        # 规则 4: 敏感文件访问
        if SENSITIVE_FILE_PATTERN.search(line):
            self.findings.append({
                "level": LEVEL_HIGH,
                "rule": "SENSITIVE_FILE_ACCESS",
                "line": line_no,
                "time": timestamp,
                "detail": "尝试访问敏感文件/路径",
                "snippet": line.strip()[:200],
            })

        # 规则 5: 收集 HTTP 4xx 错误（用于后续频率分析）
        http_match = HTTP_ERROR_PATTERN.search(line)
        if http_match:
            # 提取 IP（uvicorn 日志格式中通常在行首）
            ip_match = re.match(r'(\d+\.\d+\.\d+\.\d+)', line)
            if ip_match:
                ip = ip_match.group(1)
                self.ip_error_counts[ip].append(timestamp)

        # 规则 6: 收集 ERROR/CRITICAL 级别日志
        level_match = LOG_LEVEL_PATTERN.search(line)
        if level_match:
            self.error_timeline.append((timestamp, level_match.group(1)))

    def analyze_patterns(self):
        """分析聚合模式（扫描完所有行后调用）"""

        # 检查 IP 异常频率：同一 IP 在 1 分钟内超过 20 次 4xx → 疑似扫描
        for ip, timestamps in self.ip_error_counts.items():
            if len(timestamps) >= 20:
                self.findings.append({
                    "level": LEVEL_MEDIUM,
                    "rule": "HIGH_ERROR_RATE",
                    "line": "-",
                    "time": timestamps[0],
                    "detail": f"IP {ip} 产生 {len(timestamps)} 次 HTTP 4xx 错误，疑似异常探测",
                    "snippet": f"首次: {timestamps[0]}, 末次: {timestamps[-1]}",
                })

        # 检查错误激增：1 分钟内超过 10 条 ERROR/CRITICAL
        if len(self.error_timeline) >= 10:
            # 简单按时间窗口统计
            window_errors = defaultdict(int)
            for ts, level in self.error_timeline:
                # 按分钟聚合
                minute_key = ts[:16]  # "2026-09-04 20:12"
                window_errors[minute_key] += 1

            for minute, count in window_errors.items():
                if count >= 10:
                    self.findings.append({
                        "level": LEVEL_MEDIUM,
                        "rule": "ERROR_SURGE",
                        "line": "-",
                        "time": minute,
                        "detail": f"{minute} 分钟内出现 {count} 条 ERROR/CRITICAL 日志",
                        "snippet": f"错误激增时段: {minute}",
                    })

    def _mask_key(self, line: str) -> str:
        """遮蔽 key 内容，只保留前 6 位"""
        def replacer(m):
            key = m.group(0)
            return key[:6] + "***[已遮蔽]***"
        masked = API_KEY_PATTERN.sub(replacer, line)
        return masked.strip()[:200]

    def scan_file(self, log_path: Path, since: datetime | None = None):
        """扫描日志文件"""
        if not log_path.exists():
            print(f"日志文件不存在: {log_path}")
            return

        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            line_no = 0
            for line in f:
                line_no += 1

                # 如果指定了 since，跳过过早的行
                if since:
                    ts_match = re.match(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', line)
                    if ts_match:
                        try:
                            line_time = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S")
                            if line_time < since:
                                continue
                        except ValueError:
                            pass

                self.scan_line(line, line_no)

        self.last_position = line_no
        self.analyze_patterns()

    def scan_new_lines(self, log_path: Path):
        """增量扫描新增行（用于 watch 模式）"""
        if not log_path.exists():
            return

        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(self.last_position)
            line_no = self.last_position
            new_findings_count = len(self.findings)

            for line in f:
                line_no += 1
                self.scan_line(line, line_no)

            self.last_position = line_no

        if len(self.findings) > new_findings_count:
            self.analyze_patterns()

    def report(self) -> str:
        """生成扫描报告"""
        if not self.findings:
            return "✅ 未发现安全隐患"

        # 按级别排序
        level_order = {LEVEL_HIGH: 0, LEVEL_MEDIUM: 1, LEVEL_LOW: 2}
        sorted_findings = sorted(self.findings, key=lambda f: level_order.get(f["level"], 9))

        lines = [
            "=" * 60,
            f"🔍 安全审计报告 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"   共发现 {len(self.findings)} 项安全问题",
            "=" * 60,
            "",
        ]

        # 统计
        high_count = sum(1 for f in self.findings if f["level"] == LEVEL_HIGH)
        medium_count = sum(1 for f in self.findings if f["level"] == LEVEL_MEDIUM)
        low_count = sum(1 for f in self.findings if f["level"] == LEVEL_LOW)

        if high_count:
            lines.append(f"  {LEVEL_HIGH}: {high_count} 项")
        if medium_count:
            lines.append(f"  {LEVEL_MEDIUM}: {medium_count} 项")
        if low_count:
            lines.append(f"  {LEVEL_LOW}: {low_count} 项")
        lines.append("")

        for i, f in enumerate(sorted_findings, 1):
            lines.append(f"─── [{i}] {f['level']} | {f['rule']} ───")
            lines.append(f"  时间: {f['time']}  行号: {f['line']}")
            lines.append(f"  说明: {f['detail']}")
            lines.append(f"  原文: {f['snippet']}")
            lines.append("")

        return "\n".join(lines)


def parse_since(since_str: str) -> datetime:
    """解析 --since 参数，如 '1h', '30m', '2d'"""
    match = re.match(r'^(\d+)([hmd])$', since_str)
    if not match:
        raise ValueError(f"无法解析时间格式: {since_str}，支持格式: 1h, 30m, 2d")

    value = int(match.group(1))
    unit = match.group(2)

    delta_map = {
        'h': timedelta(hours=value),
        'm': timedelta(minutes=value),
        'd': timedelta(days=value),
    }
    return datetime.now() - delta_map[unit]


def main():
    parser = argparse.ArgumentParser(description="安全审计日志扫描器")
    parser.add_argument("--watch", action="store_true", help="持续监控模式（每 5 秒扫描新增内容）")
    parser.add_argument("--since", type=str, help="只扫描指定时间范围内的日志（如 1h, 30m, 2d）")
    parser.add_argument("--interval", type=int, default=5, help="watch 模式扫描间隔（秒，默认 5）")
    parser.add_argument("--file", type=str, help="指定扫描的日志文件路径（默认 logs/server.log）")
    args = parser.parse_args()

    since = parse_since(args.since) if args.since else None
    target_log = Path(args.file) if args.file else SERVER_LOG

    scanner = AuditScanner()

    if args.watch:
        print(f"🔍 安全审计监控已启动（间隔 {args.interval}s）...")
        print(f"   日志文件: {target_log}")
        print("   按 Ctrl+C 停止\n")

        # 先扫描已有内容
        scanner.scan_file(target_log, since=since)
        if scanner.findings:
            report = scanner.report()
            print(report)
            _write_audit_log(report)

        try:
            while True:
                time.sleep(args.interval)
                old_count = len(scanner.findings)
                scanner.scan_new_lines(target_log)
                if len(scanner.findings) > old_count:
                    report = scanner.report()
                    print(report)
                    _write_audit_log(report)
        except KeyboardInterrupt:
            print("\n⏹ 监控已停止")
    else:
        # 单次扫描
        scanner.scan_file(target_log, since=since)
        report = scanner.report()
        print(report)
        _write_audit_log(report)


def _write_audit_log(report: str):
    """追加写入审计日志文件"""
    LOG_DIR.mkdir(exist_ok=True)
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n{'=' * 60}\n")
        f.write(f"扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(report)
        f.write("\n")


if __name__ == "__main__":
    main()
