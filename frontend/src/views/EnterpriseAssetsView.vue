<script setup lang="ts">
/**
 * 企业 Web 资产窗口（档③3b + P1 词表解禁批）
 *
 * 私有空间：维持"资产只读窗口"裁决（改变本机助手行为的配置只在助手设备做；
 * 服务端权威=助手上传后最新态，文案不写"同步到本机"）。
 * 团队空间（解禁批）：热词=团队共享词表（规格 §5.3——editor+ 可增删词条、viewer 纯列表；
 * 词表是服务端团队资产，不触碰"改本机助手行为"红线）；发言人=U4 裁决维持只读窗口不升共享级。
 * 徽标单源=响应 visibility 字段（本批起真值可为 team，'personal' 硬断言已清理）；
 * 首帧取数走 space.ensureReady 单点（D014 纪律，团队词表深链重载同形态防护）。
 */
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getHotwordsAsset, getSpeakerAliasesAsset, type HotwordsPayload, type Visibility } from '@/api/context'
import { getTeamAsset, isTeamArchived, putTeamAsset } from '@/api/teams'
import { useSpaceStore } from '@/stores/space'
import { showToast } from '@/composables/useToast'
import VisibilityBadge from '@/components/common/VisibilityBadge.vue'

const props = defineProps<{ kind: 'hotwords' | 'speakers' }>()
const { t } = useI18n()
const space = useSpaceStore()

const loading = ref(true)
const rev = ref(0)
const visibility = ref<Visibility>('personal')
const hotwordsText = ref('')
const aliases = ref<Record<string, string>>({})

/** 团队共享词表形态：仅团队空间+热词（发言人 U4=维持个人只读窗口） */
const teamMode = computed(() => space.isTeamSpace && props.kind === 'hotwords')
const teamArchived = computed(() => teamMode.value && !!space.currentTeam && isTeamArchived(space.currentTeam))
const canEditTeamWords = computed(() => teamMode.value && space.canEdit && !teamArchived.value)

const newWord = ref('')
const saving = ref(false)

function newMutationId(): string {
  return (globalThis.crypto?.randomUUID?.() ?? `a-${Date.now()}-${Math.random().toString(36).slice(2)}`)
}

async function load() {
  loading.value = true
  try {
    if (teamMode.value) {
      const a = await getTeamAsset<HotwordsPayload>(space.currentId, 'hotwords')
      rev.value = a.current_rev
      visibility.value = a.visibility ?? 'team'
      hotwordsText.value = a.payload?.hotwords ?? ''
    } else if (props.kind === 'hotwords') {
      const a = await getHotwordsAsset()
      rev.value = a.current_rev
      visibility.value = a.visibility ?? 'personal'
      hotwordsText.value = a.payload?.hotwords ?? ''
    } else {
      const a = await getSpeakerAliasesAsset()
      rev.value = a.current_rev
      visibility.value = a.visibility ?? 'personal'
      aliases.value = a.payload?.aliases ?? {}
    }
  } finally { loading.value = false }
}

onMounted(async () => {
  await space.ensureReady()
  await load()
})

const isEmpty = computed(() => rev.value === 0)
const aliasRows = computed(() => Object.entries(aliases.value))
const wordRows = computed(() => hotwordsText.value.split('\n').map((w) => w.trim()).filter(Boolean))

async function pushWords(next: string[]) {
  if (saving.value || !space.currentTeam) return
  saving.value = true
  try {
    await putTeamAsset(space.currentId, 'hotwords', { hotwords: next.join('\n') }, { idempotencyKey: newMutationId(), baseRev: rev.value })
    rev.value += 1
    hotwordsText.value = next.join('\n')
    showToast(t('enterprise.assets.team_saved'), 'success')
  } catch (err) {
    const status = (err as { response?: { status?: number } })?.response?.status
    if (status === 409) {
      // 词表冲突=整表重读后用户重改（绝不静默覆盖；纪要级 diff 流在 WP-5，词表不做）
      showToast(t('enterprise.assets.team_conflict'), 'error')
      await load()
    } else if (status === 403) {
      showToast(t('enterprise.assets.team_forbidden'), 'error')
    } else {
      showToast(t('enterprise.assets.team_failed'), 'error')
    }
  } finally { saving.value = false }
}

function addWord() {
  const w = newWord.value.trim()
  if (!w || wordRows.value.includes(w)) { newWord.value = ''; return }
  newWord.value = ''
  void pushWords([...wordRows.value, w])
}

function removeWord(word: string) {
  void pushWords(wordRows.value.filter((x) => x !== word))
}
</script>

<template>
  <div class="ea-root">
    <header class="ea-head">
      <h1>{{ kind === 'hotwords' ? t('enterprise.assets.hotwords_title') : t('enterprise.assets.speakers_title') }}</h1>
      <VisibilityBadge :visibility="visibility" />
    </header>

    <!-- 团队共享词表指引（规格 §5.3 逐字）；私有面沿用产品逐字指引 -->
    <p class="ea-guide" role="note">
      {{ teamMode
        ? t('enterprise.assets.team_hotwords_guide')
        : (kind === 'hotwords' ? t('enterprise.assets.hotwords_guide') : t('enterprise.assets.speakers_guide')) }}
    </p>
    <p v-if="teamArchived" class="ea-guide">{{ t('enterprise.assets.team_archived_note') }}</p>

    <p v-if="loading" class="ea-muted">{{ t('enterprise.library.loading') }}</p>
    <p v-else-if="isEmpty && !canEditTeamWords" class="ea-muted">{{ t('enterprise.assets.empty') }}</p>

    <!-- 团队热词=共享词表（editor+ 可增删，viewer 纯列表） -->
    <template v-else-if="teamMode">
      <p v-if="isEmpty" class="ea-muted">{{ t('enterprise.assets.team_empty') }}</p>
      <ul v-if="wordRows.length" class="ea-words">
        <li v-for="w in wordRows" :key="w" class="ea-word">
          <span class="ea-word-text">{{ w }}</span>
          <button v-if="canEditTeamWords" type="button" class="ea-word-del" :aria-label="t('enterprise.assets.remove_word_aria')" :disabled="saving" @click="removeWord(w)">✕</button>
        </li>
      </ul>
      <form v-if="canEditTeamWords" class="ea-add" @submit.prevent="addWord">
        <input v-model="newWord" type="text" :placeholder="t('enterprise.assets.add_placeholder')" :aria-label="t('enterprise.assets.add_placeholder')">
        <button type="submit" :disabled="saving || !newWord.trim()">{{ t('enterprise.assets.add_btn') }}</button>
      </form>
    </template>

    <template v-else-if="kind === 'hotwords'">
      <pre class="ea-hotwords">{{ hotwordsText }}</pre>
    </template>
    <template v-else>
      <table class="ea-table">
        <thead>
          <tr>
            <th>{{ t('enterprise.assets.alias_speaker') }}</th>
            <th>{{ t('enterprise.assets.alias_name') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="[tag, name] in aliasRows" :key="tag">
            <td>{{ tag }}</td>
            <td>{{ name }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </div>
</template>

<style scoped>
.ea-root { max-width: 760px; margin: 0 auto; padding: calc(var(--s-3, 16px) * 1.5); color: var(--fg, #222); }
.ea-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--s-2, 8px); }
.ea-head h1 { font-size: 17px; margin: 0; }
.ea-guide { font-size: var(--fs-12, 12px); color: var(--muted, #666); margin: 0 0 var(--s-3, 16px); }
.ea-muted { color: var(--muted, #666); font-size: var(--fs-12, 12px); }
.ea-hotwords { white-space: pre-wrap; font-family: inherit; font-size: var(--fs-12, 13px); line-height: 1.8; background: var(--surface, #fff); border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); padding: var(--s-3, 16px); margin: 0; }
.ea-words { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.ea-word { display: flex; align-items: center; justify-content: space-between; gap: 8px; background: var(--surface, #fff); border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); padding: 8px 12px; font-size: var(--fs-12, 13px); }
.ea-word-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ea-word-del { border: none; background: none; color: var(--subtle, #999); cursor: pointer; font-size: var(--fs-12, 12px); }
.ea-word-del:hover { color: var(--warn, #c33); }
.ea-word-del:focus-visible { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 1px; }
.ea-add { display: flex; gap: 8px; margin-top: var(--s-3, 14px); }
.ea-add input { flex: 1; padding: 8px 10px; border: 1px solid var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); background: var(--surface-2, #fafaf8); font-size: var(--fs-12, 12px); color: var(--fg, #222); }
.ea-add input:focus { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 1px; }
.ea-add button { padding: 8px 14px; border: none; border-radius: var(--radius-sm, 8px); background: var(--accent, #2a6); color: var(--accent-fg, #fff); font-size: var(--fs-12, 12px); font-weight: 600; cursor: pointer; }
.ea-add button:disabled { opacity: 0.5; cursor: not-allowed; }
.ea-table { width: 100%; border-collapse: collapse; background: var(--surface, #fff); border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); font-size: var(--fs-12, 12px); overflow: hidden; }
.ea-table th, .ea-table td { text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--border, #eee); }
.ea-table th { color: var(--muted, #666); font-weight: 500; }
</style>
