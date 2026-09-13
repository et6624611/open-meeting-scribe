import { ref, computed, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'

/**
 * 容器宽度档位检测 composable
 *
 * 统一封装 ResizeObserver 逻辑，将容器宽度映射为标准化 tier 等级，
 * 并输出兼容现有 CSS 类名约定的 class（is-xnarrow / is-narrow / is-compact）。
 *
 * 默认断点与原有 App.vue / LibraryView 内联逻辑完全一致，确保迁移零回归。
 */

/** 容器宽度档位：xs → 最窄，full → 最宽 */
export type SizeTier = 'xs' | 'sm' | 'md' | 'lg' | 'full'

/** 断点配置（单位 px），所有字段可选，未填使用默认值 */
export interface Breakpoints {
  xs?: number   // 默认 480
  sm?: number   // 默认 640
  md?: number   // 默认 860
  lg?: number   // 默认 1080
}

interface UseContainerSizeOptions {
  /** 自定义断点，与默认值合并 */
  breakpoints?: Breakpoints
}

interface UseContainerSizeReturn {
  /** 当前容器像素宽度 */
  width: Ref<number>
  /** 当前档位标识 */
  tier: ComputedRef<SizeTier>
  /** 兼容 CSS 类名：is-xnarrow / is-narrow / is-compact / 空串 */
  widthClass: ComputedRef<string>
  /** 宽度 ≤ sm 断点（≈ 原 is-xnarrow + is-narrow 合并） */
  isCompact: ComputedRef<boolean>
  /** 宽度 ≤ md 断点（≈ 原 is-compact 及以上） */
  isNarrow: ComputedRef<boolean>
}

export function useContainerSize(
  elRef: Ref<HTMLElement | null>,
  options?: UseContainerSizeOptions,
): UseContainerSizeReturn {
  const width = ref(0)
  let observer: ResizeObserver | null = null

  // 合并断点：用户自定义覆盖默认值
  const bp = {
    xs: 480,
    sm: 640,
    md: 860,
    lg: 1080,
    ...options?.breakpoints,
  }

  /** 当前档位 */
  const tier = computed<SizeTier>(() => {
    const w = width.value
    if (w <= bp.xs) return 'xs'
    if (w <= bp.sm) return 'sm'
    if (w <= bp.md) return 'md'
    if (w <= bp.lg) return 'lg'
    return 'full'
  })

  /**
   * 兼容 CSS 类名
   * 与原 App.vue / LibraryView 内联 updateWidthClass 完全等价：
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
    // 初始化，避免首帧 width=0 闪烁
    width.value = elRef.value.clientWidth
  })

  onBeforeUnmount(() => {
    observer?.disconnect()
    observer = null
  })

  return { width, tier, widthClass, isCompact, isNarrow }
}
