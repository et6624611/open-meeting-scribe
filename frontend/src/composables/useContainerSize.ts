import { ref, computed, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'

/**
 * 容器宽度档位检测 composable + 全局断点常量 / Container width tier detection composable + global breakpoint constants
 *
 * 统一封装 ResizeObserver 逻辑，将容器宽度映射为标准化 tier 等级， / Unified ResizeObserver logic; maps container width to standardized tier levels,
 * 并输出兼容现有 CSS 类名约定的 class（is-xnarrow / is-narrow / is-compact）。 / and outputs CSS classes compatible with existing conventions (is-xnarrow / is-narrow / is-compact).
 *
 * ## 断点体系 / Breakpoint system
 * - **JS 层（容器级）**：通过 `BREAKPOINTS` 常量统一管理，供 composable 和组件引用 / **JS layer (container-level)**: unified via `BREAKPOINTS` constants for composable/component use
 * - **CSS 层（视口级）**：@media 查询处理结构性布局切换（如并排→Tab），断点值独立维护 / **CSS layer (viewport-level)**: @media queries handle structural layout switches (e.g. side-by-side → tabs); breakpoints maintained independently
 * - 两层职责分离：JS 管内容降级，CSS 管结构切换 / Separation of concerns: JS handles content degradation, CSS handles structural switching
 */

/**
 * 全局容器断点常量（单位 px） / Global container breakpoint constants (px)
 *
 * 所有需要按容器宽度做降级判断的 JS/TS 代码应引用此常量， / All JS/TS code needing width-based degradation should reference these constants,
 * 而非各自硬编码魔法数字。 / rather than hardcoding magic numbers.
 */
export const BREAKPOINTS = {
  xs: 480,
  sm: 640,
  md: 860,
  lg: 1080,
} as const

/** 容器宽度档位：xs → 最窄，full → 最宽 / Container width tier: xs → narrowest, full → widest */
export type SizeTier = 'xs' | 'sm' | 'md' | 'lg' | 'full'

/** 断点配置（单位 px），所有字段可选，未填使用默认值 / Breakpoint config (px); all fields optional, defaults used if omitted */
export interface Breakpoints {
  xs?: number   // 默认 480
  sm?: number   // 默认 640
  md?: number   // 默认 860
  lg?: number   // 默认 1080
}

interface UseContainerSizeOptions {
  /** 自定义断点，与默认值合并 / Custom breakpoints, merged with defaults */
  breakpoints?: Breakpoints
}

interface UseContainerSizeReturn {
  /** 当前容器像素宽度 / Current container pixel width */
  width: Ref<number>
  /** 当前档位标识 / Current tier identifier */
  tier: ComputedRef<SizeTier>
  /** 兼容 CSS 类名：is-xnarrow / is-narrow / is-compact / 空串 / Compatible CSS class: is-xnarrow / is-narrow / is-compact / empty string */
  widthClass: ComputedRef<string>
  /** 宽度 ≤ sm 断点（≈ 原 is-xnarrow + is-narrow 合并） / Width ≤ sm breakpoint (≈ former is-xnarrow + is-narrow combined) */
  isCompact: ComputedRef<boolean>
  /** 宽度 ≤ md 断点（≈ 原 is-compact 及以上） / Width ≤ md breakpoint (≈ former is-compact and above) */
  isNarrow: ComputedRef<boolean>
}

export function useContainerSize(
  elRef: Ref<HTMLElement | null>,
  options?: UseContainerSizeOptions,
): UseContainerSizeReturn {
  const width = ref(0)
  let observer: ResizeObserver | null = null

  // 合并断点：用户自定义覆盖默认值（引用全局常量） / Merge breakpoints: user custom overrides on defaults (references global constants)
  const bp = {
    xs: BREAKPOINTS.xs,
    sm: BREAKPOINTS.sm,
    md: BREAKPOINTS.md,
    lg: BREAKPOINTS.lg,
    ...options?.breakpoints,
  }

  /** 当前档位 / Current tier */
  const tier = computed<SizeTier>(() => {
    const w = width.value
    if (w <= bp.xs) return 'xs'
    if (w <= bp.sm) return 'sm'
    if (w <= bp.md) return 'md'
    if (w <= bp.lg) return 'lg'
    return 'full'
  })

  /**
   * 兼容 CSS 类名 / Compatible CSS class
   * 与原 App.vue / LibraryView 内联 updateWidthClass 完全等价： / Fully equivalent to former inline updateWidthClass in App.vue / LibraryView:
   *   ≤480 → 'is-xnarrow' | ≤640 → 'is-narrow' | ≤860 → 'is-compact' | >860 → ''
   */
  const widthClass = computed<string>(() => {
    const w = width.value
    if (w <= bp.xs) return 'is-xnarrow'
    if (w <= bp.sm) return 'is-narrow'
    if (w <= bp.md) return 'is-compact'
    return ''
  })

  const isCompact = computed(() => width.value <= bp.sm)
  const isNarrow = computed(() => width.value <= bp.md)

  onMounted(() => {
    if (!elRef.value) return
    observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        width.value = entry.contentRect.width
      }
    })
    observer.observe(elRef.value)
    // 初始化，避免首帧 width=0 闪烁 / Initialize to avoid first-frame width=0 flicker
    width.value = elRef.value.clientWidth
  })

  onBeforeUnmount(() => {
    observer?.disconnect()
    observer = null
  })

  return { width, tier, widthClass, isCompact, isNarrow }
}
