---
title: "洞察台 Board Spec v0 草案"
description: "洞察台从多卡片模式回归单页总览板（Insight Board）的内容规格契约 v0：LLM 输出结构化 Board Spec，应用持有 HTML 模板确定性渲染，定义 zone/cell 模型、begin_time 交互契约、修订协议与卡片集迁移映射。"
tags: ["insight-board", "board-spec", "ai-insights", "design", "adr"]
created_at: "2026-09-28"
updated_at: "2026-09-28"
version: "0.3.0"
author: "wangyongliang"
status: "draft"
category: "design"
related_docs: ["API_CONTRACTS.md"]
---

# 洞察台 Board Spec v0 草案

> 状态：**设计草案 + PoC**。PoC 页面见 `docs/insight-board-poc/index.html`（用真实会议
> 「财务单据与主数据对接接口方案讨论」的 10 张洞察卡收敛成的板）。
> 本文档只定义契约，不含工程实施；实施属于 Phase 2/3。

## 1. 动机

多卡片洞察模式带来信息焦虑：10 张按时间平行罗列的卡片，实际只覆盖 4 个主题，
重复与碎片把"综合成全局"的认知负担转嫁给了用户。方向是把洞察台从「卡片流」
升级为「一块持续演化的板」：

- 用户打开洞察台，第一眼是**这场会现在长什么样**（一张板），不是一叠待处理消息；
- 卡片降级为板的细节层（区域下钻），通知语义从"来新卡了"变为"板有更新"。

渲染介质的关键决策：**LLM 拥有板的内容规格（Board Spec，纯 JSON），应用拥有板的
HTML（模板 + 设计令牌 + 交互契约）**。不允许 LLM 直接生成 HTML——安全（注入面）、
主题跟随（10 套 OKLCH 令牌）、转写定位交互、本地小模型 token 预算四条约束都指向这个分工。

## 2. 设计原则

0. **图主导（v0.2 定调）**：板的主体是视觉 cell（`flow` / `map` / `diagram`），每个 zone
   的主视觉恰好一个、占满区域宽度；文本 cell（`gaps` / `actions` / `note`）一律降级为
   折叠详情层，默认隐藏，用户主动展开才可见。zone summary 仅作为一行弱文字存在。
1. **板是指针，不是档案**：不追求板上信息自包含。盲点清单、行动建议、图注提问等
   文本信息允许“不在板上”，信息由 **AI 对话**补齐——用户对着板子提问就是消费这些细节的
   主路径（上下文注入已覆盖：zone summary + 折叠层内容均进 chat 上下文）。
2. **生成能力不是软件约束**：spec 不为弱模型做向下简化设计；模型档位决定生成质量，
   用户自选云端/本地承担能力差异。软件侧只做**校验与容错**（schema 不合则整次修订丢弃、
   板保持上一 revision），不做降级生成。
3. **Spec 是数据，不是文档**：所有字段为纯文本/结构化值，禁止内嵌 HTML/Markdown 标记；渲染器直接文本消费（自动转义），无需 sanitize 复杂语法。
4. **布局所有权在应用**：spec 中没有任何坐标、样式、宽度指令；分区如何排布由渲染器决定。
   ——**v0.3 定调**：① 板为**单列纵向流，全屏不加多栏**（zone 排序即叙事序，多栏把线性叙事
   切成 Z 字扫描；且主视觉 flow 阶段卡需要全幅宽度，两栏会把图挤到内部横滚；参照决策流面板
   760px 单栏先例，全屏只增加留白不增加列）；② 纵向过长由**吸顶区域导航**解决而非分栏：
   sticky 一条 zone chips（状态点 + 区域短名），点击锚点平滑滚动（zone 需 `scroll-margin-top`
   防遮挡），scroll-spy 高亮当前区——导航条即板的缩略图，chip 的状态点一眼呈现全局健康度。
5. **每个信息可溯源**：zone 携带 `origin`（来源洞察消息 id 列表），cell 级条目可携带 `begin_time`（跳回转写原文）。
6. **增量修订优先**：全量板文档 + 区域级 patch 操作并存；LLM 修订时只重生成变化的 zone。
7. **收敛是生成侧责任**：同主题新洞察 → `upsert_zone` 更新既有区域，而不是新建区域。这是只读累进 Phase 1（提示词去重约束）的机制化升级。

## 3. 顶层结构

```json
{
  "kind": "insight-board",
  "spec_version": "0.1",
  "task_id": "913942e9-…",
  "revision": 4,
  "phase": "post_meeting",
  "header": {
    "title": "财务单据与主数据对接接口方案讨论",
    "meeting_date": "2026-09-24",
    "summary": "接口方案背后的三类治理断点正在收敛：主数据权威源、预算控制权、单据反写闭环。",
    "stats": { "zones": 4, "open_questions": 14, "actions": 9, "merged_cards": 10 }
  },
  "zones": [ … ]
}
```

| 字段 | 说明 |
|---|---|
| `revision` | 板的修订号，每次状态修订 +1；前端「板已更新」弱提示的依据（替代未读计数） |
| `phase` | `meeting`（会中演化）/ `post_meeting`（会后收敛定稿） |
| `header.summary` | 一句话全局态势，由生成侧维护 |
| `stats.merged_cards` | 本板由多少张历史卡片收敛而来（迁移与累进的可见证据） |

## 4. Zone（区域）

Zone 是板的一级分区，**按主题聚类而非按时间**；zone 数组顺序即叙事序（按主题重要性/演化程度排列，
渲染器不得重排）。一个会议板建议 3–7 个 zone。

```json
{
  "id": "z-master-data",
  "title": "主数据一致性",
  "status": "open",
  "maturity": "forming",
  "summary": "PMS 与 ES 双编码体系并存，权威源与同步机制未定。",
  "cells": [ … ],
  "origin": ["insight-1727…-3", "insight-1727…-4", "insight-1727…-2"],
  "updated_at": 1759043817000
}
```

| 字段 | 语义 |
|---|---|
| `status` | `open`（讨论中，存在未决盲点）/ `evolving`（AI 已修订过）/ `settled`（已收敛，可归档）。渲染为状态点，**这是板上唯一的"待办感"信号**，替代卡片未读角标 |
| `maturity` | `draft` / `forming` / `confirmed`——该主题认知的成熟度（会议场景特有：区分"刚冒头"和"已聊透"） |
| `summary` | 区域当前理解的一句话，随修订更新 |
| `origin` | 来源洞察消息 id 数组。多个 id = 多卡合一的收敛证据；下钻"演化历史"时的锚点 |

## 5. Cell 类型（v0 共 6 种，分两层）

**主视觉层（每 zone 恰好一个，默认全幅展示）**：`flow` / `map` / `diagram`
**折叠详情层（默认隐藏，主动展开可见）**：`gaps` / `actions` / `note`

zone 的 `cells` 数组中第一个主视觉类型的 cell 即该 zone 的视觉主体；若存在多个主视觉
cell，渲染器取第一个为主、其余进折叠层。生成侧提示词应约束：每 zone 只产出一个主视觉。

### 5.1 `flow` — 阶段流程（主视觉，承接现阶段卡画布）

```json
{
  "kind": "flow",
  "stages": [
    { "name": "准入审批", "steps": [
      { "label": "PMS 完成资质审核", "begin_time": 840000 },
      { "label": "ES 侧状态同步？", "begin_time": null, "pending": true }
    ]}
  ]
}
```

- `begin_time`（毫秒）：点击跳回转写原文，**契约与现画布 `@@ms` 标记一致**；无对应时间戳则 `null`。
- `pending: true`：待确认节点，渲染为虚线/问号样式（保留"允许留白"的盲点表达）。

### 5.2 `gaps` — 盲点与开放问题

```json
{
  "kind": "gaps",
  "items": [
    { "question": "供应商主数据的权威源是 ES 还是 PMS？", "begin_time": 903000, "resolved": false }
  ]
}
```

洞察台首要定位（盲点揭示）的落点。`resolved` 支持会中→会后的勾选闭环。

### 5.5 `actions` — 行动建议（折叠层）

```json
{
  "kind": "actions",
  "items": [
    { "text": "付款单提交前增加「ES 编码-银行信息」联合校验", "owner": null, "begin_time": null }
  ]
}
```

### 5.2 `diagram` — 通用图（主视觉，Mermaid 源码直渲）

```json
{ "kind": "diagram", "source": "flowchart TD\n  A[准入审批] -->|无事件| B[ES 主数据]", "format": "mermaid" }
```

承载 `flow` / `map` 表达不下的发散结构（泳道、时序、思维导图、甘特），由现有
`MermaidDiagram.vue` 渲染——现有 Mermaid 管线投资在此升格为一等公民而非兑底。
约束：`format` 枚举仅 `"mermaid"`；渲染失败（语法错误）时该 cell 降级为折叠层
「图源码」条目，不影响整 zone。

### 5.3 `map` — 关系结构（主视觉，迷你 nodes/edges）

```json
{
  "kind": "map",
  "nodes": [
    { "id": "pms", "label": "PMS 编码", "begin_time": 461000 },
    { "id": "es",  "label": "ES 主数据", "begin_time": null }
  ],
  "edges": [
    { "from": "pms", "to": "es", "label": "无双向同步", "kind": "broken" }
  ]
}
```

`kind: broken`（断裂）/ `link`（正常关联）/ `dashed`（假设/待确认）。渲染由应用持有
（CSS 排布 + SVG 连线），**不引入布局引擎**——适合少量节点的关系表达，复杂结构用 `diagram`。
这是旧 `graph` 字段（InsightGraph 双轨）的收敛替代。

### 5.4 `gaps` — 盲点与开放问题（折叠层）

```json
{ "kind": "note", "text": "「控」字在讨论中高频出现，但从未有人定义「控」的执行主体——这是巧合吗？" }
```

保留现提示词"提问式图注"的产品性格，纯文本，不渲染 Markdown。

## 6. 修订协议（Phase 2 的接口契约雏形）

全量文档之外，分析端点未来输出**区域级操作**而非整板：

```json
{ "op": "upsert_zone",   "zone": { "id": "z-budget", … } }
{ "op": "replace_cells", "zone_id": "z-budget", "cell_ids": ["c1"], "cells": [ … ] }
{ "op": "settle_zone",   "zone_id": "z-master-data" }
```

- 应用侧按 `zone_id` 合并，`revision + 1`，被触碰的 zone 打「已更新」标记（变化可见，不静默改写）。
- LLM 每轮只输出变化的 zone；防抖动约束继承 Phase 1 提示词：**同主题 upsert，新主题才建 zone**；zone 总数超上限（7）时提示词要求先尝试合并。
- 不合 schema 的修订整次丢弃，板保持上一 revision（容错而非降级，见原则 2）。

## 7. 与现有资产的关系

| 现有资产 | 归宿 |
|---|---|
| `insights.json` 卡片集 | 可无损映射：每张卡的 diagram 阶段卡 → `flow` cell（主视觉），Mermaid 兑底图 → `diagram` cell（主视觉），body 提问 → `gaps`/`note`（折叠层），solution → `actions`（折叠层）。迁移脚本按标题语义聚类到 zone |
| `parseInsightFlow` 约束 Mermaid 解析器 | **退役**。阶段卡画布改为消费 `flow` cell（结构化数据，不再解析 DSL）；`@@ms` 契约平移为 `begin_time` 字段 |
| MermaidDiagram.vue | 保留并升格。作为 `diagram` cell（主视觉类型之一）的渲染器，LLM 仍写 Mermaid，主题跟随机制不变 |
| AI 对话改图（`lastViewedDiagram`） | 语义升级：对话上下文注入板 spec（zone 级），"把预算区改成泳道"= 生成 `replace_cells` 操作 |
| chat 上下文注入（`build_insights_context_block`） | 直接消费板 spec：zone summary + open gaps 天然就是全局摘要块，比"最近 5 张卡"质量高且更省 token |

## 8. 验证计划（本 PoC 要回答的问题）

1. **焦虑感是否消失**：打开 `insight-board-poc/index.html`，对比真实会议的 10 卡列表——图占主体、文本收进折叠层的信息姿态，是否比卡片流更愿意被凝视？
2. **图主导是否成立**：只盯主视觉（flow/map/diagram）扫一遍会议，能否不看任何文字就明白“这场会推到哪了”？折叠层默认隐藏后，是否有信息是“必须常显”的？（若有，说明 cell 分层需要调整）
3. **对话补齐是否顺手**：对着板向 AI 提问折叠层内容（如“预算区还有哪些没定的？”），验证 chat 上下文注入覆盖 zone 全部 cell（含折叠层）。

## 9. 未决事项

- zone 聚类的生成策略：由 LLM 直接维护 zone 树，还是应用侧按章节/关键词预聚类 + LLM 填充？（待定，与模型能力无关，是信息架构问题）
- `settled` 后的板快照与历史回放（origin 已留锚点，交互未设计）；
- 会中板与纪要页洞察 Tab 的信息分工（板放哪：独立视图 or 侧栏）；
- 折叠层的“弱提示”尺度：完全静默隐藏 vs 角标计数（如“?3”提示盲点待看），需真实会议体验后定；
- 导航升级位：总览模式（每区折叠为标题 + 主视觉缩略，点击展开单区），待板在真实会议中跑顺后评估。
