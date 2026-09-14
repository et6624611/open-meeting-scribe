---
title: "随记时间戳显示为 00:00 的 Bug 修复"
description: "修复录音阶段添加的随记时间戳全部显示为 00:00 的问题，确保时间戳正确记录录音进度时间"
tags: ["bug-fix", "notes", "timestamp", "recording"]
created_at: "2026-09-10"
updated_at: "2026-09-10"
version: "1.0.0"
author: "AI Assistant"
status: "published"
---

# 随记时间戳显示为 00:00 的 Bug 修复

## 问题描述

在会议纪要的"随记（笔记）"模块中，用户在"实时录音/转录"阶段手动添加的笔记，其前方的时间戳全部异常显示为 `00:00`，而非用户输入时的真实录音进度时间。

## 根因分析

经过深入排查，发现问题由 **四层缺陷叠加** 导致，仅修复上层缺陷不足以解决问题：

### 根因 1（核心）：`useWebSocket.ts` 的 `sentence` 处理器丢失了 `begin_time`

**位置**: `frontend/src/composables/useWebSocket.ts` 第 107-122 行

**原代码**:
```javascript
case 'sentence':
    rtStore.push({                    // ✅ rtStore 正确保存 begin_time
        begin_time: msg.begin_time as number || 0,
        end_time: msg.end_time as number || 0,
        ...
    })
    lines.value.push({               // ❌ lines 丢失了 begin_time / end_time！
        speaker_id: ...,
        speaker_name: ...,
        text: msg.text as string,
        isFinal: true,
        // 没有 begin_time！没有 end_time！
    })
    break
```

**影响**:
- 后端 WS 正确发送了 `sentence` 消息中的 `begin_time`（来自 DashScope ASR 引擎，毫秒精度）
- `rtStore`（realtime store）正确保存了 `begin_time`
- 但 `lines` 数组（UI 实际使用的数据源）完全丢失了 `begin_time`
- 导致 `wsLines[i].begin_time` 始终为 `undefined`
- 这是 **修复不生效的真正原因**：即使 `formatNoteTime` 和 `onSendNote` 已修复，`line?.begin_time` 始终为 `undefined`，总是回退到备用值

**对比**: `history` 处理器（第 92-99 行）正确包含 `begin_time`，因此页面刷新后加载的历史行有时间戳，但实时到达的新行没有。

### 根因 2：`onSendNote` 备用值使用了 `Date.now()`

**位置**: `frontend/src/views/RecordingView.vue` 第 627-636 行

**原代码**:
```javascript
function onSendNote() {
  const text = noteText.value.trim()
  if (!text) return
  const lineIndex = wsLines.value.length > 0 ? wsLines.value.length - 1 : 0
  const time = wsLines.value[lineIndex]?.begin_time || Date.now()  // ❌ 问题
  const id = crypto.randomUUID()
  userNotes.value.push({ id, text, lineIndex, time })
  noteText.value = ''
  saveNotesToStorage()
}
```

**问题**: 
- 当没有 WS 转写行时（录音刚开始或网络延迟），`time` 被设置为 `Date.now()`
- `Date.now()` 返回 Unix 纪元以来的毫秒数（约 1.7 万亿），不是录音经过时间
- 这个巨大的数字无法被正确格式化为 `MM:SS` 格式

### 根因 3：`restoreNotesFromStorage` 重置了所有笔记的 `lineIndex`

**位置**: `frontend/src/views/RecordingView.vue` 第 606-619 行

**原代码**:
```javascript
function restoreNotesFromStorage() {
  try {
    const saved = localStorage.getItem(NOTES_LS_KEY)
    if (!saved) return
    const data: PersistedNote[] = JSON.parse(saved)
    if (!Array.isArray(data) || data.length === 0) return
    userNotes.value = data.map(n => ({
      id: n.id || crypto.randomUUID(),
      text: n.text,
      lineIndex: -1,  // ❌ 所有恢复的笔记 lineIndex 都是 -1
      time: n.time,
    }))
  } catch { /* 忽略 */ }
}
```

**问题**:
- 从 localStorage 恢复笔记时，`lineIndex` 被硬编码为 `-1`
- 这是因为页面刷新后无法精确匹配原始的行号

### 根因 4：`formatNoteTime` 无法处理 `lineIndex = -1` 的情况

**位置**: `frontend/src/views/RecordingView.vue` 第 887-894 行

**原代码**:
```javascript
function formatNoteTime(lineIdx: number): string {
  const line = wsLines.value[lineIdx]  // ❌ lineIdx = -1 时返回 undefined
  if (!line?.begin_time) return '00:00'  // ❌ 总是返回 '00:00'
  const sec = Math.floor(line.begin_time / 1000)
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}
```

**问题**:
- `wsLines.value[-1]` 返回 `undefined`
- 函数直接返回 `'00:00'`，完全忽略了存储的 `time` 字段

### 根因 5：`onStop` 调用 `formatNoteTime` 时未传递存储的时间

**位置**: `frontend/src/views/RecordingView.vue` 第 847-849 行

**原代码**:
```javascript
const notesText = userNotes.value.length > 0
  ? userNotes.value.map(n => `[${formatNoteTime(n.lineIndex)}] ${n.text}`).join('\n')
  : undefined
```

**问题**:
- 只传递了 `lineIndex`，没有传递笔记中存储的 `time` 值
- 导致 `formatNoteTime` 无法使用备用时间

## 修复方案

### 修复 1（核心）：`useWebSocket.ts` `sentence` 处理器补上 `begin_time` / `end_time`

```javascript
case 'sentence':
    rtStore.push({
        begin_time: msg.begin_time as number || 0,
        end_time: msg.end_time as number || 0,
        ...
    })
    partialText.value = ''
    lines.value.push({
        speaker_id: ...,
        speaker_name: ...,
        text: msg.text as string,
        begin_time: msg.begin_time as number,  // ✅ 补上
        end_time: msg.end_time as number,       // ✅ 补上
        isFinal: true,
    })
    break
```

### 修复 2: `onSendNote` 使用录音经过时间作为备用值

```javascript
function onSendNote() {
  const text = noteText.value.trim()
  if (!text) return
  const lineIndex = wsLines.value.length > 0 ? wsLines.value.length - 1 : 0
  const time = wsLines.value[lineIndex]?.begin_time || (recorder.elapsed.value * 1000)  // ✅ 修复
  const id = crypto.randomUUID()
  userNotes.value.push({ id, text, lineIndex, time })
  noteText.value = ''
  saveNotesToStorage()
}
```

**说明**:
- `recorder.elapsed.value` 是录音经过的秒数（来自 `useRecorder` composable）
- 乘以 1000 转换为毫秒，与 `begin_time` 的单位保持一致
- 这样即使没有 WS 行，也能保存正确的录音进度时间

### 修复 3: `formatNoteTime` 增加备用时间参数

```javascript
function formatNoteTime(lineIdx: number, fallbackTimeMs: number): string {
  const line = lineIdx >= 0 ? wsLines.value[lineIdx] : null  // ✅ 安全检查
  const timeMs = line?.begin_time || fallbackTimeMs  // ✅ 使用备用时间
  if (!timeMs) return '00:00'
  const sec = Math.floor(timeMs / 1000)
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}
```

**说明**:
- 增加 `fallbackTimeMs` 参数
- 当 `lineIdx` 无效（-1）或对应行没有 `begin_time` 时，使用备用时间
- 添加 `lineIdx >= 0` 的安全检查，避免数组越界访问

### 修复 4: `onStop` 传递存储的时间作为备用值

```javascript
const notesText = userNotes.value.length > 0
  ? userNotes.value.map(n => `[${formatNoteTime(n.lineIndex, n.time)}] ${n.text}`).join('\n')
  : undefined
```

**说明**:
- 将笔记中存储的 `time` 值传递给 `formatNoteTime`
- 确保即使 `lineIndex` 无效，也能使用保存的时间戳

### 修复 5: `restoreNotesFromStorage` 增加旧数据清洗

```javascript
function restoreNotesFromStorage() {
  const MAX_REASONABLE_MS = 24 * 60 * 60 * 1000  // 24 小时
  // 超出视为旧版 Date.now() 脏数据，重置为 0
  userNotes.value = data.map(n => {
    const time = (n.time > MAX_REASONABLE_MS) ? 0 : n.time
    return { id: ..., text: ..., lineIndex: -1, time }
  })
  if (dirty) saveNotesToStorage()  // 写回清洗后的数据
}
```

### 修复 6: `||` → `??` 避免 `begin_time=0` 被误判

```javascript
// 修复前：begin_time=0 时回退到备用值
const time = wsLines.value[lineIndex]?.begin_time || (recorder.elapsed.value * 1000)
// 修复后：仅 undefined/null 时回退
const time = wsLines.value[lineIndex]?.begin_time ?? (recorder.elapsed.value * 1000)
```

## 修复效果

修复后，随记时间戳的显示逻辑如下：

1. **正常情况**（有 WS 转写行）：
   - 使用对应行的 `begin_time`（ASR 引擎提供的精确时间）
   - 格式：`MM:SS`（如 `05:23`）

2. **备用情况**（无 WS 转写行或 lineIndex 无效）：
   - 使用 `recorder.elapsed.value * 1000`（录音经过毫秒数）
   - 格式：`MM:SS`（如 `05:23`）

3. **恢复情况**（从 localStorage 恢复的笔记）：
   - 使用保存的 `time` 值（可能是 `begin_time` 或录音经过时间）
   - 格式：`MM:SS`（如 `05:23`）

## 测试场景

### 场景 1: 录音开始时立即添加笔记
- **操作**: 开始录音，在出现转写文本前添加笔记
- **预期**: 时间戳显示为 `00:XX`（录音经过秒数）
- **修复前**: 显示为 `00:00`
- **修复后**: ✅ 正确显示

### 场景 2: 录音中途添加笔记
- **操作**: 录音进行到 5 分 23 秒时添加笔记
- **预期**: 时间戳显示为 `05:23`
- **修复前**: 显示为 `00:00`
- **修复后**: ✅ 正确显示

### 场景 3: 页面刷新后停止录音
- **操作**: 录音中途刷新页面，然后停止录音
- **预期**: 恢复的笔记时间戳正确显示
- **修复前**: 显示为 `00:00`
- **修复后**: ✅ 正确显示

## 涉及文件

- `frontend/src/composables/useWebSocket.ts`（**核心修复**）
  - `sentence` 处理器：补上 `begin_time` / `end_time`（第 116-123 行）
- `frontend/src/views/RecordingView.vue`
  - `onSendNote()` 函数（第 627-637 行）
  - `restoreNotesFromStorage()` 函数（第 606-627 行）
  - `formatNoteTime()` 函数（第 895-905 行）
  - `onStop()` 函数（第 847-849 行）

## 相关代码路径

1. **录音阶段**:
   - 用户添加笔记 → `onSendNote()` → 保存到 `userNotes` 和 localStorage
   - 停止录音 → `onStop()` → 格式化时间戳 → 提交到后端

2. **后端存储**:
   - `app/routers/record.py` → `stop_record()` → 保存到 `tasks[task_id]["user_notes"]`
   - `app/routers/notes.py` → `GET /api/tasks/{id}/notes` → 返回笔记内容

3. **纪要阶段**:
   - `GeneratingView.vue` → `loadNotes()` → 从后端加载笔记
   - `MdBlockEditor.vue` → 渲染笔记内容（包含时间戳）

## 技术要点

1. **时间单位统一**: 
   - `begin_time`: 毫秒（ASR 引擎提供）
   - `recorder.elapsed.value`: 秒（录音计时器）
   - 需要乘以 1000 转换为毫秒

2. **localStorage 持久化**:
   - 笔记结构: `{ id, text, lineIndex, time }`
   - 恢复时 `lineIndex` 设为 -1（无法精确匹配行号）
   - 依赖 `time` 字段作为备用时间源

3. **函数签名变更**:
   - `formatNoteTime(lineIdx)` → `formatNoteTime(lineIdx, fallbackTimeMs)`
   - 增加备用参数，提高容错性

## 后续建议

1. **添加单元测试**: 验证时间戳格式化逻辑在各种边界条件下的正确性
2. **监控日志**: 在 `formatNoteTime` 中添加日志，记录使用备用时间的情况
3. **用户提示**: 当使用备用时间时，可在 UI 上显示提示（如"估算时间"）
