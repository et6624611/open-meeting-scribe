/**
 * 定稿正文排版解析（B5 版式找回，UI-RESTORE-INVENTORY）
 *
 * 助手上传的 formal=纯文本，实测行形态为「说话人名: 内容」（个人版转录面板同源数据）。
 * 本模块只做**呈现层分段**（不改变任何字符内容，拼接后与原文逐字一致）：
 *  - speaker：行首「名字: 」（半/全角冒号），名字≤24 字且不含句读——同名人跨段稳定同色由消费侧哈希保证；
 *  - heading：行首「名字：」但冒号后为空（章节/小节引导行），渲染为加粗引导而非发言人 chip；
 *  - plain：其余行并入当前段（保留原始换行），无当前段时独立成 plain 段。
 */

export type FormalSegment =
  | { kind: 'speaker'; name: string; text: string }
  | { kind: 'heading'; name: string; text: string }
  | { kind: 'plain'; name: null; text: string }

/** 名字部分禁用字符：出现句读/换行语义即不是说话人名 */
const NAME_RE = /^[^。．！？!?,，；;：:\s][^。．！？!?,，；;：:]{0,22}[^。．！？!?,，；;：:\s]$/
const SPEAKER_LINE_RE = /^([^:：]{1,26})[：:][ \t]*(.*)$/

function isSpeakerName(raw: string): boolean {
  const n = raw.trim()
  return n.length >= 1 && n.length <= 24 && NAME_RE.test(n)
}

export function parseFormalSegments(raw: string): FormalSegment[] {
  if (!raw) return []
  const out: FormalSegment[] = []
  let current: FormalSegment | null = null

  const flush = () => { if (current) { out.push(current); current = null } }

  for (const line of raw.split('\n')) {
    const m = line.match(SPEAKER_LINE_RE)
    if (m && isSpeakerName(m[1])) {
      const name = m[1].trim()
      const rest = m[2]
      // speaker 段与 heading 段都独立成段（引导行不吞后续内容进 chip 段）
      flush()
      current = rest
        ? { kind: 'speaker', name, text: rest }
        : { kind: 'heading', name, text: '' }
      continue
    }
    if (current) {
      current.text += (current.text ? '\n' : '') + line
    } else {
      const last = out[out.length - 1]
      if (last && last.kind === 'plain') last.text += '\n' + line
      else out.push({ kind: 'plain', name: null, text: line })
    }
  }
  flush()
  return out
}
