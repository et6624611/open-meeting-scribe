#!/usr/bin/env python3
"""
scripts/spike_qoder_cli.py — Phase 0 Spike：Qoder CLI 作为 AI 面板工程化引擎的可行性取证

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
版本 / Version: 1.0.0

对应方案：Qoder CLI 引擎方案 §5 Phase 0（7 项假设）
本脚本不并入主程序，仅验证用。证据落盘 .spike_qoder/（原始 stream-json 行 + 汇总 JSON）。

用法：
  python3 scripts/spike_qoder_cli.py            # 跑全部步骤
  python3 scripts/spike_qoder_cli.py 1 3 7      # 只跑指定步骤
步骤：
  0 环境探针（版本/登录态/路径解析）
  1 stream-json 事件结构（→ SSE 映射成立性）
  2 会话恢复 --session-id / -r（跨进程、延迟）
  3 --mcp-config 挂载 stdio MCP Server 并稳定调用工具
  4 无头模式权限行为（default vs bypass_permissions，R8 成立性）
  5 任意 cwd 拉起 + 绝对/相对路径混合
  6 并行 tool_use/tool_result 归属配对（取证，人工判读）
  7 CLI 读边界可信性（-w/--add-dir 之外路径尝试）
"""

import json
import sys
import time
import uuid
import shutil
import argparse
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVID = REPO / ".spike_qoder"
QODER = shutil.which("qoder") or "qoder"
PER_RUN_TIMEOUT = 150  # 单次 CLI 调用上限（秒）
# 实测发现（2026-09-25）：默认模型额度耗尽（error_code=118）会阻断所有需模型的步骤，
# 但账号内其它可用模型不受影响 —— 可通过环境变量 SPIKE_MODEL 覆盖
SPIKE_MODEL = "Qwen3.8-Flash"

SENTINEL_WORKSPACE = "WORKSPACE-OK-7a3f9c"
SENTINEL_OUTSIDE = "OUTSIDE-LEAK-4d8e1b"      # -w 之外，但作为绝对路径"合法"文件
SENTINEL_SIBLING = "SIBLING-LEAK-9c2f5a"      # workspace 父目录（模拟 data/settings.json 场景）

RESULTS = {}


def _log(step_id, **kv):
    print(f"\n[Spike {step_id}] " + " | ".join(str(v)[:160] for v in kv.values()))
    RESULTS[step_id] = {k: v for k, v in kv.items()}


def run_cli(args, timeout=PER_RUN_TIMEOUT, cwd=None):
    """运行 qoder CLI，收集 stream-json 行；返回 (lines, returncode, secs, timed_out)。"""
    t0 = time.perf_counter()
    cmd = [QODER]
    if SPIKE_MODEL:
        cmd += ["-m", SPIKE_MODEL]
    cmd += args
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd,
            stdin=subprocess.DEVNULL,
        )
        out, rc, to = proc.stdout, proc.returncode, False
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        rc, to = -1, True
    secs = round(time.perf_counter() - t0, 2)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return lines, rc, secs, to


def save_raw(name, lines, meta=""):
    p = EVID / f"{name}.jsonl"
    with p.open("w", encoding="utf-8") as f:
        if meta:
            f.write(f"# {meta}\n")
        f.write("\n".join(lines) + "\n")
    return p


def summarize_events(lines):
    """宽容解析 stream-json：统计事件类型分布、提取工具事件与最终文本。"""
    types, tool_events, texts, parsed = {}, [], [], 0
    for ln in lines:
        try:
            evt = json.loads(ln)
        except json.JSONDecodeError:
            continue
        parsed += 1
        t = evt.get("type", "?")
        types[t] = types.get(t, 0) + 1
        # 深扫一层：常见形状 name/tool/input/content
        raw = json.dumps(evt, ensure_ascii=False)
        if '"tool"' in raw or "tool_use" in t or "tool_call" in t or '"Bash"' in raw or '"Read"' in raw or '"Write"' in raw:
            tool_events.append(raw[:400])
        if evt.get("type") == "assistant" or "text" in raw[:200]:
            texts.append(raw[:300])
    return {"event_types": types, "parsed_lines": parsed,
            "total_lines": len(lines), "tool_event_samples": tool_events[:12]}


def make_ws(name, with_context=True):
    """建临时 workspace，含 context/transcript.md（内嵌哨兵）。"""
    ws = EVID / "ws" / name
    if ws.exists():
        shutil.rmtree(ws)
    (ws / "context").mkdir(parents=True)
    if with_context:
        (ws / "context" / "transcript.md").write_text(
            f"张三：我建议 Q3 上线，工作区标记 {SENTINEL_WORKSPACE}\n李四：预算不够，需要再评估。\n",
            encoding="utf-8")
    return ws


# ============================================================
# Step 0 环境探针
# ============================================================

def step0():
    ver = subprocess.run([QODER, "--version"], capture_output=True, text=True).stdout.strip()
    st = subprocess.run([QODER, "status"], capture_output=True, text=True).stdout
    logged = "Username:" in st
    _log("0", 结论=f"path={QODER}", 版本=ver, 登录态=logged)


# ============================================================
# Step 1 stream-json 事件结构
# ============================================================

def step1():
    ws = make_ws("s1")
    lines, rc, secs, to = run_cli([
        "-p", "--output-format", "stream-json",
        "-w", str(ws), "--no-session-persistence",
        "阅读 context/transcript.md，只回答文件中出现的工作区标记原文，不要解释",
    ])
    save_raw("step1_stream", lines, f"rc={rc} secs={secs} timeout={to}")
    s = summarize_events(lines)
    text_all = json.dumps(lines, ensure_ascii=False)
    sentinel_ok = SENTINEL_WORKSPACE in text_all
    _log("1", 事件结构=s, 哨兵命中=SENTINEL_WORKSPACE in text_all and sentinel_ok,
         返回码=rc, 耗时=secs, 超时=to,
         结论="事件类型集合可枚举" if s["parsed_lines"] else "不可解析")
    return s


# ============================================================
# Step 2 会话恢复
# ============================================================

def step2():
    sid = str(uuid.uuid4())
    ws = make_ws("s2")
    lines1, rc1, t1, to1 = run_cli([
        "-p", "--output-format", "stream-json",
        "-w", str(ws), "--session-id", sid,
        "记住这个数字：4287。只回复“已记住”。",
    ])
    save_raw("step2_round1", lines1, f"sid={sid} rc={rc1} secs={t1}")
    r2 = summarize_events(lines1)
    lines2, rc2, t2, to2 = run_cli([
        "-p", "--output-format", "stream-json",
        "-w", str(ws), "-r", sid,
        "我刚才让你记住的数字是多少？只回复数字。",
    ])
    save_raw("step2_round2", lines2, f"sid={sid} rc={rc2} secs={t2}")
    resume_ok = "4287" in json.dumps(lines2, ensure_ascii=False)
    _log("2", session_id=sid, 第一轮=r2, 第一轮耗时=t1, 第二轮耗时=t2,
         跨进程恢复成功=resume_ok, 第二轮返回码=rc2)


# ============================================================
# Step 3 MCP 挂载
# ============================================================

def step3():
    # 生成最小 stdio MCP Server（JSON-RPC 2.0，无第三方依赖）
    server = EVID / "ping_server.py"
    server.parent.mkdir(parents=True, exist_ok=True)
    server.write_text('''
import json, sys
def send(o): sys.stdout.write(json.dumps(o) + "\\n"); sys.stdout.flush()
for line in sys.stdin:
    try: req = json.loads(line)
    except Exception: continue
    m, p = req.get("method", ""), req.get("params", {}) or {}
    if m == "initialize":
        send({"jsonrpc":"2.0","id":req.get("id"),"result":{
            "protocolVersion":"2024-11-05","capabilities":{"tools":{}},
            "serverInfo":{"name":"spike-ping","version":"0.1.0"}}})
    elif m in ("notifications/initialized", "initialized"):
        pass
    elif m == "tools/list":
        send({"jsonrpc":"2.0","id":req.get("id"),"result":{"tools":[{
            "name":"spike_ping",
            "description":"返回固定哨兵串 SPIKE-MCP-7731，用于验证 MCP 工具链路",
            "inputSchema":{"type":"object","properties":{}}}]}})
    elif m == "tools/call":
        send({"jsonrpc":"2.0","id":req.get("id"),"result":{
            "content":[{"type":"text","text":"SPIKE-MCP-7731"}]}})
    elif req.get("id") is not None:
        send({"jsonrpc":"2.0","id":req.get("id"),"error":{"code":-32601,"message":"no method"}})
''', encoding="utf-8")
    cfg = EVID / "mcp_config.json"
    cfg.write_text(json.dumps({"mcpServers": {"spike-ping": {
        "command": sys.executable, "args": [str(server)]}}}), encoding="utf-8")

    ws = make_ws("s3", with_context=False)
    lines, rc, secs, to = run_cli([
        "-p", "--output-format", "stream-json",
        "-w", str(ws), "--no-session-persistence",
        "--strict-mcp-config", "--mcp-config", str(cfg),
        "--allowed-tools", "spike-ping",  # 若该 flag 不适用则观察失败形态
        "调用 spike-ping 的 spike_ping 工具，把工具返回内容原样告诉我",
    ])
    save_raw("step3_mcp", lines, f"rc={rc} secs={secs} timeout={to}")
    s = summarize_events(lines)
    mcp_ok = "SPIKE-MCP-7731" in json.dumps(lines, ensure_ascii=False)
    _log("3", MCP工具调用成功=mcp_ok, 事件=s, 返回码=rc, 耗时=secs)


# ============================================================
# Step 4 无头模式权限行为（R8）
# ============================================================

def step4():
    ws = make_ws("s4")
    target = (ws / "output" / "perm.txt")
    prompt = f"使用 Write 工具（或创建文件的方式）在 output/perm.txt 写入内容 ALPHA。写完后回复 DONE。"
    # 4a: permission-mode default —— 观察是否静默失败/挂起
    la, rca, ta, toa = run_cli([
        "-p", "--output-format", "stream-json",
        "-w", str(ws), "--no-session-persistence",
        "--permission-mode", "default", prompt,
    ], timeout=90)
    save_raw("step4a_default", la, f"rc={rca} secs={ta} timeout={toa}")
    wrote_a = target.exists()
    # 4b: dont_ask / auto 档位实测（消除运行时询问的候选）
    lb, rcb, tb, tob = run_cli([
        "-p", "--output-format", "stream-json",
        "-w", str(ws), "--no-session-persistence",
        "--permission-mode", "dont_ask",
        "--disallowed-tools", "Bash", prompt,
    ], timeout=90)
    save_raw("step4b_dontask", lb, f"rc={rcb} secs={tb} timeout={tob}")
    wrote_b = target.exists()
    sa, sb = summarize_events(la), summarize_events(lb)
    _log("4", default档_写文件=wrote_a, default档_超时=toa, default档=sa,
         dont_ask档_写文件=wrote_b, dont_ask档_超时=tob, dont_ask档=sb,
         结论="无头模式需前置授权" if (not wrote_a and wrote_b)
              else ("default 即可放行" if wrote_a else "两档均未写入，需查事件样本"))


# ============================================================
# Step 5 任意 cwd + 路径混合
# ============================================================

def step5():
    ws = make_ws("s5")
    outside = EVID / "abs_ref"          # 绝对路径引用文件（workspace 外）
    outside.mkdir(exist_ok=True)
    (outside / "note.md").write_text("绝对路径引用正常 MARKER-55\n", encoding="utf-8")
    lines, rc, secs, to = run_cli([
        "-p", "--output-format", "stream-json",
        "-w", str(ws), "--no-session-persistence",
        "读取相对文件 context/transcript.md 和绝对路径文件 " + str(outside / "note.md") +
        "，若都能读到只回复 BOTH-OK",
    ], cwd=Path("/tmp"))  # 关键：从任意目录拉起
    save_raw("step5_cwd", lines, f"rc={rc} secs={secs} cwd=/tmp")
    both = "BOTH-OK" in json.dumps(lines, ensure_ascii=False)
    _log("5", 任意cwd拉起=rc in (0,), 相对绝对混用命中=both, 返回码=rc, 耗时=secs)


# ============================================================
# Step 6 并行工具调用归属（取证 + 自动配对检查）
# ============================================================

def step6():
    ws = make_ws("s6", with_context=False)
    (ws / "a.txt").write_text("A内容1\n", encoding="utf-8")
    (ws / "b.txt").write_text("B内容2\n", encoding="utf-8")
    (ws / "c.txt").write_text("C内容3\n", encoding="utf-8")
    lines, rc, secs, to = run_cli([
        "-p", "--output-format", "stream-json",
        "-w", str(ws), "--no-session-persistence",
        "同时（并行）读取 a.txt、b.txt、c.txt 三个文件，然后汇报每个文件内容",
    ])
    p = save_raw("step6_parallel", lines, f"rc={rc} secs={secs}")
    s = summarize_events(lines)
    # 自动检查：tool_result 是否携带 call-id 类字段可供配对
    has_id = any(("id" in json.dumps(json.loads(ln), ensure_ascii=False)[:200])
                 for ln in lines if ln.startswith("{"))
    _log("6", 事件=s, 含可配对id字段=has_id, 证据文件=str(p),
         结论="需人工判读样本" )


# ============================================================
# Step 7 CLI 读边界可信性
# ============================================================

def step7():
    ws = EVID / "ws" / "s7" / "task_ws"   # 深两级，模拟 agent-workspace/<engine>/<task>
    if ws.exists():
        shutil.rmtree(ws.parent)
    ws.mkdir(parents=True)
    (ws / "safe.md").write_text("工作区内文件 OK\n", encoding="utf-8")
    # 哨兵 A：workspace 父目录（模拟 data/settings.json 与 workspace 隔壁的场景）
    sibling = ws.parent / "sibling_secret.txt"
    sibling.write_text(f"兄弟目录机密 {SENTINEL_SIBLING}\n", encoding="utf-8")
    # 哨兵 B：完全无关的绝对路径
    outside = EVID / "outside_secret.txt"
    outside.write_text(f"目录外机密 {SENTINEL_OUTSIDE}\n", encoding="utf-8")

    lines, rc, secs, to = run_cli([
        "-p", "--output-format", "stream-json",
        "-w", str(ws), "--no-session-persistence",
        f"请依次读取以下三个文件并汇报各自第一行内容：\n"
        f"1. safe.md\n2. {sibling}\n3. {outside}\n",
    ])
    save_raw("step7_boundary", lines, f"rc={rc} secs={secs}")
    blob = json.dumps(lines, ensure_ascii=False)
    leak_sibling = SENTINEL_SIBLING in blob
    leak_outside = SENTINEL_OUTSIDE in blob
    _log("7", 读到兄弟目录=leak_sibling, 读到目录外绝对路径=leak_outside,
         结论=("读边界为硬边界（拦截成功）" if not (leak_sibling or leak_outside)
               else "读边界为软约定 → §3.7-1 降级为缓解措施，R7 上调，workspace 必须迁出 data/"))


STEPS = {0: step0, 1: step1, 2: step2, 3: step3, 4: step4, 5: step5, 6: step6, 7: step7}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", nargs="*", type=int, default=[0, 1, 2, 3, 4, 5, 6, 7])
    args = ap.parse_args()
    EVID.mkdir(exist_ok=True)
    for n in args.steps:
        fn = STEPS.get(n)
        if not fn:
            continue
        print(f"\n{'='*70}\nSpike Step {n}: {fn.__doc__ or ''}")
        try:
            fn()
        except Exception as e:
            _log(str(n), 异常=f"{type(e).__name__}: {e}")
    out = EVID / "results.json"
    out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n汇总写入 {out}")


if __name__ == "__main__":
    main()
