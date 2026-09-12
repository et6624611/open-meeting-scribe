<template>
  <!-- 知识库关联引导弹窗 -->
  <div v-if="modelValue" class="proj-onboarding-overlay" @click.self="emit('close')" @keydown.esc="emit('close')">
    <div class="proj-onboarding-card" role="dialog" aria-modal="true" aria-labelledby="projObDialogTitle">
      <!-- 标题区（复用说话人引导弹窗样式） -->
      <div class="spk-ob-header">
        <h3 id="projObDialogTitle">{{ t('generating.project_onboarding.title') }}</h3>
      </div>
      <!-- 演示区：空知识库 → 文档 + 纪要回写 -->
      <div class="proj-ob-demo">
        <div class="proj-ob-scene" :class="{ connected }">
          <!-- 左：知识库文件夹 -->
          <div class="proj-ob-folder">
            <div class="proj-ob-folder-icon">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            </div>
            <span class="proj-ob-folder-label">{{ t('generating.project_onboarding.knowledge_base') }}</span>
            <!-- 文件夹内的文档 -->
            <div class="proj-ob-docs">
              <div class="proj-ob-doc">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                <span>.md</span>
              </div>
              <div class="proj-ob-doc">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                <span>.pdf</span>
              </div>
            </div>
          </div>
          <!-- 中：双向连接通道 -->
          <div class="proj-ob-connector">
            <!-- 上路：知识 → AI -->
            <div class="proj-ob-flow proj-ob-flow--right">
              <svg class="proj-ob-flow-svg" viewBox="0 0 90 10" preserveAspectRatio="none">
                <line class="proj-ob-flow-line" x1="0" y1="5" x2="82" y2="5"/>
                <polygon class="proj-ob-flow-arrow" points="80,1 90,5 80,9"/>
              </svg>
              <span class="proj-ob-flow-label">{{ t('generating.project_onboarding.ai_citation') }}</span>
            </div>
            <!-- 下路：纪要 ← AI（带回流文档图标） -->
            <div class="proj-ob-flow proj-ob-flow--left">
              <svg class="proj-ob-flow-svg" viewBox="0 0 90 10" preserveAspectRatio="none">
                <line class="proj-ob-flow-line" x1="8" y1="5" x2="90" y2="5"/>
                <polygon class="proj-ob-flow-arrow" points="10,1 0,5 10,9"/>
              </svg>
              <!-- 回流文件实体 -->
              <div class="proj-ob-flow-doc">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              </div>
              <span class="proj-ob-flow-label">{{ t('generating.project_onboarding.notes_sync') }}</span>
            </div>
          </div>
          <!-- 右：AI + 用户生态 -->
          <div class="proj-ob-right">
            <div class="proj-ob-ai">
              <div class="proj-ob-ai-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8z"/></svg>
              </div>
              <span class="proj-ob-ai-label">{{ t('generating.project_onboarding.ai_context') }}</span>
            </div>
            <div class="proj-ob-user-eco">
              <div class="proj-ob-user-eco-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>
              </div>
              <span class="proj-ob-user-eco-label">{{ t('generating.project_onboarding.user_eco') }}</span>
            </div>
          </div>
        </div>
      </div>
      <!-- 底部操作区（复用说话人引导弹窗样式） -->
      <div class="spk-ob-footer">
        <button type="button" class="spk-ob-got-it" @click="emit('close')">{{ t('generating.project_onboarding.got_it') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps<{
  modelValue: boolean
  connected: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()
</script>
