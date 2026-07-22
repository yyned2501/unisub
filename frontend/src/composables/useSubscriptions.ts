import { ref, computed, onMounted, watch } from 'vue'
import { getSubscriptions, deleteSubscription, syncSubscriptions, toggleBlacklist } from '@/service/api/subscriptions'
import { usePagedList } from '@/composables/usePagedList'
import { msg } from '@/utils/message'
import type { Subscription } from '@/types'

/**
 * 订阅列表业务逻辑
 * - 加载活跃订阅、同步、删除
 */
export function useSubscriptions() {
  const list = ref<Subscription[]>([])
  const loading = ref(false)
  const syncing = ref(false)

  const searchText = ref('')
  const filterTab = ref('active')

  const filteredList = computed(() => {
    let items = list.value
    if (filterTab.value === 'active') {
      items = items.filter((i) => !i.completed && !i.blacklisted)
    } else if (filterTab.value === 'completed') {
      items = items.filter((i) => i.completed && !i.blacklisted)
    } else if (filterTab.value === 'blacklisted') {
      items = items.filter((i) => i.blacklisted)
    } else if (filterTab.value === 'all') {
      items = items.filter((i) => !i.blacklisted)
    }
    if (searchText.value.trim()) {
      const kw = searchText.value.trim().toLowerCase()
      items = items.filter((i) => i.title?.toLowerCase().includes(kw))
    }
    return items
  })

  // 前端分页
  const { page, pageSize, totalPages, pagedList, setPage: handlePageChange, reset: resetPage } = usePagedList(filteredList, 20)

  // 切换 tab / 搜索时重置到第一页
  watch([filterTab, searchText], () => resetPage())

  async function loadList() {
    loading.value = true
    try {
      const data = await getSubscriptions()
      list.value = Array.isArray(data) ? data : []
    } finally {
      loading.value = false
    }
  }

  async function handleSync() {
    syncing.value = true
    try {
      await syncSubscriptions()
      await loadList()
      msg.success(`同步完成，共 ${list.value.length} 条订阅`)
    } finally {
      syncing.value = false
    }
  }

  async function handleDelete(row: Subscription) {
    try {
      await deleteSubscription(row.id)
      msg.success(`已取消订阅「${row.title}」`)
      list.value = list.value.filter((i) => i.id !== row.id)
    } catch {
      msg.error(`取消订阅「${row.title}」失败`)
    }
  }

  async function handleBlacklist(row: Subscription) {
    try {
      const res = await toggleBlacklist(row.id)
      msg.success(res.message)
      // 更新本地状态
      const item = list.value.find((i) => i.id === row.id)
      if (item) item.blacklisted = res.blacklisted
    } catch {
      msg.error('操作失败')
    }
  }

  onMounted(async () => {
    await loadList()
  })

  return {
    list,
    loading,
    syncing,
    searchText,
    filterTab,
    filteredList,
    pagedList,
    page,
    pageSize,
    totalPages,
    loadList,
    handleSync,
    handleDelete,
    handleBlacklist,
    handlePageChange,
  }
}
