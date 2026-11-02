/** 治理面纯函数回归（WP-4）：首访轻提示的管理员取数 */
import { describe, expect, it } from 'vitest'
import { firstAdminName } from '@/api/teams'

describe('firstAdminName · 首访轻提示 X 取数', () => {
  it('返回首个 admin 显示名', () => {
    expect(firstAdminName([
      { display_name: '张三', role: 'editor' },
      { display_name: '李四', role: 'admin' },
      { display_name: '王五', role: 'admin' },
    ])).toBe('李四')
  })

  it('无 admin 或空列表返回 null（消费侧降级不猜名）', () => {
    expect(firstAdminName([{ display_name: '张三', role: 'viewer' }])).toBeNull()
    expect(firstAdminName([])).toBeNull()
  })
})
