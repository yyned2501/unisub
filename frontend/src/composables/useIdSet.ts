import { ref } from 'vue'

/**
 * 行级 loading 状态集合 — 管理"哪些 ID 正在操作中"。
 * 通过替换 Set 引用触发 Vue 响应式更新。
 *
 * @example
 * const deleting = useIdSet()
 * deleting.add(row.id)
 * try { await deleteRow(row.id) } finally { deleting.remove(row.id) }
 * // 模板中：:loading="deleting.has(row.id)"
 */
export function useIdSet() {
  const ids = ref<Set<number>>(new Set())

  function add(id: number) {
    ids.value = new Set([...ids.value, id])
  }

  function remove(id: number) {
    const next = new Set(ids.value)
    next.delete(id)
    ids.value = next
  }

  function has(id: number): boolean {
    return ids.value.has(id)
  }

  return { ids, add, remove, has }
}
