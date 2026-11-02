<script setup lang="ts">
/**
 * 企业版顶栏右侧用户菜单（UI 规格 §1）：头像 + 设置 / 我的数据在哪 / 退出登录，
 * 管理员额外"进入管理台"。员工端除该入口外不出现任何管理功能（§4 边界）。
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useSpaceStore } from '@/stores/space'
import { usePopMenu } from '@/composables/usePopMenu'

const { t } = useI18n()
const router = useRouter()
const userStore = useUserStore()

const btnEl = ref<HTMLElement | null>(null)
const menuEl = ref<HTMLElement | null>(null)
const { visible, close, toggle, triggerAttrs, menuAttrs } = usePopMenu(menuEl, btnEl)

async function onLogout() {
  close()
  await userStore.logout()
  // 空间上下文随登出清态（W1-04 清态纪律；last_space 键本身由 purgeUserScopedData 覆盖）
  useSpaceStore().reset()
  router.replace('/login')
}

function go(path: string) {
  close()
  router.push(path)
}
</script>

<template>
  <div class="ent-user-menu">
    <button
      ref="btnEl" class="ent-avatar-btn" v-bind="triggerAttrs" aria-haspopup="true"
      :aria-expanded="visible ? 'true' : 'false'" @click="toggle"
    >
      <span class="ent-avatar" aria-hidden="true">{{ userStore.avatarLetter }}</span>
      <span class="ent-avatar-name">{{ userStore.displayName }}</span>
    </button>
    <div v-show="visible" ref="menuEl" class="ent-menu" v-bind="menuAttrs" role="menu">
      <button role="menuitem" @click="go('/settings')">{{ t('enterprise.menu.settings') }}</button>
      <button role="menuitem" @click="go('/settings?cat=data_location')">{{ t('enterprise.menu.where_is_my_data') }}</button>
      <button v-if="userStore.isAdmin" role="menuitem" @click="go('/admin')">{{ t('enterprise.menu.enter_admin') }}</button>
      <hr class="ent-menu-sep">
      <button role="menuitem" class="is-danger" @click="onLogout">{{ t('enterprise.menu.logout') }}</button>
    </div>
  </div>
</template>

<style scoped>
.ent-user-menu { position: relative; }
.ent-avatar-btn {
  display: flex;
  align-items: center;
  gap: var(--s-2, 8px);
  padding: 4px 10px 4px 4px;
  border: 1px solid var(--border, #e2e2de);
  border-radius: 999px;
  background: var(--surface, #fff);
  color: var(--fg, #222);
  cursor: pointer;
  font-size: var(--fs-12, 12px);
}
.ent-avatar-btn:hover { background: var(--surface-2, #fafaf8); }
.ent-avatar-btn:focus-visible { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 2px; }
.ent-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--accent, #2a6);
  color: var(--accent-fg, #fff);
  display: grid;
  place-items: center;
  font-size: var(--fs-11, 11px);
  font-weight: 600;
}
.ent-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  z-index: var(--z-popover, 1000);
  min-width: 180px;
  padding: var(--s-2, 8px) 0;
  background: var(--surface, #fff);
  border: 1px solid var(--border, #e2e2de);
  border-radius: var(--radius-sm, 8px);
  box-shadow: 0 8px 24px rgb(0 0 0 / 0.1);
}
.ent-menu button {
  display: block;
  width: 100%;
  padding: 8px 14px;
  border: none;
  background: none;
  text-align: left;
  font-size: var(--fs-12, 12px);
  color: var(--fg, #222);
  cursor: pointer;
}
.ent-menu button:hover { background: var(--surface-2, #fafaf8); }
.ent-menu button.is-danger { color: var(--warn, #c33); }
.ent-menu-sep { margin: var(--s-2, 8px) 0; border: none; border-top: 1px solid var(--border, #eee); }
</style>
