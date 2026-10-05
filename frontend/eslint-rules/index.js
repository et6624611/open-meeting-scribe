/**
 * 本地 ESLint 插件：eslint-plugin-meeting-scribe
 *
 * 封装项目级不可变更原则为 lint 规则，CI 拦截违规代码。
 */

import requireButtonLabel from './require-button-label.js'

const plugin = {
  rules: {
    'require-button-label': requireButtonLabel,
  },
}

export default plugin
