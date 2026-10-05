import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    // 组件单测聚焦增量逻辑；DOM 操作（scrollIntoView 等）在测试内按需打桩
    globals: false,
    include: ['src/**/__tests__/**/*.test.ts'],
  },
})
