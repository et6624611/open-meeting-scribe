/**
 * AI @ 引用系统 / AI mention system
 *
 * 空态提示承诺「@ 引用原文」：输入框打 @ 唤起引用面板（与 / 指令面板同构互斥），
 * 选定后往输入文本插入短令牌（@原文/@纪要/@随记），消息气泡保持干净；
 * 后端 chat.py 扫描当前轮令牌展开为「用户显式引用」全量上下文块（升级替换采样口径）。
 * Token stays in the message text; the backend expands it into a full-fidelity
 * explicit-citation context block for the current turn only (not for history).
 */
import { ref } from 'vue'

export interface MentionSource {
  /** 中文令牌（后端契约与身份键，恒定不变），如 '@原文' */
  token: string
  /** 英文环境展示/插入的等价令牌（后端 _MENTION_TOKEN_RE 同样接受） */
  tokenEn: string
  /** i18n 裸键（ai-panel 命名空间），模板 t('ai-panel.' + descKey) */
  descKey: string
  /** 分组：meeting=本场会议内容；local=本地文件（面板按组分区展示） */
  group: 'meeting' | 'local'
}

/** 面板候选源（可用性由调用方按当前任务数据过滤）；descKey 为 ai-panel 命名空间裸键，模板 t('ai-panel.' + descKey) */
export const MENTION_SOURCES: MentionSource[] = [
  { token: '@原文', tokenEn: '@transcript', descKey: 'mention_transcript', group: 'meeting' },
  { token: '@纪要', tokenEn: '@summary', descKey: 'mention_summary', group: 'meeting' },
  { token: '@随记', tokenEn: '@notes', descKey: 'mention_notes', group: 'meeting' },
  // @附件 不插令牌：选中后唤起本地文件选择器（AIPanel.selectMention 特判）
  { token: '@附件', tokenEn: '@attachment', descKey: 'mention_attachment', group: 'local' },
]

/** 按语言取展示/插入令牌：zh 环境用中文令牌，其余用英文令牌（须与后端 _MENTION_TOKEN_RE 对齐） */
export function mentionToken(s: MentionSource, locale: string): string {
  return locale.startsWith('zh') ? s.token : s.tokenEn
}

/** 解析输入文本尾部的 @ 激活态：返回 '@' 前的位置（用于回填替换）与过滤 query；未激活返回 null */
export function parseMention(text: string): { at: number; query: string } | null {
  const m = /(?:^|\s)@([^\s@]*)$/.exec(text)
  if (!m) return null
  return { at: m.index + m[0].indexOf('@'), query: m[1] }
}

export function useAiMentions() {
  const mentionOpen = ref(false)
  const mentionIndex = ref(-1)

  function open() { mentionOpen.value = true; mentionIndex.value = 0 }
  function close() { mentionOpen.value = false; mentionIndex.value = -1 }

  function moveDown(count: number) {
    mentionIndex.value = Math.min(mentionIndex.value + 1, count - 1)
  }
  function moveUp() {
    mentionIndex.value = Math.max(mentionIndex.value - 1, 0)
  }

  /** 把尾部 @query 替换为选定令牌 + 空格 */
  function applyMention(text: string, token: string): string {
    const m = parseMention(text)
    if (!m) return text
    return text.slice(0, m.at) + token + ' '
  }

  return { mentionOpen, mentionIndex, open, close, moveDown, moveUp, applyMention }
}
