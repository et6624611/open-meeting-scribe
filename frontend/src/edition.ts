/**
 * 产品线形态开关 / Product edition switch
 *
 * 双产品线 = 同一代码库、两种打包：VITE_EDITION=enterprise 时构建企业版形态。
 * 个人版不注入该变量，行为零变化（裁决①双产品线战略）。
 * Dual product lines from one codebase; enterprise build sets VITE_EDITION=enterprise.
 */
export type Edition = 'personal' | 'enterprise'

export const EDITION: Edition =
  import.meta.env.VITE_EDITION === 'enterprise' ? 'enterprise' : 'personal'

export const isEnterprise = EDITION === 'enterprise'
