/**
 * require-button-label 规则单测 / Unit tests for the require-button-label rule
 *
 * 覆盖四类 fixture：label 属性、直接/嵌套可见文本、纯图标违规、v-if 盲点（已知局限）。
 */
import { describe, it } from 'vitest'
import { RuleTester } from 'eslint'
import vueParser from 'vue-eslint-parser'
import rule from '../require-button-label.js'

// vitest globals: false —— 将 RuleTester 的用例注册桥接到 vitest
;(RuleTester as unknown as { describe: (n: string, f: () => void) => void }).describe = (name, fn) => describe(name, fn)
;(RuleTester as unknown as { it: (n: string, f: () => void) => void }).it = (name, fn) => it(name, fn)

const ruleTester = new RuleTester({
  languageOptions: {
    parser: vueParser,
    ecmaVersion: 'latest',
    sourceType: 'module',
  },
})

const sfc = (template: string): string =>
  `<template>\n${template}\n</template>\n\n<script setup>\nconst t = (k) => k\n</script>\n`

ruleTester.run('require-button-label', rule, {
  valid: [
    // label 属性（静态 title / 动态 :aria-label / data-tip）
    { code: sfc(`<button title="关闭"><svg /></button>`), filename: 'a.vue' },
    { code: sfc(`<button :aria-label="t('common.action.close')"><svg /></button>`), filename: 'a.vue' },
    { code: sfc(`<button data-tip="关闭"><svg /></button>`), filename: 'a.vue' },
    // 直接可见文本
    { code: sfc(`<button>保存</button>`), filename: 'a.vue' },
    // 嵌套子元素内的可见文本（2026-11-04 递归修复的回归用例）
    { code: sfc(`<button><span>{{ t('task.copy_title') }}</span></button>`), filename: 'a.vue' },
    // 已知盲点（规则头注释）：文本仅来自 v-if 后代时静态分析无法证伪，规则放行
    { code: sfc(`<button><span v-if="hidden">{{ t('x') }}</span></button>`), filename: 'a.vue' },
  ],
  invalid: [
    // 纯图标、无任何文本定义
    {
      code: sfc(`<button><svg /></button>`),
      filename: 'a.vue',
      errors: [{ messageId: 'missingLabel' }],
    },
    // 只有 v-if 为假的 svg、无 label 属性
    {
      code: sfc(`<button><svg v-if="hidden" /></button>`),
      filename: 'a.vue',
      errors: [{ messageId: 'missingLabel' }],
    },
  ],
})
