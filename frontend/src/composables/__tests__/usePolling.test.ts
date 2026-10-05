import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { usePolling } from '@/composables/usePolling'

describe('usePolling', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('立即执行一次，随后按间隔链式调度', async () => {
    let n = 0
    const { start, stop } = usePolling(async () => { n += 1 }, 1000)
    start()
    await vi.advanceTimersByTimeAsync(2500)
    expect(n).toBe(3) // t=0 / 1000 / 2000
    stop()
  })

  it('上一轮在途时跳过本轮：回调永不重叠', async () => {
    let resolveFirst: () => void = () => {}
    const blocking = () => new Promise<void>((r) => { resolveFirst = r })
    let calls = 0
    const { start, stop } = usePolling(async () => { calls += 1; await blocking() }, 1000)
    start()
    expect(calls).toBe(1) // 立即首轮
    await vi.advanceTimersByTimeAsync(3000)
    expect(calls).toBe(1) // 1s/2s/3s 三次 tick 全部因在途被跳过
    resolveFirst()
    await vi.advanceTimersByTimeAsync(1050)
    expect(calls).toBe(2) // 首轮落定后链式调度恢复
    stop()
  })

  it('stop 后不再调度', async () => {
    let n = 0
    const { start, stop } = usePolling(async () => { n += 1 }, 1000)
    start()
    stop()
    await vi.advanceTimersByTimeAsync(3000)
    expect(n).toBe(1)
  })
})
