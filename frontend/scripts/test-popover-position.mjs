// 浮层定位停靠栏避让卡口 / Popover dock-avoidance regression tests
// 运行：node --experimental-strip-types scripts/test-popover-position.mjs
//
// 背景：rail 图标「点了没反应」已因浮层横压导航轨复发四次。本用例钉死：
// 任何经统一工具定位的浮层，都不得侵入左 rail / 右 AI 停靠栏的安全区。
// The rail "dead icon" bug recurred four times via popover overlap. These
// cases pin every shared-helper popover inside the dock safe-zone.
import test from 'node:test'
import assert from 'node:assert'
import {
  clampHorizontal,
  positionAroundAnchor,
  positionDropdown,
  DOCK_GAP,
} from '../src/utils/popoverPosition.ts'

// 典型布局：rail 52px / AI 折叠竖条 44px / 视口 1064×803（与实测环境一致）
const BOUNDS = { vw: 1064, vh: 803, railRight: 52, aiLeft: 1064 - 44 }

test('clampHorizontal: 靠左的短词选区，浮层左缘不得进入 rail 安全区', () => {
  // 折叠侧栏后正文左缘 ~65px，选区中心 x≈140，工具栏宽 340
  const x = clampHorizontal(140, 340, BOUNDS)
  assert.ok(x >= BOUNDS.railRight + DOCK_GAP, `x=${x} 侵入左停靠栏`)
})

test('clampHorizontal: 靠右选区，浮层右缘不得盖住 AI 折叠竖条', () => {
  const w = 240
  const x = clampHorizontal(1040, w, BOUNDS)
  assert.ok(x + w <= BOUNDS.aiLeft - DOCK_GAP, `右缘=${x + w} 侵入右停靠栏`)
})

test('clampHorizontal: 视口中部选区保持居中', () => {
  const w = 200
  const x = clampHorizontal(500, w, BOUNDS)
  assert.strictEqual(x, 400)
})

test('clampHorizontal: 浮层比停靠栏可用区更宽时退化为视口夹取，不产生 NaN/负值', () => {
  const narrow = { vw: 320, vh: 600, railRight: 200, aiLeft: 220 }
  const x = clampHorizontal(210, 300, narrow)
  assert.ok(Number.isFinite(x))
  assert.ok(x >= 8 && x + 300 <= 320 + 0.001, `退化夹取越界 x=${x}`)
})

test('clampHorizontal: 无停靠栏（railRight=0, aiLeft=vw）等价于纯视口夹取', () => {
  const none = { vw: 1000, vh: 700, railRight: 0, aiLeft: 1000 }
  assert.strictEqual(clampHorizontal(500, 200, none), 400)
  assert.strictEqual(clampHorizontal(30, 200, none), 8)
})

test('positionAroundAnchor: 默认浮在锚点上方居中', () => {
  const anchor = { top: 300, left: 400, width: 40, height: 20 }
  const { x, y } = positionAroundAnchor(anchor, 200, 40, BOUNDS)
  assert.strictEqual(x, 320)
  assert.strictEqual(y, 300 - 40 - 8)
})

test('positionAroundAnchor: 上方空间不足翻到锚点下方', () => {
  const anchor = { top: 20, left: 400, width: 40, height: 20 }
  const { y } = positionAroundAnchor(anchor, 200, 40, BOUNDS)
  assert.strictEqual(y, 20 + 20 + 8)
})

test('positionAroundAnchor: 靠左锚点仍被夹出 rail 安全区（回归：划词工具栏盖图标）', () => {
  // 折叠侧栏、正文左缘划短词：anchor 中心约 140、工具栏 340 宽
  const anchor = { top: 290, left: 120, width: 40, height: 20 }
  const { x, y } = positionAroundAnchor(anchor, 340, 38, BOUNDS)
  assert.ok(x >= BOUNDS.railRight + DOCK_GAP, `x=${x} 横压 rail`)
  assert.ok(x + 340 <= BOUNDS.aiLeft - DOCK_GAP, '右缘侵入 AI 停靠栏')
  assert.ok(y >= 8, `y=${y} 越顶`)
})

test('positionDropdown: end 对齐 + 靠左触发时左缘夹到 rail 安全区', () => {
  // 触发按钮右缘仅 120，菜单宽 200 → 理想 left=-80，必须被夹回
  const trigger = { top: 100, left: 80, width: 40, height: 30 }
  const { x, y } = positionDropdown(trigger, 200, 160, BOUNDS)
  assert.ok(x >= BOUNDS.railRight + 4, `x=${x} 横压 rail`)
  assert.strictEqual(y, 100 + 30 + 4)
})

test('positionDropdown: 下方空间不足向上翻转', () => {
  const trigger = { top: 700, left: 400, width: 40, height: 30 }
  const { y } = positionDropdown(trigger, 200, 160, BOUNDS)
  assert.strictEqual(y, 700 - 160 - 4)
})

test('positionDropdown: start 对齐且不碰停靠栏时保持原位', () => {
  const trigger = { top: 200, left: 300, width: 40, height: 30 }
  const { x } = positionDropdown(trigger, 180, 120, BOUNDS, { align: 'start' })
  assert.strictEqual(x, 300)
})

test('positionDropdown: 靠右触发时菜单右缘避让 AI 停靠栏', () => {
  const trigger = { top: 200, left: 1020, width: 40, height: 30 }
  const w = 200
  const { x } = positionDropdown(trigger, w, 120, BOUNDS)
  assert.ok(x + w <= BOUNDS.aiLeft - 4, `右缘=${x + w} 盖住 AI 竖条`)
})
