# 用量计量技术方案

> 状态：草案 v2 · 2026-09-12（去除商业订阅概念，重新定位为体验期用量管理）
> 依赖：AUTH_DESIGN.md（授权模型）、API_CONTRACTS.md（ASR/LLM 调用契约）
>
> **定位说明**：本项目为个人开发者维护的开源软件，不提供商业订阅服务。计量系统仅用于管理体验期用量，不涉及计费、资费、套餐等商业概念。

## 1. 设计目标

| 目标 | 说明 |
|------|------|
| 精确计量 | 按实际转写的音频分钟数计量，非按文件大小或请求次数 |
| 零侵入 | 计量逻辑与转写管线解耦，不改变现有 pipeline 调用签名 |
| 双轨并行 | 共享 proxy 用户走体验期配额、自持 Key 用户不计量（直接消耗自己的额度） |
| 实时可见 | 前端可随时查询本月已用 / 剩余 / 趋势 |
| 可审计 | 每次消耗都有不可篡改的日志记录 |

## 2. 计量模型

### 2.1 计量单位

| 服务 | 计量单位 | 说明 |
|------|----------|------|
| 批量转写（ASR） | 音频分钟（`audio_minutes`） | 从 `audio_duration` 秒换算，保留两位小数 |
| 实时转写（ASR） | 音频分钟 | 从 WebSocket 发送的 PCM 字节数换算 |
| 纪要生成（LLM） | **不单独计量** | 单次成本 < ¥0.05，打包进 ASR 分钟单价 |
| AI 对话（未来） | 次数 / token | 独立计量维度，本期不实现 |

### 2.2 计量公式

```
实际消耗 = audio_duration_seconds / 60

示例：
  32 分 17 秒的会议 → 32.28 分钟
  1 小时会议 → 60.00 分钟
```

### 2.3 配额规则（由开发者按需调整）

| 授权档位 | 月配额 | 说明 |
|------|--------|------|
| 体验期（free） | 300 分钟 | 唯一档位，由开发者根据 API 费用承担能力调整 |

自持 Key 用户不在此表，不计量。

## 3. 架构设计

```
┌──────────────────────────────────────────────────────────┐
│                     前端（状态栏 / 设置页）                │
│  GET /api/usage/summary  ←  本月汇总                     │
│  GET /api/usage/history  ←  逐日明细                     │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│                   app/routers/usage.py                    │
│  GET  /api/usage/summary   → 月度汇总（已用/剩余/百分比）  │
│  GET  /api/usage/history   → 按日明细（最近 90 天）        │
│  GET  /api/usage/check     → 配额预检（任务开始前调用）     │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│                    core/metering.py                       │
│                                                           │
│  record_usage()     ← 记录一次用量事件（追加 JSONL）        │
│  get_monthly_usage() ← 查询当月汇总                       │
│  get_daily_history() ← 查询逐日明细                       │
│  check_quota()      ← 预检剩余配额                        │
│  is_metered()       ← 判断当前用户是否需要计量              │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│                    数据存储                                │
│                                                           │
│  data/usage/                                              │
│  ├── usage-2026-09.jsonl    ← 按月分片的用量日志            │
│  ├── usage-2026-10.jsonl                                  │
│  └── ...                                                  │
│                                                           │
│  data/users.json                                          │
│  └── users[].subscription  ← 授权档位 + 配额信息           │
└──────────────────────────────────────────────────────────┘
```

## 4. 核心模块设计

### 4.1 `core/metering.py` — 计量引擎

```python
"""
core/metering.py — 用量计量

职责：
  1. 记录每次转写的用量事件（追加写入 JSONL）
  2. 按月汇总用量
  3. 预检配额是否充足
  4. 判断当前用户是否需要计量（自持 Key 则跳过）
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

USAGE_DIR = Path("data/usage")

# ── 授权配额（分钟/月）──
# 最终由运营配置，此处为默认值
TIER_QUOTAS = {
    "free": 300,    # 体验期
}


def is_metered() -> bool:
    """
    判断当前用户是否需要计量。

    不需要计量的情况：
      - 未登录（本地模式）
      - 自持 ASR API Key（用户自己承担费用）
      - 开发者共享 Key 未配置（回退到自持 Key 模式）

    Returns:
        True = 需要计量（消耗体验期配额）
        False = 不计量（用户自费或未启用共享服务）
    """
    from core.users import get_current_user
    from app.routers.settings import get_asr_config

    user = get_current_user()
    if not user:
        return False  # 未登录 = 本地模式，不计量

    asr_config = get_asr_config()
    # 如果 ASR Key 来自用户自行配置（非共享 proxy），不计量
    if asr_config.get("source") == "user":
        return False

    # 有授权信息且档位为有效档位 → 需要计量
    subscription = user.get("subscription", {})
    return subscription.get("tier") in TIER_QUOTAS


def record_usage(
    user_id: str,
    service: str,          # "asr_batch" | "asr_realtime" | "llm_summary"
    duration_seconds: float,
    task_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """
    记录一次用量事件。

    Args:
        user_id: 用户 ID
        service: 服务类型
        duration_seconds: 音频时长（秒）
        task_id: 关联的任务 ID（可选）
        metadata: 附加信息（模型名、厂商等）

    Returns:
        本次用量记录 {minutes, cumulative_monthly, remaining}
    """
    audio_minutes = round(duration_seconds / 60, 2)

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "service": service,
        "duration_seconds": round(duration_seconds, 1),
        "audio_minutes": audio_minutes,
        "task_id": task_id,
        "metadata": metadata or {},
    }

    # 追加写入当月 JSONL
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    log_path = USAGE_DIR / f"usage-{month_key}.jsonl"
    USAGE_DIR.mkdir(parents=True, exist_ok=True)

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    # 计算当月累计
    cumulative = get_monthly_usage(user_id, month_key)
    quota = _get_user_quota(user_id)
    remaining = max(0, quota - cumulative)

    logger.info(
        f"用量记录: user={user_id[:8]}, service={service}, "
        f"+{audio_minutes}min, 月累计={cumulative}min, 剩余={remaining}min"
    )

    return {
        "minutes": audio_minutes,
        "cumulative_monthly": cumulative,
        "remaining": remaining,
        "quota": quota,
    }


def get_monthly_usage(user_id: str, month_key: str | None = None) -> float:
    """
    查询某用户某月的累计用量（分钟）。

    Args:
        user_id: 用户 ID
        month_key: "2026-09" 格式，默认当月

    Returns:
        累计分钟数
    """
    if month_key is None:
        month_key = datetime.now(timezone.utc).strftime("%Y-%m")

    log_path = USAGE_DIR / f"usage-{month_key}.jsonl"
    if not log_path.exists():
        return 0.0

    total = 0.0
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if event.get("user_id") == user_id:
                total += event.get("audio_minutes", 0)

    return round(total, 2)


def get_daily_history(user_id: str, days: int = 30) -> list[dict]:
    """
    查询逐日用量明细。

    Returns:
        [{"date": "2026-09-05", "minutes": 45.5, "tasks": 3}, ...]
    """
    from collections import defaultdict

    now = datetime.now(timezone.utc)
    daily = defaultdict(lambda: {"minutes": 0.0, "tasks": 0})

    # 扫描最近 N 天的月份文件
    months_needed = set()
    for d in range(days):
        from datetime import timedelta
        day = now - timedelta(days=d)
        months_needed.add(day.strftime("%Y-%m"))

    for month_key in months_needed:
        log_path = USAGE_DIR / f"usage-{month_key}.jsonl"
        if not log_path.exists():
            continue
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if event.get("user_id") != user_id:
                    continue
                ts = event.get("timestamp", "")
                date_str = ts[:10]  # "2026-09-05"
                daily[date_str]["minutes"] += event.get("audio_minutes", 0)
                if event.get("task_id"):
                    daily[date_str]["tasks"] += 1

    # 转为列表并按日期排序
    result = [
        {"date": date, "minutes": round(v["minutes"], 1), "tasks": v["tasks"]}
        for date, v in sorted(daily.items())
    ]
    return result[-days:]  # 只返回最近 N 天


def check_quota(user_id: str, estimated_minutes: float = 0) -> dict:
    """
    配额预检。在任务开始前调用，判断是否有足够配额。

    Args:
        user_id: 用户 ID
        estimated_minutes: 预估消耗（可选，用于提前预警）

    Returns:
        {
            "allowed": bool,
            "remaining": float,
            "quota": float,
            "used": float,
            "warning": str | None,  # "low" | "critical" | None
        }
    """
    from core.users import get_user_by_id

    user = get_user_by_id(user_id)
    if not user:
        return {"allowed": True, "remaining": -1, "quota": -1, "used": 0, "warning": None}

    # 不需要计量的用户直接放行
    subscription = user.get("subscription", {})
    tier = subscription.get("tier")
    if tier not in TIER_QUOTAS:
        return {"allowed": True, "remaining": -1, "quota": -1, "used": 0, "warning": None}

    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    used = get_monthly_usage(user_id, month_key)
    quota = TIER_QUOTAS.get(tier, 0)
    remaining = max(0, quota - used)
    pct = remaining / quota if quota > 0 else 0

    warning = None
    if pct < 0.1:
        warning = "critical"
    elif pct < 0.2:
        warning = "low"

    allowed = remaining > estimated_minutes

    return {
        "allowed": allowed,
        "remaining": round(remaining, 1),
        "quota": quota,
        "used": round(used, 1),
        "warning": warning,
    }


def _get_user_quota(user_id: str) -> int:
    """获取用户的月度配额"""
    from core.users import get_user_by_id
    user = get_user_by_id(user_id)
    if not user:
        return 0
    tier = user.get("subscription", {}).get("tier", "free")
    return TIER_QUOTAS.get(tier, 0)
```

### 4.2 计量钩子 — 在哪里调用

#### 批量转写完成后

在 `app/store.py` 的 `run_pipeline_task()` 中，转写成功后记录用量：

```python
# store.py:run_pipeline_task() — 转写完成后
if result.get("audio_duration"):
    from core.metering import is_metered, record_usage
    if is_metered():
        from core.users import get_current_user
        user = get_current_user()
        if user:
            record_usage(
                user_id=user["id"],
                service="asr_batch",
                duration_seconds=result["audio_duration"],
                task_id=task_id,
                metadata={"model": "paraformer-v2", "provider": "DashScope"},
            )
```

#### 实时转写结束时

在 `app/routers/record.py` 的停止录制端点中，根据录制时长记录：

```python
# record.py:stop_recording — 实时录制结束
if recording_duration > 0:
    from core.metering import is_metered, record_usage
    if is_metered():
        from core.users import get_current_user
        user = get_current_user()
        if user:
            record_usage(
                user_id=user["id"],
                service="asr_realtime",
                duration_seconds=recording_duration,
                task_id=task_id,
                metadata={"model": "qwen-audio-3.0-asr-flash-streaming"},
            )
```

#### 配额预检 — 任务开始前

在上传/录制端点中，开始前检查配额：

```python
# record.py 或 upload 端点
from core.metering import is_metered, check_quota
from core.users import get_current_user

user = get_current_user()
if user and is_metered():
    quota_check = check_quota(user["id"])
    if not quota_check["allowed"]:
        # 返回 402 或自定义错误码
        raise HTTPException(
            status_code=402,
            detail={
                "error": "quota_exhausted",
                "remaining": quota_check["remaining"],
                "message": f"本月转写额度已用完（剩余 {quota_check['remaining']} 分钟）",
            }
        )
```

### 4.3 用量查询 API

新建 `app/routers/usage.py`：

```python
"""
app/routers/usage.py — 用量查询 API

端点：
  GET /api/usage/summary   → 本月汇总
  GET /api/usage/history   → 逐日明细
  GET /api/usage/check     → 配额预检
"""

from fastapi import APIRouter
from core.users import get_current_user
from core.metering import get_monthly_usage, get_daily_history, check_quota, TIER_QUOTAS

router = APIRouter(prefix="/api/usage", tags=["用量"])


@router.get("/summary")
def usage_summary():
    """本月用量汇总（底部状态栏用）"""
    user = get_current_user()
    if not user:
        return {"metered": False, "message": "未登录"}

    from core.metering import is_metered
    if not is_metered():
        return {"metered": False, "message": "自持 Key，不计量"}

    from datetime import datetime, timezone
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    used = get_monthly_usage(user["id"], month_key)

    subscription = user.get("subscription", {})
    tier = subscription.get("tier", "free")
    quota = TIER_QUOTAS.get(tier, 0)
    remaining = max(0, quota - used)
    pct = round(remaining / quota * 100) if quota > 0 else 0

    return {
        "metered": True,
        "tier": tier,
        "month": month_key,
        "quota": quota,
        "used": round(used, 1),
        "remaining": round(remaining, 1),
        "percentage": pct,
    }


@router.get("/history")
def usage_history(days: int = 30):
    """逐日用量明细（设置页图表用）"""
    user = get_current_user()
    if not user:
        return {"history": []}
    return {"history": get_daily_history(user["id"], days)}


@router.get("/check")
def quota_check(estimated_minutes: float = 0):
    """配额预检"""
    user = get_current_user()
    if not user:
        return {"allowed": True, "metered": False}

    result = check_quota(user["id"], estimated_minutes)
    result["metered"] = True
    return result
```

### 4.4 用户数据扩展

在 `data/users.json` 的用户对象中增加 `subscription` 字段：

```json
{
  "id": "uuid",
  "name": "张三",
  "subscription": {
    "tier": "personal",
    "started_at": "2026-09-01T00:00:00Z",
    "expires_at": "2026-10-01T00:00:00Z"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `tier` | `"free"` | 授权档位（当前仅体验期） |
| `started_at` | ISO 8601 | 授权开始时间 |
| `expires_at` | ISO 8601 | 到期时间（free 为 null） |

**向后兼容**：没有 `subscription` 字段的用户视为 `tier: "free"`。

## 5. 自持 Key 用户的判定

### 5.1 判定逻辑

```
用户是否需要计量？
├── 未登录 → 否（本地模式）
├── 已登录
│   ├── subscription.tier ∈ 有效档位
│   │   ├── ASR Key 来源 = "shared_proxy" → 是（消耗体验期配额）
│   │   └── ASR Key 来源 = "user" → 否（用户自费）
│   └── 无 subscription → 否（视为自持 Key）
```

### 5.2 Key 来源标记

在 `app/routers/settings.py` 中，保存设置时标记 Key 来源：

```python
# settings.py — 保存 ASR 配置时
def save_asr_config(config: dict):
    config["source"] = "user"  # 用户自行配置
    ...

# 共享 proxy Key 在启动时标记
def get_asr_config() -> dict:
    ...
    if not settings_has_asr:
        config["source"] = "shared_proxy"  # 开发者共享 proxy
    return config
```

## 6. 前端展示

### 6.1 底部状态栏

```
┌──────────────────────────────────────────────────────────┐
│  ● DASHSCOPE 已连接    本月剩余 4h 32m ▓▓▓▓▓▓▓▓░░ 75%   │
└──────────────────────────────────────────────────────────┘
```

- **自持 Key 用户**：显示"自持 API Key · 不受限"，不显示进度条
- **共享 proxy 用户**：显示剩余时长 + 百分比进度条
- **颜色编码**：
  - 绿色（> 50%）：`oklch(0.7 0.15 145)`
  - 黄色（20-50%）：`oklch(0.75 0.15 85)`
  - 红色（< 20%）：`oklch(0.65 0.2 25)`

### 6.2 设置页 — 用量面板

在设置页增加「用量与配额」卡片：

```
┌─────────────────────────────────────────────┐
│  用量与配额                                  │
│                                              │
│  本月已使用          12h 28m / 25h           │
│  ▓▓▓▓▓▓▓▓░░░░░░░░  50%                     │
│                                              │
│  ┌─ 最近 7 天 ─────────────────────────┐    │
│  │  9/1  ██ 45min                      │    │
│  │  9/2  ████ 120min                   │    │
│  │  9/3  █ 15min                       │    │
│  │  9/4  ██████ 180min                 │    │
│  │  9/5  ██ 60min                      │    │
│  │  9/6  ███ 90min                     │    │
│  └─────────────────────────────────────┘    │
│                                              │
│  当前授权：体验期                            │
│  到期时间：2026-10-01                         │
└─────────────────────────────────────────────┘
```

### 6.3 前端 API 调用

```javascript
// 底部状态栏 — 页面加载时 + 每次转写完成后刷新
async function refreshUsageBar() {
  const res = await fetch('/api/usage/summary');
  const data = await res.json();

  const usageEl = document.getElementById('usage-indicator');
  if (!data.metered) {
    usageEl.textContent = '自持 API Key · 不受限';
    return;
  }

  const hours = Math.floor(data.remaining / 60);
  const mins = Math.round(data.remaining % 60);
  const timeStr = hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;
  const color = data.percentage > 50 ? 'green' : data.percentage > 20 ? 'yellow' : 'red';

  usageEl.innerHTML = `
    本月剩余 ${timeStr}
    <span class="usage-bar ${color}">
      <span style="width: ${data.percentage}%"></span>
    </span>
  `;
}
```

## 7. 数据流全景

```
用户点击「开始录制」
        │
        ▼
  ┌─ 配额预检 ─┐
  │ check_quota │─── 额度不足 → 返回提示 + 引导配置自有 Key
  └──────┬──────┘
         │ 通过
         ▼
  ┌─ 录制/上传 ─┐
  │  audio 管线  │
  └──────┬──────┘
         │
         ▼
  ┌─ 转写完成 ─┐
  │ audio_duration 已知
  │
  │ is_metered()?
  │   ├─ Yes → record_usage(user_id, duration)
  │   └─ No  → 跳过
  └──────┬──────┘
         │
         ▼
  ┌─ 前端刷新 ─┐
  │ refreshUsageBar()
  │ → GET /api/usage/summary
  │ → 更新底部状态栏
  └─────────────┘
```

## 8. 实施计划

| 阶段 | 内容 | 文件 | 优先级 |
|------|------|------|--------|
| **M1** | 计量引擎 | `core/metering.py` | P0 |
| **M2** | 批量转写钩子 | `app/store.py` | P0 |
| **M3** | 实时录制钩子 | `app/routers/record.py` | P0 |
| **M4** | 用量查询 API | `app/routers/usage.py` | P0 |
| **M5** | 配额预检 | `app/routers/record.py` + upload | P1 |
| **M6** | 底部状态栏展示 | `app/static/index.html` | P1 |
| **M7** | 设置页用量面板 | `app/static/index.html` | P2 |
| **M8** | 用户授权字段 | `core/users.py` | P1 |
| **M9** | Key 来源标记 | `app/routers/settings.py` | P1 |

建议先做 M1-M4（核心计量 + 查询），验证数据准确性后再做 M5-M9（管控 + 展示）。

## 9. 开放问题（已决策）

| # | 问题 | 决策结论 |
|---|------|----------|
| 1 | 实时转写的计量时机：按录制时长 or 按实际发送到 ASR 的字节数？ | **先按录制时长**，后续优化为字节数 |
| 2 | 体验期额度用尽后，是否允许用户用自己的 Key 继续？ | **允许**，在额度用尽提示中引导配置自有 Key |
| 3 | 协作授权共享池如何扣减？先扣共享还是先扣个人？ | **v1 暂不实现共享池**，后续按需设计 |
| 4 | 月度额度是否跨月清零？是否支持累积？ | **按月度额度处理，跨月清零**，后续可加「溢出结转」 |
| 5 | 是否需要用量异常告警（单日突增）？ | **v1 不做风控**，先观察数据分布 |

## 10. 与现有系统的集成点

| 现有模块 | 集成方式 | 改动量 |
|----------|----------|--------|
| `app/store.py` | 转写完成后调用 `record_usage()` | +5 行 |
| `app/routers/record.py` | 录制结束时调用 `record_usage()`；开始前调用 `check_quota()` | +10 行 |
| `app/routers/settings.py` | 保存 Key 时标记 `source` | +3 行 |
| `core/users.py` | 用户对象增加授权字段 | +10 行 |
| `app/server.py` | 注册 `usage` router | +2 行 |
| `app/static/index.html` | 底部状态栏 + 设置页面板 | +80 行 |

总改动量约 110 行核心代码 + 200 行 `core/metering.py` 新模块。
