# -*- coding: utf-8 -*-
"""T1 验收：5 场真实转写跑规范遵循率 / Prompt conformance rate check."""
import json
import os
import subprocess
import tempfile
import urllib.request

# scripts/ 的上两级 = 仓库根 / two levels above scripts/ = repo root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(ROOT, "frontend")
MEETINGS = {
    "预算复盘": [
        (0, "先同步下Q3执行率数据，各部门汇报"),
        (1, "营销超支5主要是临时投放"),
        (2, "研发反而省了8个点"),
        (0, "省下来的钱建议调剂给营销做双11"),
        (1, "同意但要走审批流程"),
        (2, "我牵头周五前提交调剂申请"),
        (0, "好，另外年度滚动预测机制这次挂起"),
    ],
    "产品发布评审": [
        (0, "这次发版范围锁定三个功能"),
        (1, "搜索优化已完成灰度90%"),
        (2, "离线模式还有两个阻塞bug"),
        (0, "离线模式如果修不完就砍出本次范围"),
        (1, "同意，优先保搜索上线"),
        (2, "那我把bug转backlog，下版本处理"),
        (0, "好，明天十点发布窗口不变"),
    ],
    "供应商争议": [
        (0, "供应商交付延迟了三周，合同违约金条款要启动"),
        (1, "先确认延迟原因是物流还是产能"),
        (2, "对方说是原材料涨价导致停产"),
        (0, "不管什么原因合同第四条款都适用"),
        (1, "我发函主张违约金，抄送法务"),
        (2, "同时启动备选供应商询价"),
        (0, "两周内给我处理方案"),
    ],
    "团队重组": [
        (0, "想把客服和技术支持合并成一个体验组"),
        (1, "编制上没问题但两套排班系统不兼容"),
        (2, "合并后我需要双倍人力管排班"),
        (0, "先做两周双轨试运行"),
        (1, "试运行指标怎么定？"),
        (2, "建议用响应时长和满意度两个指标"),
        (0, "好，下周一开始试点"),
    ],
    "安全事件复盘": [
        (0, "昨晚的接口超时持续了47分钟，影响三百客户"),
        (1, "根因是连接池配置太小"),
        (2, "告警没触发是因为阈值设的120秒"),
        (0, "今天先把池子扩三倍"),
        (1, "明天上线新的监控阈值"),
        (2, "我写一份故障报告周五复盘会用"),
        (0, "客户补偿方案今天下午定"),
    ],
}
CHAPTERS = {
    "预算复盘": ["Q3执行率", "调剂决议", "遗留事项"],
    "产品发布评审": ["发布范围", "风险评估", "排期"],
    "供应商争议": ["延迟定责", "索赔路径", "备选方案"],
    "团队重组": ["合并方案", "试点设计", "指标定义"],
    "安全事件复盘": ["事故影响", "根因定位", "整改项"],
}

checker_tpl = """
import {{ parseInsightFlow }} from './src/utils/parseInsightFlow.ts'
import {{ readFile }} from 'node:fs/promises'
const d = JSON.parse(await readFile('{data}', 'utf8')).diagram
console.log(parseInsightFlow(d) ? 'CONFORM' : 'DEGRADE')
"""

ok = 0
for name, script in MEETINGS.items():
    lines = [
        {"text": t, "speaker_id": s, "begin_time": 60000 + i * 47000}
        for i, (s, t) in enumerate(script)
    ]
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/insights/analyze",
        data=json.dumps({"recent_lines": lines, "chapter_titles": CHAPTERS[name]}).encode(),
        headers={"Content-Type": "application/json"},
    )
    r = json.loads(urllib.request.urlopen(req, timeout=120).read())
    diagram = r.get("diagram", "")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"diagram": diagram}, f)
        dpath = f.name
    with tempfile.NamedTemporaryFile("w", suffix=".ts", delete=False, dir=FRONTEND) as f:
        f.write(checker_tpl.format(data=dpath))
        cpath = f.name
    out = subprocess.run(
        ["node", "--experimental-strip-types", os.path.basename(cpath)],
        capture_output=True, text=True, cwd=FRONTEND,
    )
    text = (out.stdout + out.stderr).strip()
    verdict = "ERROR: " + text.splitlines()[-1][:120] if out.returncode != 0 else text.strip().splitlines()[-1]
    os.unlink(cpath)
    os.unlink(dpath)
    if verdict == "CONFORM":
        ok += 1
    print(f"{name}: {verdict}")
    if verdict != "CONFORM":
        print("---- diagram ----")
        print(diagram[:400])
print(f"\n规范遵循率: {ok}/{len(MEETINGS)} = {ok/len(MEETINGS)*100:.0f}% (达标线 80%)")
