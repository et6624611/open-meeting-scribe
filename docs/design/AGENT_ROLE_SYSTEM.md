---
title: "Agent 角色系统设计与实施计划"
description: "从硬编码提示词迁移到基于 .md 文件的 Agent 角色工作区，支持预定义角色开箱即用、用户 fork 自定义、场景间自由切换。分三阶段渐进实施。"
tags: ["agent", "role", "prompt", "workspace", "design", "implementation-plan"]
created_at: "2026-09-15"
updated_at: "2026-09-17"
version: "1.1.0"
author: "wangyongliang"
status: "implemented"
category: "design"
related_docs: ["ADR-0017", "ARCHITECTURE.md", "design/DESIGN_DECISIONS.md"]
---

# Agent 角色系统设计与实施计划

> 将 AI 行为定义从 Python 硬编码常量迁移到 `.md` 文件工作区，通过预定义角色 + 用户自定义实现「开箱即用 + 无限定制」的 Agent 体验。
> 配套架构决策：[ADR-0017](../adr/0017-agent角色系统从硬编码提示词到md工作区.md)

## 1. 问题背景

### 1.1 现状

当前系统的 AI 行为由 4 个 Python 字符串常量硬编码定义：

| 提示词 | 位置 | 用途 |
|--------|------|------|
| `CHAT_SYSTEM_PROMPT` | `app/routers/chat.py` | AI 对话助手的人格与能力边界 |
| `SYSTEM_PROMPT` | `core/summarize.py` | 纪要生成的结构化模板 |
| `TITLE_SYSTEM_PROMPT` | `core/summarize.py` | 会议标题生成 |
| `SUMMARY_SYSTEM_PROMPT` | `core/realtime_summary.py` | 实时增量总结 |

设置界面（`SettingsView.vue` 提示词分类）对这些提示词**只读展示**，用户无法修改。

### 1.2 痛点

1. **单一角色无法适应多场景**：会议纪要、深度分析、学习辅导等不同场景需要不同的 AI 人格和输出风格，但系统只有一套固定行为
2. **用户无法定制**：高级用户希望调整 AI 的回复风格、输出模板、关注维度，但提示词锁死在代码中
3. **开发者迭代成本高**：每次调整提示词都需要修改 Python 代码、重启服务，无法快速实验

### 1.3 目标

- **预定义角色保底**：零配置即可使用经过调优的专业角色
- **用户自定义延伸**：基于预定义角色 fork 编辑，创建个性化角色
- **场景自由切换**：不同会话/任务可绑定不同角色，适应不同使用场景
- **渐进式加载**：按需加载角色定义文件，不浪费 context window

## 2. 角色分类与预定义

### 2.1 会议类（Meeting）

#### 📋 会议纪要员 `meeting-minutes`

**定位**：忠实记录者，结构化输出优先。

```markdown
# 角色定义

你是一位专业的会议纪要员。核心职责是将会议对话转化为准确、结构化的书面记录。

## 核心原则
- 忠于原文，绝不编造
- 内容不足时如实说明
- 识别语音识别错误并标注 [待确认]

## 输出风格
- 严格结构化（概要 → 结论 → 待办 → 议题归类）
- 简洁书面语，去除口语化表达
- 保留关键数据和人名

## 回复风格
- 极简，不寒暄
- 用户问纪要相关问题时直接引用原文
- 不主动分析或评价会议内容
```

**附带文件**：
- `summary-template.md` — 纪要输出模板（替代 `SYSTEM_PROMPT` 常量）

#### 📊 会议分析师 `meeting-analyst`

**定位**：深度分析者，关注决策模式与潜在风险。

```markdown
# 角色定义

你是一位会议分析师。不仅记录发生了什么，更关注为什么发生、意味着什么、后续可能怎样。

## 核心能力
- 决策模式识别：谁在做决策？基于什么信息？
- 风险预警：哪些讨论中隐含了未被明确提出的风险？
- 发言分析：各参与者的关注点和立场差异
- 行动建议：基于会议内容给出可操作的后续建议

## 输出风格
- 分析性语言，善用「值得注意的是」「潜在风险在于」
- 分层表达：事实 → 解读 → 建议
- 适当使用对比和关联

## 回复风格
- 主动提供多角度分析
- 用户问简单问题时也给出背景脉络
- 会指出会议中的矛盾点和未决事项
```

**附带文件**：
- `analysis-style.md` — 分析维度定义
- `insight-rules.md` — 洞察提取规则

#### 🎯 会议引导师 `meeting-coach`

**定位**：效率关注者，实时关注会议进程与质量。

```markdown
# 角色定义

你是一位会议引导师。关注会议效率与质量，帮助用户把控议程节奏、发现讨论偏题、建议议程调整。

## 核心能力
- 议程偏离检测：讨论是否跑题？偏了多远？
- 时间分配建议：哪些议题讨论过多/过少？
- 参与度分析：是否有人被忽略或主导了对话？
- 决策推进：讨论陷入循环时提供推进建议

## 输出风格
- 引导性语言，善用提问而非断言
- 「是否可以考虑...」「注意到大家还没有讨论...」
- 温和但直接

## 回复风格
- 主动观察并反馈会议动态
- 适时提醒议程进度
- 在讨论僵持时提供结构化思考框架
```

**附带文件**：
- `feedback-template.md` — 反馈模板

### 2.2 学习型（Learning）

#### 📚 学习辅导员 `learning-tutor`

**定位**：知识转化者，将会议/讲座内容转化为可复习的学习材料。

```markdown
# 角色定义

你是一位学习辅导员。帮助用户从会议、讲座、研讨内容中提取知识要点，转化为可复习的学习材料。

## 核心能力
- 知识点提取：从对话中识别核心概念和关键论述
- 结构化笔记：将零散讨论整理为层次化的知识框架
- 复习题生成：基于内容生成自测题目
- 关联建议：推荐相关知识领域或深入方向

## 输出风格
- 教学性语言，清晰易懂
- 善用类比和举例解释复杂概念
- 知识点用编号和层级组织

## 回复风格
- 耐心、循序渐进
- 用户提问时先确认理解水平再调整深度
- 主动提供「延伸思考」方向
```

**附带文件**：
- `note-template.md` — 学习笔记模板
- `review-rules.md` — 复习提醒规则

#### 📖 深度阅读者 `deep-reader`

**定位**：批判性思考者，深度分析文本内容。

```markdown
# 角色定义

你是一位深度阅读者。帮助用户深入理解文本内容，进行批判性分析，建立知识关联。

## 核心能力
- 论点拆解：识别核心论点、论据和隐含假设
- 批判性评价：分析论证的强弱和逻辑漏洞
- 知识关联：将内容与更广泛的知识体系建立连接
- 摘要与提炼：不同压缩层级的内容概要

## 输出风格
- 学术性但不过于晦涩
- 「作者的核心论点是...」「这里的逻辑是...」
- 善用引用和对比

## 回复风格
- 深度优先于广度
- 鼓励用户提出质疑和反思
- 提供多视角解读
```

**附带文件**：
- `extraction-style.md` — 知识提取风格定义

## 3. 目录结构设计

```
data/
  agent/
    _roles/                              # 角色定义区
      # ── 预定义角色（系统内置）──
      _builtin/
        meeting-minutes/                 # 会议纪要员
          AGENT.md                       # 人格 + 能力边界（必须）
          summary-template.md            # 纪要输出模板（可选，管线阶段加载）
          todo-rules.md                  # 待办提取规则（可选）
        meeting-analyst/                 # 会议分析师
          AGENT.md
          analysis-style.md
          insight-rules.md
        meeting-coach/                   # 会议引导师
          AGENT.md
          feedback-template.md
        learning-tutor/                  # 学习辅导员
          AGENT.md
          note-template.md
          review-rules.md
        deep-reader/                     # 深度阅读者
          AGENT.md
          extraction-style.md

      # ── 用户自定义角色（从预定义 fork 而来）──
      # 用户通过管理界面创建，目录名即角色 ID
      my-budget-reviewer/
        _forked-from: meeting-minutes    # 溯源标记（纯文本文件）
        AGENT.md                         # 用户已编辑
        summary-template.md
      my-thesis-advisor/
        _forked-from: learning-tutor
        AGENT.md
```

### 3.1 AGENT.md 文件格式

每个角色的 `AGENT.md` 必须包含 YAML front matter：

```yaml
---
title: 会议纪要员
description: 专注于结构化纪要输出，忠实记录会议结论与待办
category: meeting
version: 1.0.0
tags: [纪要, 结构化, 待办提取]
---
```

正文为 Markdown 格式的角色定义，支持 `<role>`、`<capabilities>`、`<constraints>`、`<output_format>` 等 XML 标签划分语义区域（与现有 `CHAT_SYSTEM_PROMPT` 格式兼容）。

### 3.2 查找优先级

角色文件解析按以下优先级查找：

1. **用户自定义区**：`data/agent/_roles/{role_name}/`
2. **预定义区**：`data/agent/_roles/_builtin/{role_name}/`
3. **硬编码兜底**：Python 常量（仅在角色文件不存在时启用）

这保证了：用户 fork 的角色自动优先于预定义角色；预定义角色永远可用不会被意外覆盖。

## 4. 角色加载机制

### 4.1 新增核心模块：`core/agent_workspace.py`

```python
# 核心接口（伪代码）

def resolve_agent_role(
    session_id: str | None = None,
    task_id: str | None = None,
) -> dict:
    """
    解析当前应加载的角色定义。

    优先级：会话绑定 > 任务关联 > 全局默认（meeting-minutes）

    Returns:
        {
            "role_name": "meeting-minutes",
            "agent_md": "...(AGENT.md 内容)...",
            "extra_files": {
                "summary-template.md": "...(内容)...",
                "todo-rules.md": "...(内容)...",
            },
            "source": "builtin" | "custom",
        }
    """

def load_role_files(role_dir: Path) -> dict:
    """加载指定角色目录下的所有 .md 文件。"""

def list_roles() -> list[dict]:
    """列出所有可用角色（预定义 + 用户自定义），含元数据。"""

def fork_role(builtin_name: str, custom_name: str) -> Path:
    """从预定义角色 fork 为用户自定义角色。"""
```

### 4.2 上下文注入位置

在 `app/routers/chat.py` 的 chat 端点中，新增**维度 0**（角色定义加载），位于所有现有维度之前：

```
system_prompt 构建顺序：

[0] AGENT.md              ← 角色人格（替代硬编码 CHAT_SYSTEM_PROMPT）
[0+] 角色附带 .md 文件     ← 按需检索（summary-template 等）
[1] 任务数据               ← 现有：会议转写/纪要/待办
[2] 项目资料               ← 现有：项目文件关键词检索
[3] 页面上下文             ← 现有：build_page_context
[4] 对话历史               ← 现有：最近 10 轮
```

### 4.3 管线阶段的角色感知

`core/pipeline_runner.py` 的 Stage 2（纪要生成）同样需要角色感知：

```python
# 伪代码
def _run_stage2_for_task(task_id, task):
    role = resolve_agent_role(task_id=task_id)

    # 如果角色附带 summary-template.md，用它替代默认 SYSTEM_PROMPT
    summary_prompt = (
        role["extra_files"].get("summary-template.md")
        or SYSTEM_PROMPT  # 硬编码兜底
    )
    # ... 后续纪要生成使用 summary_prompt
```

### 4.4 角色解析优先级

```python
def resolve_agent_role(session_id=None, task_id=None):
    # 1. 会话级绑定（用户在 AI 面板手动切换了角色）
    if session_id:
        role = get_session_role(session_id)
        if role:
            return _load_role(role)

    # 2. 任务级关联（会议创建时选择的默认角色）
    if task_id:
        role = tasks.get(task_id, {}).get("role")
        if role:
            return _load_role(role)

    # 3. 全局默认
    return _load_role("meeting-minutes")
```

## 5. 角色切换 UI

### 5.1 AI 面板角色选择器

在 `AIPanel.vue` 的会话 Tab 区域下方增加角色标识 + 下拉选择器：

```
┌─────────────────────────────┐
│ 🗂 会话 1    🗂 会话 2   +  │  ← 现有 Tab 栏
│ 📋 会议纪要员          ▾    │  ← 新增：角色标识 + 下拉
├─────────────────────────────┤
│                             │
│   对话区域...               │
```

### 5.2 下拉菜单结构

```
┌──────────────────────────┐
│ ── 会议 ──               │
│  📋 会议纪要员      ✓    │  ← 当前选中
│  📊 会议分析师            │
│  🎯 会议引导师            │
│ ── 学习 ──               │
│  📚 学习辅导员            │
│  📖 深度阅读者            │
│ ── 我的 ──               │
│  💰 预算评审专家          │
│  🎓 论文导师              │
│ ────────────             │
│  ✏️ 管理角色...           │  ← 打开角色管理
└──────────────────────────┘
```

### 5.3 角色管理界面

在设置页面新增「角色管理」分类（替代现有只读的「提示词」分类）：

- 查看所有可用角色（预定义 + 自定义）
- 从预定义角色 fork 创建自定义角色
- 编辑自定义角色的 `.md` 文件（Markdown 编辑器）
- 删除自定义角色（预定义角色不可删除）
- 预览角色定义内容

## 6. 数据模型变更

### 6.1 会话数据

AI 会话存储新增角色绑定字段：

```json
{
  "session_id": "abc123",
  "role": "meeting-minutes",
  "role_source": "builtin",
  "created_at": "2026-09-15T10:00:00Z"
}
```

### 6.2 任务数据

`data/tasks/{task_id}.json` 新增可选字段：

```json
{
  "task_id": "xxx",
  "role": "meeting-analyst",
  ...
}
```

### 6.3 设置数据

`data/settings.json` 新增可选字段：

```json
{
  "default_role": "meeting-minutes",
  ...
}
```

## 7. 实施路径

### Phase 1 — 角色文件化（1-2 天）

**目标**：将 `CHAT_SYSTEM_PROMPT` 外化为 `.md` 文件，验证加载链路。

| 步骤 | 内容 | 涉及文件 |
|------|------|----------|
| 1.1 | 创建 `data/agent/_roles/_builtin/` 目录结构 | 文件系统 |
| 1.2 | 将 `CHAT_SYSTEM_PROMPT` 迁移为 `meeting-minutes/AGENT.md` | 新建 `.md` |
| 1.3 | 将 `SYSTEM_PROMPT`（纪要模板）迁移为 `meeting-minutes/summary-template.md` | 新建 `.md` |
| 1.4 | 新建 `core/agent_workspace.py`，实现 `resolve_agent_role()` 和 `load_role_files()` | 新建 Python |
| 1.5 | 修改 `app/routers/chat.py`：用 `resolve_agent_role()` 替代硬编码常量 | 修改 Python |
| 1.6 | 修改 `core/summarize.py`：纪要生成时优先读取角色的 `summary-template.md` | 修改 Python |
| 1.7 | 保留所有硬编码常量作为 fallback（角色文件不存在时使用） | 无变更 |

**验收标准**：
- [ ] 默认角色（meeting-minutes）的 AGENT.md 内容与原 `CHAT_SYSTEM_PROMPT` 等价
- [ ] 修改 AGENT.md 后无需重启服务即可生效
- [ ] 删除 AGENT.md 后系统自动回退到硬编码常量，不报错
- [ ] 现有所有 AI 对话功能不受影响

### Phase 2 — 预定义角色 + 切换（2-3 天）

**目标**：完成 5 个预定义角色，实现会话级角色切换。

| 步骤 | 内容 | 涉及文件 |
|------|------|----------|
| 2.1 | 创建 5 个预定义角色的 `.md` 文件 | `data/agent/_roles/_builtin/` |
| 2.2 | 新增 API：`GET /api/agent/roles`（列出可用角色） | `app/routers/` 新建或扩展 |
| 2.3 | 新增 API：`POST /api/agent/sessions/{id}/role`（切换会话角色） | 同上 |
| 2.4 | AI 会话数据新增 `role` 字段，持久化到磁盘 | `app/routers/chat.py` 或独立 store |
| 2.5 | `AIPanel.vue` 增加角色选择器 UI | 前端组件 |
| 2.6 | 前端调用角色列表 API，渲染下拉菜单 | 前端 API 层 |
| 2.7 | chat 端点根据 session role 加载不同 AGENT.md | `app/routers/chat.py` |
| 2.8 | i18n 语言包新增角色相关翻译 | `frontend/src/i18n/` |

**验收标准**：
- [ ] AI 面板显示当前角色名称，可下拉切换
- [ ] 切换角色后，下一次对话使用新角色的 AGENT.md
- [ ] 5 个预定义角色均可选择且行为差异化可感知
- [ ] 刷新页面后角色选择保持（持久化）

### Phase 3 — 角色管理（3-5 天）

**目标**：用户可 fork 预定义角色、编辑自定义角色。

| 步骤 | 内容 | 涉及文件 |
|------|------|----------|
| 3.1 | 新增 API：`POST /api/agent/roles/fork`（fork 预定义角色） | 后端 |
| 3.2 | 新增 API：`PUT /api/agent/roles/{name}/files/{filename}`（编辑角色文件） | 后端 |
| 3.3 | 新增 API：`DELETE /api/agent/roles/{name}`（删除自定义角色） | 后端 |
| 3.4 | 设置页面新增「角色管理」分类，替代只读的「提示词」分类 | `SettingsView.vue` |
| 3.5 | 角色管理界面：列表 + fork + 编辑 + 删除 | 前端组件 |
| 3.6 | Markdown 编辑器组件（用于编辑角色 `.md` 文件） | 前端组件 |
| 3.7 | fork 时复制所有 `.md` 文件并写入 `_forked-from` 标记 | 后端 |
| 3.8 | 删除自定义角色前检查是否被会话引用，给出提示 | 后端 + 前端 |

**验收标准**：
- [ ] 用户可从预定义角色 fork 出自定义角色
- [ ] 自定义角色的 `.md` 文件可在线编辑并实时生效
- [ ] 预定义角色不可删除、不可编辑
- [ ] 删除被引用的自定义角色时给出提示
- [ ] fork 标记（`_forked-from`）正确记录溯源信息

## 8. 与现有系统的兼容性

| 现有组件 | 影响 | 处理方式 |
|----------|------|----------|
| `CHAT_SYSTEM_PROMPT` 常量 | 变为 `_builtin/meeting-minutes/AGENT.md` | 保留为 fallback |
| `SYSTEM_PROMPT`（纪要） | 角色 `summary-template.md` 优先 | 保留为 fallback |
| `build_page_context` | 不受影响 | 页面上下文与角色正交 |
| `project_index.py` | 复用检索逻辑 | 角色附带 `.md` 可用同款关键词检索 |
| 设置页「提示词」分类 | 进化为「角色管理」 | Phase 3 替换 |
| `SYSTEM_PROMPTS` 注册表 | 只读展示保留 | 增加角色来源标注 |

## 9. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 用户编辑 `.md` 导致 AI 行为异常 | 中 | 中 | 提供「恢复默认」按钮；预定义角色不可修改 |
| 角色文件过多导致 context 溢出 | 低 | 高 | 始终加载仅 AGENT.md；附带文件按关键词检索，总量限制 3000 字符 |
| fork 后原预定义角色更新，用户版本不同步 | 中 | 低 | fork 时记录版本号；管理界面提示「有新版本可用」 |
| 角色切换后用户期望不一致 | 中 | 低 | 切换时显示角色能力摘要；提供「切换回上一角色」快捷操作 |

## 10. 后续演进方向

- **角色市场**：用户间分享自定义角色（导出/导入 `.md` 文件包）
- **任务自动匹配**：根据会议类型（技术评审/头脑风暴/1-on-1）自动推荐角色
- **角色组合**：一个会话中动态切换多个角色（如前半段用引导师、后半段用纪要员）
- **项目级角色默认值**：不同项目可设置不同的默认角色（如预算项目默认用「预算评审专家」）
