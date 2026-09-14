---
title: 图标规范
description: 统一图标库选型、尺寸体系、集成方式及 Emoji 替换映射，确保全应用图标风格一致。
tags: ["icon", "ui", "design-system", "feather", "lucide"]
created_at: "2026-09-08"
updated_at: "2026-09-08"
version: "1.0.0"
author: "wangyongliang"
status: "published"
category: "design"
---

# ICON SPEC — 图标规范

> 本文是图标使用的**唯一事实源**。所有前端图标必须遵循本规范。

## 1. 图标库：Lucide（Feather Icons 活跃分支）

| 维度 | 说明 |
|------|------|
| 库名 | [Lucide](https://lucide.dev/icons/) |
| 来源 | Feather Icons 社区维护分支，视觉风格 100% 兼容 |
| 选型理由 | 项目现有内联 SVG 已采用 Feather 风格；Feather 已停更（2020），Lucide 持续维护且图标更全 |
| 许可 | ISC License，可自由使用 |
| 风格特征 | 24×24 viewBox、stroke-only（无 fill）、round 端点、2px 线宽 |

### 为什么不用其他方案

| 方案 | 不选原因 |
|------|----------|
| Font Awesome / Material Icons | 重量级（数千图标），本项目只需 ~50 个；fill 风格与现有设计不匹配 |
| emoji | 跨平台渲染不一致、无法通过 CSS 控制颜色/尺寸、与 SVG 图标混搭视觉割裂 |
| 纯手写 SVG | 已证明可行但维护成本高，同一图标多处重复，不如集中管理 |

## 2. 集成方式：JS 图标映射表

项目为单 HTML 文件、无构建系统，采用 **JS 图标映射表 + 辅助函数** 方式集成：

```javascript
/**
 * 图标映射表 — 集中管理所有 Lucide SVG path
 * 使用方式：icon('check') 返回完整 <svg> HTML 字符串
 */
const ICONS = {
  check:    '<polyline points="20 6 9 17 4 12"/>',
  x:        '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  plus:     '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  folder:   '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
  // ... 按需补充
};

/**
 * 生成图标 HTML
 * @param {string} name  图标名（ICONS 中的 key）
 * @param {string} size  尺寸等级：'sm' | 'md' | 'lg' | 'xl'（默认 'md'）
 * @param {string} cls   附加 CSS 类名（可选）
 * @returns {string}     完整 <svg> HTML
 */
function icon(name, size = 'md', cls = '') {
  const paths = ICONS[name];
  if (!paths) return `<!-- icon: ${name} not found -->`;
  const sizeClass = `ic-${size}`;
  const extra = cls ? ` ${cls}` : '';
  return `<svg class="ic ${sizeClass}${extra}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;
}
```

### 使用示例

```javascript
// HTML 中静态使用
<button class="topbar-new-btn">${icon('plus', 'md')}</button>

// JS 动态生成
html += `<span class="error-icon">${icon('alert-triangle', 'lg')}</span>`;

// 带附加类名
icon('folder', 'md', 'proj-row-icon-svg')
```

## 3. 尺寸体系

统一 4 个尺寸等级，通过 CSS 类控制：

| 等级 | CSS 类 | 尺寸 | 使用场景 |
|------|--------|------|----------|
| sm | `.ic-sm` | 14×14 | 内联文字标记、勾选符、排序箭头、紧凑列表 |
| md | `.ic-md` | 16×16 | **默认**：按钮内图标、导航项、搜索框、菜单项 |
| lg | `.ic-lg` | 20×20 | 标题区图标、引导提示、空状态小图 |
| xl | `.ic-xl` | 24×24 | 空状态大图、独立图标按钮、品牌标识辅助 |

### CSS 定义

```css
/* ─── 图标基础 ─── */
.ic {
  flex-shrink: 0;
  stroke: currentColor;
  fill: none;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.ic-sm { width: 14px; height: 14px; }
.ic-md { width: 16px; height: 16px; }
.ic-lg { width: 20px; height: 20px; }
.ic-xl { width: 24px; height: 24px; }
```

### 尺寸选择原则

1. **按钮内图标** → `md`（16px），与 14px 文字搭配视觉平衡
2. **空状态插画** → `xl`（24px）或更大（可用 CSS 覆盖至 48px）
3. **表格/列表内联** → `sm`（14px），避免撑开行高
4. **独立操作按钮**（如折叠/展开） → `md` 或 `lg`，视按钮尺寸而定

## 4. SVG 属性规范

所有内联 SVG 必须遵循以下属性：

| 属性 | 值 | 说明 |
|------|-----|------|
| `viewBox` | `0 0 24 24` | 统一 24×24 坐标系 |
| `fill` | `none` | 纯线条风格，不填充 |
| `stroke` | `currentColor` | 跟随父元素文字颜色 |
| `stroke-width` | `2` | 标准线宽（特殊场景可用 `1.6`） |
| `stroke-linecap` | `round` | 圆头端点 |
| `stroke-linejoin` | `round` | 圆角转折 |

**例外**：品牌标识（GitHub logo 等）使用 `fill="currentColor"` 填充风格，不受上述约束。

## 5. Emoji 替换映射表

以下 emoji 必须替换为 Lucide SVG 图标：

### 5.1 主页面（index.html）

| 当前 Emoji | 含义 | 替换为 Lucide 图标 | 位置 |
|-----------|------|-------------------|------|
| ⚠ | 警告/错误 | `alert-triangle` | 错误分类图标（L9536）、录音结束警告（L8074） |
| 🔄 | 重试/暂时不可用 | `refresh-cw` | 错误分类 transient（L9538） |
| 🎵 | 音频文件 | `music` | 错误分类 audio（L9539） |
| 🔑 | API 配置 | `key` | 错误分类 api_config（L9540） |
| 📎 | 附件/引用源 | `paperclip` | AI 来源标签（L12542） |
| 📁 | 文件夹/项目 | `folder` | 项目列表项（L13856, L14309, L14474） |
| 📂 | 浏览文件夹 | `folder-open` | 浏览按钮（L14073） |
| ✎ | 编辑（CSS ::after） | `edit-2` 或 `pencil` | 时间编辑按钮 hover（L1654） |
| ✕ | 关闭/清除 | `x` | 搜索清除按钮（L4750） |
| ✓ | 勾选 | `check` | 选项勾选标记（L5038, L8574） |
| ☐ | 未选复选框 | `square` | Markdown 待办渲染（L13263） |
| ☑ | 已选复选框 | `check-square` | Markdown 待办渲染（L13264） |
| ↑ ↓ | 排序方向 | `chevron-up` / `chevron-down` | 说话人排序列头（L5608） |
| ↕ | 滚动模式 | `move-vertical` | 拖拽模式提示（L7488） |

### 5.2 管理页面（admin.html）

| 当前 Emoji | 含义 | 替换为 Lucide 图标 | 位置 |
|-----------|------|-------------------|------|
| 📭 | 空邮箱/无数据 | `inbox` | 用户列表空状态（L532） |
| 📢 | 公告/消息 | `megaphone` | 消息列表空状态（L638） |
| 🎛️ | 功能开关 | `sliders` | 开关列表空状态（L705） |

### 5.3 保留 emoji 的场景

以下场景**允许保留 emoji**（不强制替换）：

- 产品 logo 中的 🎙 录音徽标（品牌元素，非功能图标）
- 用户消息内容中的表情符号（用户输入，非 UI 元素）

## 6. 新增图标的流程

1. 在 [Lucide 图标库](https://lucide.dev/icons/) 搜索目标图标
2. 复制 SVG 内部 path 内容（不含 `<svg>` 外壳）
3. 添加到 `ICONS` 映射表，key 使用 Lucide 官方命名
4. 使用 `icon('name', 'size')` 函数调用，**不要手写 `<svg>` 标签**
5. 如需特殊样式，通过附加 CSS 类或 `currentColor` 继承控制

## 7. 禁止事项

- **禁止**在 UI 功能元素中使用 emoji 作为图标（按钮、标签、状态指示等）
- **禁止**硬编码 `<svg>` 标签 — 必须通过 `icon()` 函数或 `ICONS` 映射表
- **禁止**修改 SVG 的 `viewBox`、`fill`、`stroke` 基础属性（尺寸通过 CSS 类控制）
- **禁止**引入其他风格的图标库（fill 风格、glyph font 等）
