import { ref } from 'vue'

export interface QuoteRef {
  text: string
  source: string
  blockIndex: number
}

export interface RewritePending {
  originalText: string
  source: string
  blockIndex: number
}

const quoteRef = ref<QuoteRef | null>(null)
const rewritePending = ref<RewritePending | null>(null)

type BlockUpdater = (blockIndex: number, newSource: string) => void

let blockUpdateFn: BlockUpdater | null = null

export function useQuoteRef() {
  function setQuote(text: string, source: string, blockIndex = -1) {
    quoteRef.value = {
      text: text.length > 200 ? text.slice(0, 200) + '…' : text,
      source,
      blockIndex,
    }
  }

  function clearQuote() {
    quoteRef.value = null
  }

  function getQuoteContext(): { context: string; cleared: boolean } | null {
    if (!quoteRef.value) return null
    const q = quoteRef.value
    const srcLabel = q.source + (q.blockIndex >= 0 ? ` · 第 ${q.blockIndex + 1} 块` : '')
    const context = `[用户引用了一段内容（${srcLabel}）]:\n"""${q.text}"""\n`
    clearQuote()
    return { context, cleared: true }
  }

  function startRewrite(text: string, source: string, blockIndex: number) {
    rewritePending.value = { originalText: text, source, blockIndex }
  }

  function clearRewrite() {
    rewritePending.value = null
  }

  function registerBlockUpdater(fn: BlockUpdater | null) {
    blockUpdateFn = fn
  }

  function acceptRewrite(aiText: string): boolean {
    if (!rewritePending.value || !blockUpdateFn) return false
    const { blockIndex } = rewritePending.value
    if (blockIndex < 0) return false
    blockUpdateFn(blockIndex, aiText + ' <!--ai-->')
    rewritePending.value = null
    return true
  }

  return {
    quoteRef,
    rewritePending,
    setQuote,
    clearQuote,
    getQuoteContext,
    startRewrite,
    clearRewrite,
    registerBlockUpdater,
    acceptRewrite,
  }
}
