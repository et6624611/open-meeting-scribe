<script setup lang="ts">
/**
 * 企业 Web 资产只读窗口（档③3b，产品裁决 cmsg_01m63m8f1zb261meqx14xsqs9k）
 *
 * 原则："企业 Web = 定稿文字查看编辑面 + 资产的只读窗口；改变本机助手行为的配置只在助手设备做"。
 * 数据源 assets GET（服务端权威=助手上传后最新态；无下行同步属预期语义，文案不写"同步到本机"）。
 */
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getHotwordsAsset, getSpeakerAliasesAsset } from '@/api/context'
import VisibilityBadge from '@/components/common/VisibilityBadge.vue'

const props = defineProps<{ kind: 'hotwords' | 'speakers' }>()
const { t } = useI18n()

const loading = ref(true)
const rev = ref(0)
// 徽标数据属性单源：消费响应 visibility 字段（UI W4 备案项顺手落地，P0 值恒 personal）
const visibility = ref<'personal'>('personal')
const hotwordsText = ref('')
const aliases = ref<Record<string, string>>({})

onMounted(async () => {
  try {
    if (props.kind === 'hotwords') {
      const a = await getHotwordsAsset()
      rev.value = a.current_rev
      visibility.value = (a.visibility ?? 'personal') as 'personal'
      hotwordsText.value = a.payload?.hotwords ?? ''
    } else {
      const a = await getSpeakerAliasesAsset()
      rev.value = a.current_rev
      visibility.value = (a.visibility ?? 'personal') as 'personal'
      aliases.value = a.payload?.aliases ?? {}
    }
  } finally { loading.value = false }
})

const isEmpty = computed(() => rev.value === 0)
const aliasRows = computed(() => Object.entries(aliases.value))
</script>

<template>
  <div class="ea-root">
    <header class="ea-head">
      <h1>{{ kind === 'hotwords' ? t('enterprise.assets.hotwords_title') : t('enterprise.assets.speakers_title') }}</h1>
      <VisibilityBadge :visibility="visibility" />
    </header>

    <!-- 产品逐字指引（热词）；发言人同逻辑口径 -->
    <p class="ea-guide" role="note">
      {{ kind === 'hotwords'
        ? t('enterprise.assets.hotwords_guide')
        : t('enterprise.assets.speakers_guide') }}
    </p>

    <p v-if="loading" class="ea-muted">{{ t('enterprise.library.loading') }}</p>
    <p v-else-if="isEmpty" class="ea-muted">{{ t('enterprise.assets.empty') }}</p>

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
.ea-table { width: 100%; border-collapse: collapse; background: var(--surface, #fff); border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); font-size: var(--fs-12, 12px); overflow: hidden; }
.ea-table th, .ea-table td { text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--border, #eee); }
.ea-table th { color: var(--muted, #666); font-weight: 500; }
</style>
