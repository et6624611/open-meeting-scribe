<template>
  <div class="ws-node">
    <div
      class="ws-node-row"
      :class="{ 'is-dir': node.type === 'dir', 'is-file': node.type === 'file', 'is-active': isActive }"
      :style="{ paddingLeft: `${depth * 12 + 8}px` }"
      @click="onClick"
    >
      <!-- 折叠箭头（仅目录；文件留占位保持对齐） -->
      <svg v-if="node.type === 'dir'" class="ws-tw" :class="{ 'is-open': isOpen }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
      <span v-else class="ws-tw ws-tw-leaf"></span>

      <!-- 类型图标 -->
      <svg v-if="node.type === 'dir'" class="ws-ic" :class="{ 'is-open': isOpen }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2Z"/></svg>
      <svg v-else class="ws-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/></svg>

      <span class="ws-name" :title="node.name">{{ node.name }}</span>
      <span v-if="node.type === 'file' && node.size > 0" class="ws-size">{{ formatSize(node.size) }}</span>
    </div>

    <div v-if="node.type === 'dir' && isOpen" class="ws-children">
      <FileTreeNode
        v-for="child in node.children"
        :key="child.rel_path"
        :node="child"
        :depth="depth + 1"
        :active-path="activePath"
        @select="$emit('select', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { WorkspaceNode } from '@/api/workspace'

const props = defineProps<{
  node: WorkspaceNode
  depth: number
  activePath?: string
}>()

const emit = defineEmits<{
  (e: 'select', relPath: string): void
}>()

const isOpen = ref(props.depth === 0) // 顶层目录默认展开

const isActive = computed(() =>
  props.node.type === 'file' && props.activePath === props.node.rel_path,
)

function onClick() {
  if (props.node.type === 'dir') {
    isOpen.value = !isOpen.value
  } else {
    // 文件：emit 给上层加载预览 / File: emit so parent loads preview
    emit('select', props.node.rel_path)
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}K`
  return `${(bytes / 1024 / 1024).toFixed(1)}M`
}
</script>

<style scoped>
.ws-node { user-select: none; }
.ws-node-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-top: 4px;
  padding-bottom: 4px;
  padding-right: 8px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-secondary, #6b7280);
  font-size: 12px;
  line-height: 1.4;
  transition: background 0.12s, color 0.12s;
}
.ws-node-row:hover { background: var(--hover-bg, rgba(0,0,0,0.04)); color: var(--text-primary, #111827); }
.ws-node-row.is-active { background: var(--accent-soft, rgba(59,130,246,0.12)); color: var(--accent, #3b82f6); }
.ws-node-row.is-dir { font-weight: 500; color: var(--text-primary, #111827); }
.ws-tw {
  width: 12px; height: 12px;
  flex-shrink: 0;
  transition: transform 0.15s;
}
.ws-tw.is-open { transform: rotate(90deg); }
.ws-tw-leaf { display: inline-block; }
.ws-ic { width: 14px; height: 14px; flex-shrink: 0; opacity: 0.8; }
.ws-ic.is-open { color: var(--accent, #3b82f6); }
.ws-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ws-size { font-size: 10px; color: var(--text-tertiary, #9ca3af); flex-shrink: 0; }
</style>
