/**
 * parseInsightFlow 单元测试 / Unit tests for the Insight Deck canvas parser
 *
 * 运行：node --experimental-strip-types scripts/test-parse-insight-flow.ts
 * 覆盖验收项：规范样例、缺 @@、多余 -->、非 LR、嵌套异常，及各项边界容错。
 */
import {
  parseInsightFlow,
  matchPhaseDescriptions,
  formatFlowTime,
} from '../src/utils/parseInsightFlow.ts'
import assert from 'node:assert/strict'

let passed = 0
function t(name: string, fn: () => void) {
  try {
    fn()
    passed++
    console.log(`  ✓ ${name}`)
  } catch (e) {
    console.error(`  ✗ ${name}`)
    console.error(e)
    process.exitCode = 1
  }
}

const SPEC_SAMPLE = `flowchart LR
  subgraph S1["数据核对"]
    S1a["拉取费控数据 @@84000"]
    S1b["确认统计口径 @@461000"]
  end
  subgraph S2["差异讨论"]
    S2a["差旅超支归因 @@903000"]
  end
  S1a --- S2a`

t('规范样例：解析成功且结构正确', () => {
  const r = parseInsightFlow(SPEC_SAMPLE)
  assert.ok(r)
  assert.equal(r!.phases.length, 2)
  assert.equal(r!.phases[0].title, '数据核对')
  assert.equal(r!.phases[0].steps.length, 2)
  assert.equal(r!.phases[0].steps[0].label, '拉取费控数据')
  assert.equal(r!.phases[0].steps[0].beginTime, 84000)
  assert.equal(r!.phases[1].steps[0].beginTime, 903000)
  assert.deepEqual(r!.links, [{ from: 'S1', to: 'S2' }])
})

t('缺 @@ 标记：beginTime 为 0', () => {
  const r = parseInsightFlow(`flowchart LR
  subgraph S1["阶段甲"]
    S1a["无时间标记"]
  end
  subgraph S2["阶段乙"]
    S2a["也无"]
  end`)
  assert.ok(r)
  assert.equal(r!.phases[0].steps[0].beginTime, 0)
  assert.equal(r!.links.length, 0)
})

t('多余 --> 箭头：返回 null', () => {
  assert.equal(parseInsightFlow(SPEC_SAMPLE.replace('S1a --- S2a', 'S1a --> S2a')), null)
})

t('虚线 -.-> 宽容为无向连线；粗箭头 ==> 仍拒绝', () => {
  const r = parseInsightFlow(SPEC_SAMPLE.replace('S1a --- S2a', 'S1a -.-> S2a'))
  assert.ok(r)
  assert.deepEqual(r!.links, [{ from: 'S1', to: 'S2' }])
  assert.equal(parseInsightFlow(SPEC_SAMPLE.replace('S1a --- S2a', 'S1a ==> S2a')), null)
})

t('非 LR 方向（TD）：返回 null', () => {
  assert.equal(parseInsightFlow(SPEC_SAMPLE.replace('flowchart LR', 'flowchart TD')), null)
  assert.equal(parseInsightFlow(SPEC_SAMPLE.replace('flowchart LR', 'graph LR')), null)
})

t('嵌套 subgraph 异常：返回 null', () => {
  assert.equal(parseInsightFlow(`flowchart LR
  subgraph S1["外层"]
    subgraph S2["内层"]
      S2a["步骤"]
    end
  end`), null)
})

t('subgraph 未闭合：返回 null', () => {
  assert.equal(parseInsightFlow(`flowchart LR
  subgraph S1["只有开头"]
    S1a["步骤甲"]`), null)
})

t('裸节点（subgraph 外）：返回 null', () => {
  assert.equal(parseInsightFlow(`flowchart LR
  X1["裸节点"]
  subgraph S1["阶段甲"]
    S1a["步骤"]
  end`), null)
})

t('节点前缀与所属阶段不符：返回 null', () => {
  assert.equal(parseInsightFlow(`flowchart LR
  subgraph S1["阶段甲"]
    S2a["错位节点"]
  end`), null)
})

t('阶段内连线 / 连线引用未定义节点：返回 null', () => {
  assert.equal(parseInsightFlow(SPEC_SAMPLE.replace('S1a --- S2a', 'S1a --- S1b')), null)
  assert.equal(parseInsightFlow(SPEC_SAMPLE.replace('S1a --- S2a', 'S1a --- S9z')), null)
})

t('阶段数越界（1 个 / 6 个）：返回 null', () => {
  assert.equal(parseInsightFlow(`flowchart LR
  subgraph S1["唯一"]
    S1a["步"]
  end`), null)
  const six = ['flowchart LR']
  for (let i = 1; i <= 6; i++) six.push(`  subgraph S${i}["阶段${i}"]`, `    S${i}a["步骤"]`, '  end')
  assert.equal(parseInsightFlow(six.join('\n')), null)
})

t('引号变体：阶段标题超长拒绝；节点超长截断；非法声明语法降级', () => {
  const trunc = parseInsightFlow(`flowchart LR
  subgraph S1["阶段甲"]
    S1a["这一行标签文字总共超过十四字的长度限制"]
  end
  subgraph S2["阶段乙"]
    S2a["步"]
  end`)
  assert.ok(trunc) // 超长已改为截断，不再触发降级 / truncation, no degrade
  assert.equal(trunc!.phases[0].steps[0].label.length, 14)
  assert.equal(parseInsightFlow(`flowchart LR
  subgraph S1["阶段甲"]
    S1("带圆括号的节点 ID 非法")
  end
  subgraph S2["阶段乙"]
    S2a["步"]
  end`), null) // 真实输出变体：非方括号声明语法 → 降级
  assert.equal(parseInsightFlow(`flowchart LR
  subgraph S1["这个阶段的标题名字实在是太长了"]
    S1a["步"]
  end
  subgraph S2["乙"]
    S2a["步"]
  end`), null)
})

t('超长标签截断而非降级（上限 14 字）', () => {
  const r = parseInsightFlow(`flowchart LR
  subgraph S1["阶段甲"]
    S1a["这一行标签文字总共超过十四字的长度限制 @@84000"]
  end
  subgraph S2["阶段乙"]
    S2a["步"]
  end`)
  assert.ok(r)
  assert.equal(r!.phases[0].steps[0].label.length, 14)
  assert.equal(r!.phases[0].steps[0].beginTime, 84000)
})

t('@@ 只剥离尾部一处（正文含 @@ 不误伤）', () => {
  const r = parseInsightFlow(`flowchart LR
  subgraph S1["阶段甲"]
    S1a["邮箱 a@@b.com @@84000"]
  end
  subgraph S2["阶段乙"]
    S2a["步"]
  end`)
  assert.ok(r)
  assert.equal(r!.phases[0].steps[0].label, '邮箱 a@@b.com')
  assert.equal(r!.phases[0].steps[0].beginTime, 84000)
})

t('总节点超限（>12）：返回 null', () => {
  const lines = ['flowchart LR']
  for (let i = 1; i <= 4; i++) {
    lines.push(`  subgraph S${i}["阶段${i}"]`)
    for (let j = 0; j < 4; j++) lines.push(`    S${i}${'abcd'[j]}["步骤"]`)
    lines.push('  end')
  }
  assert.equal(parseInsightFlow(lines.join('\n')), null)
})

t('阶段级连线去重聚合', () => {
  const r = parseInsightFlow(`flowchart LR
  subgraph S1["甲"]
    S1a["一"]
    S1b["二"]
  end
  subgraph S2["乙"]
    S2a["三"]
  end
  S1a --- S2a
  S1b --- S2a`)
  assert.ok(r)
  assert.deepEqual(r!.links, [{ from: 'S1', to: 'S2' }])
})

t('空/乱输入：返回 null', () => {
  assert.equal(parseInsightFlow(''), null)
  assert.equal(parseInsightFlow('random text'), null)
  assert.equal(parseInsightFlow('mindmap\n  root((主题))'), null)
})

t('matchPhaseDescriptions：按「阶段名：一句话」匹配', () => {
  const r = parseInsightFlow(SPEC_SAMPLE)!
  matchPhaseDescriptions(r.phases, '数据核对：核对三个系统口径。\n\n差异讨论：聚焦差旅超支。这里是否缺了……？')
  assert.equal(r.phases[0].desc, '核对三个系统口径。')
  assert.equal(r.phases[1].desc, '聚焦差旅超支。这里是否缺了……？')
})

t('matchPhaseDescriptions：匹配不到保持无描述（合法降级）', () => {
  const r = parseInsightFlow(SPEC_SAMPLE)!
  matchPhaseDescriptions(r.phases, '这段图注里没有任何阶段名。')
  assert.equal(r.phases[0].desc, undefined)
  matchPhaseDescriptions(r.phases, null)
  assert.equal(r.phases[0].desc, undefined)
})

t('matchPhaseDescriptions：列表前缀与半角冒号兼容', () => {
  const r = parseInsightFlow(SPEC_SAMPLE)!
  matchPhaseDescriptions(r.phases, '- 数据核对: 冒号前半角也有列表符')
  assert.equal(r.phases[0].desc, '冒号前半角也有列表符')
})

t('真实输出变体：无引号标签 + 单 @ 标记也能解析', () => {
  const r = parseInsightFlow(`flowchart LR
  subgraph S1[概念辨析]
    S1a[区分偏差与缺陷 @120000]
  end
  subgraph S2[归因分层]
    S2a[流程响应慢？ @@408000]
  end
  S1a --- S2a`)
  assert.ok(r)
  assert.equal(r!.phases[0].title, '概念辨析')
  assert.equal(r!.phases[0].steps[0].label, '区分偏差与缺陷')
  assert.equal(r!.phases[0].steps[0].beginTime, 120000)
  assert.equal(r!.phases[1].steps[0].beginTime, 408000)
})

t('无引号变体：超长标签同样截断保留', () => {
  const r = parseInsightFlow(`flowchart LR
  subgraph S1[概念辨析]
    S1a[这一行裸标签的文字长度同样超过了十四字的限制]
  end
  subgraph S2[归因]
    S2a[步]
  end`)
  assert.ok(r)
  assert.equal(r!.phases[0].steps[0].label.length, 14)
})

t('matchPhaseDescriptions：占位符「阶段名：」序列写法定位分配', () => {
  const r = parseInsightFlow(SPEC_SAMPLE)!
  matchPhaseDescriptions(r.phases, '阶段名：第一项描述。\n阶段名：第二项描述。')
  assert.equal(r.phases[0].desc, '第一项描述。')
  assert.equal(r.phases[1].desc, '第二项描述。')
})

t('matchPhaseDescriptions：正文含精确名时占位符不抢先分配', () => {
  const r = parseInsightFlow(SPEC_SAMPLE)!
  matchPhaseDescriptions(r.phases, '阶段名：这是占位条目。\n数据核对：真正的描述。')
  assert.equal(r.phases[0].desc, '真正的描述。')
  assert.equal(r.phases[1].desc, undefined)
})

t('formatFlowTime 格式化', () => {
  assert.equal(formatFlowTime(0), '00:00')
  assert.equal(formatFlowTime(84000), '01:24')
  assert.equal(formatFlowTime(461000), '07:41')
  assert.equal(formatFlowTime(3792000), '1:03:12')
})

console.log(`\n${passed} tests passed${process.exitCode ? ' (with failures)' : ''}`)
