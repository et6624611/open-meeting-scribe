<script setup lang="ts">
/**
 * 首次知情同意卡（UI 规格 §3，档⑦）——正文=§7 锁定三行（单源组件），仅首次弹一次。
 * 触发：active=true（首次生成/看到纪要）且本用户命名空间无 ack 记录；粒度已裁决：不做每会确认、无全局开关。
 * 按钮："知道了，继续"（关闭并记 ack）/「查看数据位置」（关闭记 ack 并跳 Settings 数据位置分区回看）。
 */
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { scopedGet, scopedSet } from '@/utils/scopedStorage'
import LockedPrivacyBlock from '@/components/common/LockedPrivacyBlock.vue'

const props = defineProps<{ active: boolean }>()
const { t } = useI18n()
const router = useRouter()
const userStore = useUserStore()
const visible = ref(false)

watch(() => props.active, (on) => {
  const uid = userStore.user?.id
  if (on && uid && !scopedGet(uid, 'consent_acknowledged')) visible.value = true
})

function ack() {
  const uid = userStore.user?.id
  if (uid) scopedSet(uid, 'consent_acknowledged', new Date().toISOString())
  visible.value = false
}

function viewLocation() {
  ack()
  router.push('/settings?cat=data_location')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="cg-mask">
      <div class="cg-card" role="alertdialog" aria-modal="true" aria-labelledby="cgTitle">
        <h3 id="cgTitle">{{ t('enterprise.settings.consent.title') }}</h3>
        <LockedPrivacyBlock />
        <div class="cg-actions">
          <button class="cg-btn" @click="ack">{{ t('enterprise.settings.consent.ack') }}</button>
          <button class="cg-btn is-ghost" @click="viewLocation">{{ t('enterprise.settings.consent.view_data_location') }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.cg-mask { position: fixed; inset: 0; background: rgb(0 0 0 / 0.35); display: grid; place-items: center; z-index: var(--z-toast, 1200); }
.cg-card { width: min(440px, calc(100vw - 32px)); background: var(--surface, #fff); border-radius: calc(var(--radius-sm, 8px) * 1.5); padding: calc(var(--s-3, 16px) * 1.5); box-shadow: 0 16px 48px rgb(0 0 0 / 0.2); display: flex; flex-direction: column; gap: var(--s-3, 16px); }
.cg-card h3 { margin: 0; font-size: 15px; }
.cg-actions { display: flex; gap: var(--s-2, 10px); justify-content: flex-end; }
.cg-btn { padding: 8px 16px; border: none; border-radius: var(--radius-sm, 8px); background: var(--accent, #2a6); color: var(--accent-fg, #fff); cursor: pointer; font-size: var(--fs-12, 12px); font-weight: 600; }
.cg-btn.is-ghost { background: none; border: 1px solid var(--border, #d8d8d4); color: var(--fg, #222); font-weight: 400; }
</style>
