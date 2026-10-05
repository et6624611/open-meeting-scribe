/**
 * utils/speakerDisplay.ts — 说话人占位名判定与展示解析（REQ-SPK-RN T2）
 *
 * 口径来源：docs/design/SPK-RN-DISPLAY-STRATEGY.md §1（判定器）+
 * 说话人展示 T1 后端评审 D6 裁决（超集正则，与 core/speakers.PLACEHOLDER_NAME_RE 同源）。
 * AC-8 双侧一致性：样本矩阵钉死于 tests/test_speaker_realname_be.py::AC8_SAMPLE_MATRIX，
 * 本文件自测（__selfTestAc8）逐条复用同一矩阵。
 *
 * 约定：命中判定 = 「无真实信息」→ 未绑定态（D5 聚合「未识别」）；空串/空白同样视为未命名
 * （BE-R1 新数据形态）。真实名一律原样展示。
 */

const PLACEHOLDER_WORDS = 'One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten'

/** 与后端 core/speakers.PLACEHOLDER_NAME_RE 同源：整串锚定、大小写不敏感 */
export const PLACEHOLDER_NAME_RE = new RegExp(
  `^\\s*(?:Speaker\\s+\\d+|Speaker\\s+(?:${PLACEHOLDER_WORDS})|说话人\\s*\\d+|发言人\\s*\\d+)\\s*$`,
  'i',
)

/** 姓名是否无效（占位编号/空/非字符串）→ 未识别态 */
export function isPlaceholderName(name: unknown): boolean {
  if (typeof name !== 'string') return true
  const s = name.trim()
  return !s || PLACEHOLDER_NAME_RE.test(s)
}

/** 归一单值：占位/空白 → ''，真名去首尾空白返回 */
export function normalizeSpeakerName(name: unknown): string {
  return isPlaceholderName(name) ? '' : (name as string).trim()
}

/**
 * 聚合计数：mapping 中未命名说话人按 speaker_id（键）去重计数。
 * 注意：跨任务/库级不做人数加总（设计稿 §3.1），库级用 hasUnidentified 布尔。
 */
export function countUnidentified(mapping: Record<string, unknown> | null | undefined): number {
  if (!mapping) return 0
  return Object.values(mapping).filter(isPlaceholderName).length
}

/** 该 mapping 是否含 ≥1 未绑定说话人（库级布尔聚合项口径） */
export function hasUnidentified(mapping: Record<string, unknown> | null | undefined): boolean {
  if (!mapping) return false
  return Object.values(mapping).some(isPlaceholderName)
}

/** 仅真实名列表（保展示顺序，去重） */
export function realNames(mapping: Record<string, unknown> | null | undefined): string[] {
  if (!mapping) return []
  const out: string[] = []
  for (const v of Object.values(mapping)) {
    const n = normalizeSpeakerName(v)
    if (n && !out.includes(n)) out.push(n)
  }
  return out
}

/** 展示名解析：真名直出；无效名 → 中性「未识别」（调用方传译好的文案） */
export function displayNameOr(name: unknown, unidentifiedLabel: string): string {
  return normalizeSpeakerName(name) || unidentifiedLabel
}

/** 头像首字：真名取首字符；未识别取「未」（en 环境由调用方传 '?' 标签时同样生效） */
export function avatarInitial(name: unknown, unidentifiedLabel = '未'): string {
  const n = normalizeSpeakerName(name)
  if (!n) return unidentifiedLabel.charAt(0)
  return n.charAt(0).toUpperCase()
}

/**
 * AC-8 自测矩阵（与后端 tests/test_speaker_realname_be.py::AC8_SAMPLE_MATRIX 同源）。
 * 由 selftest Playwright 在页面上下文调用，断言两侧判定逐条一致。
 */
export function ac8SampleMatrix(): Record<string, string> {
  return {
    'Speaker 1': 'unnamed',
    'Speaker Two': 'unnamed',
    'SPEAKER nine': 'unnamed',
    '说话人5': 'unnamed',
    '发言人 12': 'unnamed',
    '': 'unnamed',
    '  ': 'unnamed',
    '王五': 'named',
    'Speaker 4 王五': 'named',
    '发言人2（待确认）': 'named',
  }
}

/** 返回 AC-8 矩阵中判定不一致的样本（正常应为空数组） */
export function ac8Mismatches(): string[] {
  const bad: string[] = []
  for (const [sample, expect] of Object.entries(ac8SampleMatrix())) {
    const got = isPlaceholderName(sample) ? 'unnamed' : 'named'
    if (got !== expect) bad.push(`${sample}: expect ${expect}, got ${got}`)
  }
  return bad
}
