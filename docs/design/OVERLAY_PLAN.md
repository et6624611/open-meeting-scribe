---
title: "蒙版应用计划"
description: "基于蒙版类型与用户感知分析，梳理项目现有蒙版场景的一致性问题，提出统一设计规范与实施方案。"
tags: ["design", "overlay", "modal", "mask", "ux", "frontend"]
created_at: "2026-09-13"
updated_at: "2026-09-13"
version: "1.0.0"
author: "wangyongliang"
status: "published"
category: "design"
---

# 蒙版应用计划

> 本文档基于蒙版类型（硬阻断、软阻断、局部蒙版、无阻断）与用户感知影响的分析，
> 对 Open Meeting Scribe 项目中所有蒙版场景进行审计、归类，并提出统一的设计规范与实施方案。
> 与 [`DESIGN_DECISIONS.md`](./DESIGN_DECISIONS.md) 配合阅读——本文聚焦蒙版领域，后者记录全局设计决策。

## 1. 现有蒙版场景审计

### 1.1 场景清单

按**阻断强度**从高到低排列：

| # | 场景 | 选择器 | 文件 | 蒙版类型 | 背景不透明度 | z-index | 入场动效 | 退出路径 |
|---|------|--------|------|----------|-------------|---------|----------|----------|
| 1 | 登录遮罩 | `.login-overlay` | `auth.css` | **硬阻断**（不透明全屏） | `var(--bg)` 100% | `--z-toast` (1100) | opacity 0.3s | 返回按钮 + ESC 键帽 |
| 2 | 新建会议向导 | `.wizard-overlay` | `meeting-view.css` | 硬阻断 Modal | `oklch(0% 0 0 / 0.45)` | `--z-modal` (1000) | opacity 0.2s | 关闭按钮 |
| 3 | 说话人绑定引导 | `.spk-onboarding-overlay` | `meeting-view.css` | 硬阻断 Modal | `oklch(0% 0 0 / 0.4)` | `--z-modal` (1000) | fadein 0.2s + card 0.4s | 点击蒙版 + ESC |
| 4 | 知识库关联引导 | `.proj-onboarding-overlay` | `meeting-view.css` | 硬阻断 Modal | `oklch(0% 0 0 / 0.4)` | `--z-modal` (1000) | 复用上方动效 | 点击蒙版 + ESC |
| 5 | 删除确认 | `.delete-dialog-overlay` | `DeleteDialog.vue` (scoped) | 硬阻断 Modal | `oklch(0% 0 0 / 0.5)` | `--z-modal` (1000) | 无 | 点击蒙版 |
| 6 | 归档确认 | `.archive-dialog-overlay` | `ArchiveDialog.vue` (scoped) | 硬阻断 Modal | `rgba(0,0,0,0.5)` | `--z-modal` (1000) | 无 | 点击蒙版 |
| 7 | 说话人管理弹窗 | `.modal-overlay` | `speakers.css` | 硬阻断 Modal | `oklch(0% 0 0 / 0.4)` | 硬编码 1000 | opacity 0.2s | 关闭按钮 |
| 8 | 存在性警告 | `.rec-presence-overlay` | `recording-view.css` | 硬阻断 Modal | `oklch(0% 0 0 / 0.4)` | 硬编码 1000 | 无 | 按钮操作 |
| 9 | 放弃录音确认 | `.abandon-overlay` | `recording-view.css` | 硬阻断 Modal | `oklch(0% 0 0 / 0.35)` | `--z-modal` (1000) | opacity 0.2s | 按钮操作 |
| 10 | 隐私免责声明 | `.privacy-overlay` | `start-page.css` | 硬阻断 Modal | `oklch(0% 0 0 / 0.4)` | `--z-modal` (1000) | 无 | 按钮操作 |
| 11 | 重启确认 | `.restart-modal` | `update-panel.css` | 硬阻断 Modal | `oklch(0% 0 0 / 0.35)` | `--z-modal` (1000) | opacity 0.25s + scale | 按钮操作 |
| 12 | 录音结束过渡 | `.rec-ending-overlay` | `recording-view.css` | **局部蒙版**（区域内） | `var(--bg)` + `backdrop-filter: blur(4px)` | 10（局部上下文） | opacity 0.3s | 自动（状态驱动） |

### 1.2 按用户感知分类

| 感知类型 | 场景 | 匹配度评估 |
|----------|------|-----------|
| **"世界暂停了"**（硬阻断，必须回应） | 登录、存在性警告、放弃录音 | ✅ 合理——这些操作不可忽略 |
| **"请做决定"**（硬阻断，需要选择） | 删除确认、归档确认、隐私声明、重启确认 | ✅ 合理——破坏性操作需要二次确认 |
| **"来了解这个功能"**（硬阻断，引导教学） | 说话人绑定引导、知识库关联引导 | ⚠️ 偏重——引导类内容用硬阻断 Modal 让用户感觉"被困住"，但内容本身是可选的知识 |
| **"一步步完成任务"**（硬阻断，多步流程） | 新建会议向导 | ✅ 合理——多步向导需要独立空间感 |
| **"正在过渡"**（局部蒙版） | 录音结束过渡 | ✅ 合理——局部 blur 暗示"这里正在发生变化" |

## 2. 一致性问题

### 2.1 蒙版背景不透明度不统一

| 不透明度 | 使用场景 | 问题 |
|----------|---------|------|
| `0.35` | 放弃录音、重启确认 | 偏轻，与同层 Modal 不一致 |
| `0.4` | 引导弹窗、存在性警告、说话人管理、隐私声明 | 使用最广，事实上已成为标准值 |
| `0.45` | 新建会议向导 | 略重于标准值 |
| `0.5` | 删除确认、归档确认 | 最重，scoped 组件内各自定义 |
| `rgba(0,0,0,0.5)` | 归档确认 | 未使用 OKLCH 色彩空间，与主题体系不一致 |

**结论**：应收敛到 **`oklch(0% 0 0 / 0.4)`** 作为统一蒙版背景色（已是使用最广的值）。

### 2.2 z-index 未统一使用 token

| 写法 | 使用场景 | 问题 |
|------|---------|------|
| `var(--z-modal)` | 大多数 Modal | ✅ 正确 |
| 硬编码 `1000` | 存在性警告、说话人管理弹窗 | ❌ 绕过 token，维护困难 |

### 2.3 入场/退场动效不一致

| 动效模式 | 使用场景 |
|----------|---------|
| fadein + card slide-up（0.4s cubic-bezier） | 仅引导弹窗（spk/proj-onboarding） |
| opacity transition（0.2s） | 向导、放弃录音、说话人管理 |
| opacity transition（0.25s）+ scale | 重启确认 |
| opacity transition（0.3s） | 登录遮罩、录音结束 |
| 无动效 | 删除确认、归档确认、存在性警告、隐私声明 |

**结论**：存在至少 5 种不同的动效方案。应统一为 2 种：
- **标准 Modal**：opacity 0.2s + card translateY(8px) 0.25s
- **引导型 Modal**（含丰富动画演示）：保留现有 fadein + card slide-up

### 2.4 ESC 关闭支持不完整

| 支持 ESC | 不支持 ESC |
|----------|-----------|
| 说话人引导 ✅、知识库引导 ✅ | 删除确认 ❌、归档确认 ❌、存在性警告 ❌、放弃录音 ❌、隐私声明 ❌、重启确认 ❌、向导 ❌、说话人管理 ❌ |

**结论**：所有 `--z-modal` 级别的 Modal **必须**支持 ESC 关闭（存在性警告除外——它要求用户做出明确操作决策）。

### 2.5 卡片样式不统一

| 维度 | 引导弹窗 | 向导 | 确认弹窗（scoped） | 说话人管理 |
|------|---------|------|-------------------|-----------|
| 宽度 | 480px | 560px | 400px / 500px | 480px |
| 圆角 | `--radius-xl` | `--radius-lg` | `--radius-lg` / `12px` | `--radius-lg` |
| 边框 | `--border-strong` | 无 | `--border` / 无 | `--border` |
| 阴影 | 双层阴影 | 单层 0.2 | 单层 0.15~0.2 | 单层 0.2 |

**结论**：应定义统一的 Modal 卡片基础样式，通过 `--modal-width` 等变量控制尺寸变体。

### 2.6 代码重复

- `.wizard-overlay` 在 `meeting-view.css` 和 `speakers.css` 中各定义了一份（完全相同）。
- 确认类弹窗（删除、归档）各自在 scoped CSS 中独立实现，结构几乎相同但样式细节不同。

## 3. 统一蒙版设计规范

### 3.1 蒙版分级体系

基于前述感知分析，定义三级蒙版：

| 级别 | 名称 | 背景 | 场景 | 用户感知 |
|------|------|------|------|----------|
| **L3 硬阻断** | Modal | `oklch(0% 0 0 / 0.4)` | 确认操作、引导教学、多步向导 | "我必须处理这件事" |
| **L2 软阻断** | Drawer / Side Panel | `oklch(0% 0 0 / 0.25)` | 未来：设置面板、详情预览 | "我在旁边看看，随时回去" |
| **L1 轻量提示** | Toast / Inline Banner | 无蒙版或 `oklch(0% 0 0 / 0.1)` | 操作反馈、状态提示 | "我知道了，继续做手头的事" |

> 当前项目以 L3 为主，L1 已有 Toast 体系，L2（Drawer）尚未使用但适合未来的设置面板等场景。

### 3.2 CSS Token 定义

在 `base.css` 的 `:root` 中新增蒙版相关 token：

```css
:root {
  /* ── 蒙版体系 token ── */
  --overlay-bg: oklch(0% 0 0 / 0.4);        /* 标准 Modal 蒙版背景 */
  --overlay-bg-soft: oklch(0% 0 0 / 0.25);  /* Drawer / 软阻断背景 */
  --overlay-bg-heavy: oklch(0% 0 0 / 0.55); /* 极重阻断（如登录全屏不透明） */
  --overlay-enter: 0.2s ease;               /* 蒙版淡入时长 */
  --card-enter: 0.25s cubic-bezier(0.16, 1, 0.3, 1); /* 卡片入场时长 */
  --modal-width-sm: 400px;   /* 确认弹窗 */
  --modal-width-md: 480px;   /* 标准弹窗、引导弹窗 */
  --modal-width-lg: 560px;   /* 向导 */
}
```

### 3.3 统一 Modal 基础结构

所有 L3 硬阻断 Modal 应使用统一的基础 CSS 类：

```css
/* ── 统一蒙版基础（base.css） ── */
.oms-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  background: var(--overlay-bg);
  display: grid;
  place-items: center;
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--overlay-enter);
}
.oms-overlay.is-open {
  opacity: 1;
  pointer-events: auto;
}

.oms-overlay-card {
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-xl);
  box-shadow: 0 20px 60px oklch(0% 0 0 / 0.10), 0 4px 16px oklch(0% 0 0 / 0.05);
  width: var(--modal-width-md);
  max-width: calc(100% - var(--s-6));
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transform: translateY(8px);
  opacity: 0;
  transition: transform var(--card-enter), opacity var(--card-enter);
}
.oms-overlay.is-open .oms-overlay-card {
  transform: translateY(0);
  opacity: 1;
}
```

### 3.4 交互行为统一规范

| 行为 | 规则 | 例外 |
|------|------|------|
| 点击蒙版关闭 | ✅ 所有非破坏性 Modal | 存在性警告（需明确操作） |
| ESC 关闭 | ✅ 所有 Modal | 存在性警告 |
| 关闭按钮（×） | ✅ 所有 Modal 右上角 | 无例外 |
| `role="dialog"` + `aria-modal="true"` | ✅ 所有 Modal | 无例外 |
| `aria-labelledby` | ✅ 所有 Modal 关联标题 | 无例外 |
| `prefers-reduced-motion` | ✅ 禁用入场动画 | 无例外 |
| `<Teleport to="body">` | ✅ 所有 Modal 脱离组件层级 | 无例外 |

### 3.5 动效规范

**标准 Modal 入场**（确认弹窗、管理弹窗）：
```
蒙版: opacity 0 → 1, 0.2s ease
卡片: translateY(8px) → 0 + opacity 0 → 1, 0.25s cubic-bezier(0.16, 1, 0.3, 1)
```

**引导型 Modal 入场**（含丰富演示动画的引导弹窗）：
```
蒙版: opacity 0 → 1, 0.2s ease
卡片: translateY(16px) scale(0.97) → 0 + opacity 0 → 1, 0.4s cubic-bezier(0.16, 1, 0.3, 1)
```
> 引导型允许更大幅度的入场动效，因为其卡片内含复杂动画演示，需要更长的铺垫时间。

**退场**：统一使用 opacity 淡出，不额外做卡片退场动画（避免关闭时"卡一下"的感觉）。

## 4. 实施方案

### 4.1 Phase 1：Token 化与基础类（优先级高，影响面小）

**目标**：在 `base.css` 中定义蒙版 token 和基础类，不改动现有组件。

| 步骤 | 文件 | 变更 |
|------|------|------|
| 1 | `styles/base.css` | 新增 `--overlay-bg`、`--overlay-bg-soft`、`--overlay-enter`、`--card-enter`、`--modal-width-*` token |
| 2 | `styles/base.css` | 新增 `.oms-overlay` + `.oms-overlay-card` 基础类 |

**验证**：不影响现有任何 Modal 的视觉表现。

### 4.2 Phase 2：收敛不透明度与 z-index（优先级高，低风险）

**目标**：将所有现有蒙版的不透明度统一到 `var(--overlay-bg)`，z-index 统一到 `var(--z-modal)`。

| 场景 | 当前值 | 目标值 |
|------|--------|--------|
| `.wizard-overlay` background | `0.45` | `var(--overlay-bg)` |
| `.delete-dialog-overlay` background | `0.5` | `var(--overlay-bg)` |
| `.archive-dialog-overlay` background | `rgba(0,0,0,0.5)` | `var(--overlay-bg)` |
| `.abandon-overlay` background | `0.35` | `var(--overlay-bg)` |
| `.restart-modal-overlay` background | `0.35` | `var(--overlay-bg)` |
| `.rec-presence-overlay` z-index | 硬编码 `1000` | `var(--z-modal)` |
| `.modal-overlay`（speakers） z-index | 硬编码 `1000` | `var(--z-modal)` |

### 4.3 Phase 3：ESC 关闭补全（优先级中，低风险）

为以下 Modal 补充 `@keydown.esc` 处理：

| 场景 | 组件文件 | 处理方式 |
|------|---------|---------|
| 删除确认 | `DeleteDialog.vue` | `@keydown.esc="emit('update:modelValue', false)"` |
| 归档确认 | `ArchiveDialog.vue` | `@keydown.esc="emit('close')"` |
| 隐私声明 | `StartView.vue` | `@keydown.esc` 关闭弹窗 |
| 重启确认 | `UpdatePanel.vue` | `@keydown.esc` 关闭弹窗 |
| 新建会议向导 | `LibraryView.vue` / wizard 组件 | `@keydown.esc` 关闭向导 |
| 说话人管理 | `SpeakersView.vue` | `@keydown.esc` 关闭弹窗 |

**不补 ESC 的例外**：
- 存在性警告（`.rec-presence-overlay`）——要求用户做出明确操作决策
- 放弃录音确认——同上，已提供按钮操作路径

### 4.4 Phase 4：动效统一（优先级中，中风险）

| 场景 | 当前动效 | 目标动效 |
|------|---------|---------|
| 删除确认 | 无 | 标准 Modal 入场 |
| 归档确认 | 无 | 标准 Modal 入场 |
| 存在性警告 | 无 | 标准 Modal 入场 |
| 隐私声明 | 无 | 标准 Modal 入场 |
| 重启确认 | opacity + scale | 标准 Modal 入场（去掉 scale） |

### 4.5 Phase 5：scoped 组件迁移到全局类（优先级低，中风险）

将 `DeleteDialog.vue`、`ArchiveDialog.vue` 的 scoped overlay 样式迁移到全局 `.oms-overlay` + `.oms-overlay-card` 基础类，消除重复代码。

**迁移策略**：
1. 组件模板改用 `oms-overlay` + `oms-overlay-card` 类名
2. 删除 scoped 中的 overlay / dialog 定位与基础样式
3. 保留 scoped 中仅与业务相关的样式（如 `.delete-dialog-body` 的特殊布局）

### 4.6 Phase 6：消除 CSS 重复定义（优先级低，低风险）

| 问题 | 解决方案 |
|------|---------|
| `.wizard-overlay` 在 `meeting-view.css` 和 `speakers.css` 中重复定义 | 仅保留 `meeting-view.css` 中的定义，`speakers.css` 中删除重复块 |

## 5. 潜在新增蒙版场景

### 5.1 适合引入 Drawer（L2 软阻断）的场景

| 场景 | 理由 |
|------|------|
| 设置面板（当前为独立路由页） | 用户可能想在设置与内容之间快速切换，Drawer 保留上下文可见性 |
| 说话人详情/编辑 | 当前为独立路由页，信息量适中，适合侧边预览 |
| 会议详情预览（从侧边栏或会议库触发） | 快速查看不需要离开当前页面 |

### 5.2 适合新增 Modal（L3 硬阻断）的场景

| 场景 | 理由 |
|------|------|
| 导出选项确认 | 多格式选择 + 预览，需要独立空间 |
| 批量操作确认（会议库批量删除/导出） | 破坏性操作需要二次确认 |

### 5.3 应保持无蒙版的场景

| 场景 | 理由 |
|------|------|
| 说话人绑定栏（`.gen-binding-bar`） | 已作为内联横幅实现，不打断工作流 ✅ |
| 洞察台横幅 | 已作为浮动提示实现，不阻断操作 ✅ |
| Toast 通知 | 已使用轻量级提示 ✅ |

## 6. 设计决策记录

### D-1：为什么引导弹窗用硬阻断而非软阻断？

**决定**：说话人绑定引导和知识库关联引导使用 L3 硬阻断 Modal。

**理由**：
- 引导弹窗内含 before/after 双态对比动画演示（4s 周期），需要用户**完整注意力**才能理解功能价值
- 如果底层内容可见（软阻断），动画演示的视觉焦点会与底层内容竞争
- 引导弹窗是**一次性**的（`localStorage` 持久化已看过状态），用户只会被"困住"一次

**代价**：首次体验时用户无法参照实际数据理解功能——通过弹窗内的演示数据弥补。

### D-2：为什么存在性警告不支持 ESC 关闭？

**决定**：`.rec-presence-overlay`（紧急级别）不提供 ESC 关闭。

**理由**：
- 存在性警告表示"检测到你可能在录音，是否继续？"——这是一个**需要明确决策**的场景
- ESC 关闭 = 默认忽略警告，可能导致用户无意中丢失录音
- 与 DESIGN_DECISIONS §12 的登录遮罩设计一致：关键决策必须有明确操作路径

### D-3：为什么统一不透明度选 0.4 而非 0.5？

**决定**：标准蒙版不透明度为 `oklch(0% 0 0 / 0.4)`。

**理由**：
- 0.5 的阻断感过强——用户感觉"被锁在黑屋子里"，尤其暗色主题下几乎看不到底层内容
- 0.4 已是项目中使用最广的值（6/12 场景），收敛成本最低
- 0.4 在亮色和暗色主题下均能提供足够的"有东西挡住了"感知，同时保留底层内容的隐约轮廓

## 7. 检查清单

新增任何蒙版场景时，逐项确认：

- [ ] 阻断级别匹配：操作的重要程度是否匹配所选蒙版类型？（参考 §3.1 分级表）
- [ ] 背景使用 `var(--overlay-bg)` 而非硬编码
- [ ] z-index 使用 `var(--z-modal)` 而非硬编码数值
- [ ] 支持 ESC 关闭（除非属于 §3.4 例外场景）
- [ ] 支持点击蒙版关闭（除非属于 §3.4 例外场景）
- [ ] 有可见的关闭按钮（§3.4 规则，无例外）
- [ ] `role="dialog"` + `aria-modal="true"` + `aria-labelledby`
- [ ] 使用 `<Teleport to="body">` 脱离组件层级
- [ ] `prefers-reduced-motion` 降级处理
- [ ] 入场动效使用标准 Modal 或引导型 Modal 方案（§3.5）
- [ ] 响应式：`max-width: calc(100% - var(--s-6))` 确保小屏不溢出
