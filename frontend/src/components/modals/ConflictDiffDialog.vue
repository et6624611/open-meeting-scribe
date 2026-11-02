<script setup lang="ts">
/**
 * 冲突对照合并弹窗（WP-5，规格 §6 下限形态=交付形态）
 *
 * 装载=409{current_rev, latest 全文}（契约必含项①）两版文本；输出=逐 change 块取舍后的合并文本。
 * 语义钉（规格逐字）：取消=弃稿装载新版；确认=新 Idempotency-Key+If-Match=current_rev 重推（调用侧执行）；
 * 绝不静默覆盖、冲突不记留痕（P1 裁）。
 * 多字段（纪要+笔记）=tab 切换；单字段（词表）=并排退化——同一组件两种形态，零额外实现。
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { allChoices, diffParas, mergedText, splitParas, type ChangeChoice } from '@/utils/paraDiff'

export interface DiffField {
  key: string
  label: string
  serverText: string
  myText: string
}

const props = defineProps<{ fields: DiffField[]; submitting?: boolean; /** 短文本参数化（规格 §6）：词表等单行条目=按行分段（每词条一段），纪要/笔记默认空行分段 */ lineMode?: boolean }>()
const emit = defineEmits<{
  /** 取消=弃稿装载新版（规格逐字语义，调用侧负责 load 最新并保留提示） */
  cancel: []
  /** 确认=逐字段合并文本（Record<field.key, mergedText>），重推由调用侧执行 */
  confirm: [merged: Record<string, string>]
}>()

const { t } = useI18n()

// 装载即定型：ops/choices 按 key 建表，父级更新 fields 时整窗重开（不做半路换数据源）
function splitUnits(text: string): string[] {
  return props.lineMode
    ? text.split('\n').map((w) => w.trim()).filter(Boolean) // 词表退化：每词条一段，行级取舍
    : splitParas(text)
}
const blocksByField = computed(() =>
  props.fields.map((f) => ({
    ...f,
    ops: diffParas(splitUnits(f.serverText), splitUnits(f.myText)),
  })),
)
const activeKey = ref(props.fields[0]?.key ?? '')
/** choices[fieldIdx][blockIdx]——默认全"我的"（用户刚做的编辑意图优先保），快捷钮可整体翻转，逐块可改 */
const choices = ref<Record<string, Record<number, ChangeChoice>>>(
  Object.fromEntries(blocksByField.value.map((b) => [b.key, { ...allChoices(b.ops, 'mine') }])),
)

function setAll(pick: ChangeChoice) {
  const next: Record<string, Record<number, ChangeChoice>> = {}
  for (const b of blocksByField.value) next[b.key] = { ...allChoices(b.ops, pick) }
  choices.value = next
}

const hasChangeBlocks = computed(() => blocksByField.value.some((b) => b.ops.some((o) => o.kind === 'change')))

function onConfirm() {
  const out: Record<string, string> = {}
  for (const b of blocksByField.value) out[b.key] = mergedText(b.ops, choices.value[b.key] ?? {})
  emit('confirm', out)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && !props.submitting) emit('cancel')
}
</script>

<template>
  <Teleport to="body">
    <div class="cdd-overlay" @keydown="onKeydown">
      <div class="cdd-modal" role="dialog" aria-modal="true" :aria-label="t('enterprise.diff.title')">
        <header class="cdd-head">
          <div>
            <h2 class="cdd-title">{{ t('enterprise.diff.title') }}</h2>
            <p class="cdd-desc">{{ t('enterprise.diff.desc') }}</p>
          </div>
          <div class="cdd-quick">
            <button type="button" class="cdd-quick-btn" :disabled="submitting || !hasChangeBlocks" @click="setAll('theirs')">{{ t('enterprise.diff.all_theirs') }}</button>
            <button type="button" class="cdd-quick-btn" :disabled="submitting || !hasChangeBlocks" @click="setAll('mine')">{{ t('enterprise.diff.all_mine') }}</button>
          </div>
        </header>

        <!-- 多字段 tab（纪要/笔记）；单字段自然退化不显 tab 轨 -->
        <nav v-if="fields.length > 1" class="cdd-tabs" role="tablist">
          <button
            v-for="f in fields"
            :key="f.key"
            role="tab"
            :class="{ 'is-active': activeKey === f.key }"
            :aria-selected="activeKey === f.key"
            @click="activeKey = f.key"
          >{{ f.label }}</button>
        </nav>

        <div class="cdd-body">
          <template v-for="field in blocksByField" :key="field.key">
            <div v-show="field.key === activeKey" class="cdd-ops">
              <template v-for="(op, idx) in field.ops" :key="idx">
                <p v-if="op.kind === 'same'" class="cdd-same">{{ op.text }}</p>
                <div v-else class="cdd-change">
                  <div class="cdd-col" :class="{ 'is-picked': (choices[field.key] ?? {})[idx] === 'theirs' }">
                    <div class="cdd-col-head">
                      <label class="cdd-pick">
                        <input
                          type="radio"
                          :name="`${field.key}-${idx}`"
                          :checked="(choices[field.key] ?? {})[idx] === 'theirs'"
                          :disabled="submitting"
                          @change="((choices[field.key] ??= {})[idx] = 'theirs')"
                        />
                        {{ t('enterprise.diff.server_new') }}
                      </label>
                    </div>
                    <p v-if="op.theirs.length" class="cdd-col-text">{{ op.theirs.join('\n\n') }}</p>
                    <p v-else class="cdd-col-empty">{{ t('enterprise.diff.empty_side') }}</p>
                  </div>
                  <div class="cdd-col" :class="{ 'is-picked': (choices[field.key] ?? {})[idx] !== 'theirs' }">
                    <div class="cdd-col-head">
                      <label class="cdd-pick">
                        <input
                          type="radio"
                          :name="`${field.key}-${idx}`"
                          :checked="(choices[field.key] ?? {})[idx] !== 'theirs'"
                          :disabled="submitting"
                          @change="((choices[field.key] ??= {})[idx] = 'mine')"
                        />
                        {{ t('enterprise.diff.my_change') }}
                      </label>
                    </div>
                    <p v-if="op.mine.length" class="cdd-col-text">{{ op.mine.join('\n\n') }}</p>
                    <p v-else class="cdd-col-empty">{{ t('enterprise.diff.empty_side') }}</p>
                  </div>
                </div>
              </template>
              <p v-if="!field.ops.length" class="cdd-col-empty">{{ t('enterprise.diff.empty_side') }}</p>
            </div>
          </template>
        </div>

        <footer class="cdd-foot">
          <p class="cdd-foot-hint">{{ t('enterprise.diff.cancel_hint') }}</p>
          <div class="cdd-foot-actions">
            <button type="button" class="cdd-btn-ghost" :disabled="submitting" @click="emit('cancel')">{{ t('common.action.cancel') }}</button>
            <button type="button" class="cdd-btn-primary" :disabled="submitting || !hasChangeBlocks" @click="onConfirm">
              {{ submitting ? t('enterprise.detail.saving') : t('enterprise.diff.confirm') }}
            </button>
          </div>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* 弹出层纪律：Teleport 挂 body+fixed（D019 归正后的仓内标准形态） */
.cdd-overlay { position: fixed; inset: 0; z-index: 2000; background: rgba(20, 20, 18, 0.45); display: flex; align-items: center; justify-content: center; padding: var(--s-4, 20px); }
.cdd-modal { width: min(860px, 100%); max-height: 86vh; display: flex; flex-direction: column; background: var(--surface, #fff); border-radius: var(--radius-lg, 14px); box-shadow: 0 24px 64px rgba(0, 0, 0, 0.22); color: var(--fg, #222); }
.cdd-head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--s-3, 16px); padding: var(--s-4, 20px) var(--s-5, 24px) var(--s-3, 14px); border-bottom: 1px solid var(--border, #e6e6e2); }
.cdd-title { font-size: 15px; margin: 0 0 4px; }
.cdd-desc { font-size: var(--fs-12, 12px); color: var(--muted, #666); margin: 0; max-width: 460px; line-height: 1.7; }
.cdd-quick { display: flex; gap: 8px; flex: none; }
.cdd-quick-btn { padding: 6px 12px; border: 1px solid var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); background: var(--surface, #fff); color: var(--fg, #222); font-size: var(--fs-12, 12px); cursor: pointer; }
.cdd-quick-btn:hover:not(:disabled) { border-color: var(--accent, #2a6); color: var(--accent, #2a6); }
.cdd-quick-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.cdd-tabs { display: flex; gap: 2px; padding: 0 var(--s-5, 24px); border-bottom: 1px solid var(--border, #e6e6e2); }
.cdd-tabs button { padding: 8px 14px; font-size: var(--fs-12, 12px); color: var(--muted, #666); background: none; border: none; border-bottom: 2px solid transparent; margin-bottom: -1px; cursor: pointer; }
.cdd-tabs button.is-active { color: var(--accent, #2a6); border-bottom-color: var(--accent, #2a6); font-weight: 600; }
.cdd-body { flex: 1; overflow: auto; padding: var(--s-4, 18px) var(--s-5, 24px); }
.cdd-ops { display: flex; flex-direction: column; gap: 12px; }
.cdd-same { margin: 0; font-size: var(--fs-12, 12px); line-height: 1.8; color: var(--subtle, #999); white-space: pre-wrap; border-left: 2px solid var(--border, #e6e6e2); padding-left: 10px; }
.cdd-change { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.cdd-col { border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 10px); padding: 10px 12px; background: var(--surface, #fff); transition: border-color 0.15s ease, background 0.15s ease; }
.cdd-col.is-picked { border-color: var(--accent, #2a6); background: var(--accent-soft, #f2faf4); }
.cdd-col-head { margin-bottom: 6px; }
.cdd-pick { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-11, 11px); color: var(--muted, #666); cursor: pointer; }
.cdd-pick input { accent-color: var(--accent, #2a6); }
.cdd-col-text { margin: 0; font-size: var(--fs-12, 12px); line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }
.cdd-col-empty { margin: 0; font-size: var(--fs-11, 11px); color: var(--subtle, #aaa); font-style: italic; }
.cdd-foot { display: flex; justify-content: space-between; align-items: center; gap: var(--s-3, 16px); padding: var(--s-3, 14px) var(--s-5, 24px) var(--s-4, 18px); border-top: 1px solid var(--border, #e6e6e2); }
.cdd-foot-hint { margin: 0; font-size: var(--fs-11, 11px); color: var(--subtle, #999); }
.cdd-foot-actions { display: flex; gap: 10px; flex: none; }
.cdd-btn-ghost { padding: 7px 16px; border: 1px solid var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); background: none; color: var(--muted, #666); font-size: var(--fs-12, 12px); cursor: pointer; }
.cdd-btn-ghost:hover:not(:disabled) { color: var(--fg, #222); }
.cdd-btn-primary { padding: 7px 18px; border: none; border-radius: var(--radius-sm, 8px); background: var(--accent, #2a6); color: var(--accent-fg, #fff); font-weight: 600; font-size: var(--fs-12, 12px); cursor: pointer; }
.cdd-btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.cdd-btn-primary:focus-visible, .cdd-btn-ghost:focus-visible { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 2px; }
@media (max-width: 720px) { .cdd-change { grid-template-columns: 1fr; } }
</style>
