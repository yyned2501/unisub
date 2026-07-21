import { ref } from 'vue'

/**
 * 包装异步操作，自动管理 loading 状态。
 *
 * @example
 * const { loading, run: loadList } = useAction(async () => {
 *   const data = await getSubscriptions()
 *   list.value = data
 * })
 */
export function useAction<TArgs extends unknown[], TResult>(fn: (...args: TArgs) => Promise<TResult>) {
  const loading = ref(false)

  async function run(...args: TArgs): Promise<TResult | undefined> {
    loading.value = true
    try {
      return await fn(...args)
    } finally {
      loading.value = false
    }
  }

  return { loading, run }
}
