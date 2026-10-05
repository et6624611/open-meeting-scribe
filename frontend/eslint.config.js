/**
 * ESLint 配置（flat config, ESLint 9+）
 *
 * L3 防护层：拦截无文本定义的图标按钮，确保不可变更原则不被绕过。
 */

import pluginVue from 'eslint-plugin-vue'
import vueParser from 'vue-eslint-parser'
import tseslint from 'typescript-eslint'
import meetingScribe from './eslint-rules/index.js'

export default [
  // 全局忽略
  {
    ignores: ['dist/**', 'node_modules/**'],
  },

  // Vue SFC 模板检查
  ...pluginVue.configs['flat/recommended'],

  // Vue 文件：明确指定 vue-eslint-parser 为顶层解析器，
  // TypeScript 解析器仅用于 <script> 块
  {
    files: ['src/**/*.vue'],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tseslint.parser,
        extraFileExtensions: ['.vue'],
      },
    },
    plugins: {
      'meeting-scribe': meetingScribe,
    },
    rules: {
      // L3 核心规则：禁止无文本定义的图标按钮
      'meeting-scribe/require-button-label': 'error',

      // 关闭与 TypeScript 或项目风格冲突的 Vue 推荐规则
      'vue/no-unused-vars': 'off',
      'vue/multi-word-component-names': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/attributes-order': 'off',
      'vue/html-self-closing': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/multiline-html-element-content-newline': 'off',
      'vue/html-closing-bracket-spacing': 'off',
      'vue/no-v-html': 'off',
    },
  },
]
