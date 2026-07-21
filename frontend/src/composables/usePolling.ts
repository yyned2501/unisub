import { useIntervalFn } from '@vueuse/core'

/**
 * 轮询 composable — 基于 @vueuse/core 的 useIntervalFn。
 * 自动在组件卸载 / 作用域销毁时清理定时器。
 *
 * @param fn 轮询回调
 * @param interval 间隔（毫秒）
 * @param options.immediate 是否立即执行一次（默认 false）
 *
 * @example
 * const { pause, resume, isActive } = usePolling(pollStatus, 3000, { immediate: true })
 */
export function usePolling(
  fn: () => void | Promise<void>,
  interval: number,
  options?: { immediate?: boolean }
) {
  const { pause, resume, isActive } = useIntervalFn(fn, interval, {
    immediate: options?.immediate ?? false,
    immediateCallback: options?.immediate ?? false,
  })

  return { pause, resume, isActive }
}
