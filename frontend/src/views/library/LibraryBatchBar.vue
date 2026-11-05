<template>
  <!-- 批量操作栏 -->
  <div class="batch-bar" :class="{ visible: selectedCount > 0 }">
    <span class="batch-count">{{ t('library.batch_count', { count: selectedCount }) }}</span>
    <div class="batch-spacer"></div>
    <button class="batch-btn" @click="$emit('batchExport')">{{ t('library.batch_export') }}</button>
    <button v-if="!showArchived" class="batch-btn" @click="$emit('batchArchive')">{{ t('library.batch_archive') }}</button>
    <button v-else class="batch-btn" @click="$emit('batchUnarchive')">{{ t('library.batch_unarchive') }}</button>
    <button class="batch-btn danger" @click="$emit('batchDelete')">{{ t('library.batch_delete') }}</button>
    <button class="batch-close" @click="$emit('clearSelection')" :title="t('library.batch_close')">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
    </button>
  </div>

  <!-- 批量导出格式选择弹窗 -->
  <Teleport to="body">
    <div v-show="showExportDialog" class="export-overlay" data-vue-overlay :class="{ 'is-open': showExportDialog }" @click.self="$emit('update:showExportDialog', false)">
      <div class="export-dialog" role="dialog" aria-modal="true" aria-labelledby="libExportTitle">
        <div class="export-header">
          <h3 id="libExportTitle">{{ t('library.export_dialog_title') }}</h3>
          <button class="export-close" :aria-label="t('common.action.close')" @click="$emit('update:showExportDialog', false)">
            <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6"/></svg>
          </button>
        </div>
        <div class="export-body">
          <p class="export-desc">{{ t('library.export_dialog_desc', { count: exportableCount }) }}</p>
          <div class="export-formats" role="radiogroup" :aria-label="t('library.export_format_label')">
            <label class="export-format" :class="{ 'is-active': exportFormat === 'docx' }">
              <input type="radio" value="docx" :checked="exportFormat === 'docx'" @change="$emit('update:exportFormat', 'docx')" />
              <span class="export-format-text">
                <span class="export-format-name">{{ t('library.export_format_docx') }}</span>
                <span class="export-format-desc">{{ t('library.export_format_docx_desc') }}</span>
              </span>
            </label>
            <label class="export-format" :class="{ 'is-active': exportFormat === 'md' }">
              <input type="radio" value="md" :checked="exportFormat === 'md'" @change="$emit('update:exportFormat', 'md')" />
              <span class="export-format-text">
                <span class="export-format-name">{{ t('library.export_format_md') }}</span>
                <span class="export-format-desc">{{ t('library.export_format_md_desc') }}</span>
              </span>
            </label>
          </div>
        </div>
        <div class="export-footer">
          <button class="export-cancel" @click="$emit('update:showExportDialog', false)">{{ t('library.export_cancel') }} <kbd>ESC</kbd></button>
          <button class="export-confirm" @click="$emit('confirmExport')">{{ t('library.export_confirm', { count: exportableCount }) }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { SummaryFormat } from '@/api/tasks'

const { t } = useI18n()

defineProps<{
  selectedCount: number
  showArchived: boolean
  showExportDialog: boolean
  exportFormat: SummaryFormat
  exportableCount: number
}>()

defineEmits<{
  (e: 'batchExport'): void
  (e: 'batchArchive'): void
  (e: 'batchUnarchive'): void
  (e: 'batchDelete'): void
  (e: 'clearSelection'): void
  (e: 'update:showExportDialog', v: boolean): void
  (e: 'update:exportFormat', v: SummaryFormat): void
  (e: 'confirmExport'): void
}>()
</script>

<style scoped>
/* ─── 批量操作栏 ─── */
.batch-bar {
  display: none; height: 48px; background: var(--fg); color: #fff;
  align-items: center; padding: 0 var(--s-4); gap: var(--s-3); flex-shrink: 0;
}
.batch-bar.visible { display: flex; }
.batch-count { font-size: 13px; font-weight: 500; opacity: 0.8; }
.batch-spacer { flex: 1; }
.batch-btn { padding: 6px 14px; border-radius: var(--radius); font-size: 13px; font-weight: 500; color: #fff; background: rgba(255,255,255,0.12); transition: background 0.15s; border: none; cursor: pointer; }
.batch-btn:hover { background: rgba(255,255,255,0.2); }
.batch-btn.danger { background: rgba(239,68,68,0.2); color: #fca5a5; }
.batch-btn.danger:hover { background: rgba(239,68,68,0.3); }
.batch-close { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; border-radius: var(--radius); color: rgba(255,255,255,0.6); transition: all 0.15s; border: none; cursor: pointer; background: none; }
.batch-close:hover { background: rgba(255,255,255,0.1); color: #fff; }

/* ─── 批量导出弹窗 ─── */
.export-overlay {
  position: fixed; inset: 0; z-index: var(--z-modal); background: var(--overlay-bg);
  display: grid; place-items: center; opacity: 0; pointer-events: none; transition: opacity 0.2s;
}
.export-overlay.is-open { opacity: 1; pointer-events: auto; }
.export-dialog {
  min-width: 420px; max-width: 500px; background: var(--surface);
  border: 1px solid var(--border-strong); border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px oklch(0% 0 0 / 0.10), 0 4px 16px oklch(0% 0 0 / 0.05);
  transform: translateY(8px); opacity: 0; transition: transform 0.25s ease, opacity 0.2s ease;
}
.export-overlay.is-open .export-dialog { transform: translateY(0); opacity: 1; }
.export-header { display: flex; align-items: center; justify-content: space-between; padding: var(--s-4) var(--s-5); border-bottom: 1px solid var(--border); }
.export-header h3 { margin: 0; font-size: var(--fs-15); font-weight: 600; }
.export-close { display: inline-flex; align-items: center; padding: 2px 6px; border: none; background: transparent; cursor: pointer; opacity: 0.6; transition: opacity 0.2s; border-radius: var(--radius-sm); }
.export-close:hover { opacity: 1; background: var(--surface-2); }
.export-close svg { width: 12px; height: 12px; }
.export-body { padding: var(--s-5); }
.export-desc { margin: 0 0 var(--s-4); color: var(--muted); font-size: var(--fs-13); line-height: 1.5; }
.export-formats { display: flex; flex-direction: column; gap: var(--s-2); }
.export-format { display: flex; align-items: flex-start; gap: var(--s-3); padding: var(--s-3) var(--s-4); border: 1px solid var(--border); border-radius: var(--radius); cursor: pointer; transition: border-color 0.15s, background 0.15s; }
.export-format:hover { background: var(--surface-2); }
.export-format.is-active { border-color: var(--accent); background: var(--accent-soft); }
.export-format input[type="radio"] { margin-top: 3px; accent-color: var(--accent); }
.export-format-text { display: flex; flex-direction: column; gap: 2px; }
.export-format-name { font-size: var(--fs-14); font-weight: 500; }
.export-format-desc { font-size: var(--fs-12); color: var(--muted); }
.export-footer { display: flex; gap: var(--s-2); justify-content: flex-end; padding: var(--s-3) var(--s-4); border-top: 1px solid var(--border); }
.export-cancel, .export-confirm { padding: var(--s-2) var(--s-4); border-radius: var(--radius-sm); font-size: var(--fs-14); cursor: pointer; transition: all 0.2s; }
.export-cancel { background: transparent; border: 1px solid var(--border); color: var(--fg); }
.export-cancel:hover { background: var(--surface-2); }
.export-cancel kbd { font-family: var(--font-mono); font-size: 9px; padding: 1px 4px; border-radius: 3px; border: 1px solid var(--border); background: var(--surface-2); color: var(--subtle); line-height: 1.3; margin-left: 4px; }
.export-confirm { background: var(--accent); border: 1px solid var(--accent); color: #fff; }
.export-confirm:hover { background: oklch(from var(--accent) calc(l - 0.06) c h); }
</style>
