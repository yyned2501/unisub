import { ref, computed } from 'vue'
import type { Ref, ComputedRef } from 'vue'

/**
 * 前端分页 composable — 对已有的完整列表做客户端切片分页。
 *
 * @param source 完整数据列表（ref 或 computed）
 * @param pageSize 每页条数（默认 20）
 *
 * @example
 * const { page, totalPages, pagedList, setPage, reset } = usePagedList(filteredList, 20)
 * // 模板：<n-pagination :page="page" :page-count="totalPages" @update:page="setPage" />
 */
export function usePagedList<T>(source: Ref<T[]> | ComputedRef<T[]>, pageSize = 20) {
  const page = ref(1)

  const totalPages = computed(() => Math.max(1, Math.ceil(source.value.length / pageSize)))

  const pagedList = computed(() => {
    const start = (page.value - 1) * pageSize
    return source.value.slice(start, start + pageSize)
  })

  function setPage(p: number) {
    page.value = p
  }

  function reset() {
    page.value = 1
  }

  return { page, pageSize, totalPages, pagedList, setPage, reset }
}
