import { ref, computed, onMounted } from 'vue'
import { getSubscriptions, deleteSubscription, syncSubscriptions } from '@/service/api/subscriptions'

/**
 * 订阅列表业务逻辑
 * - 加载活跃订阅、同步、删除
 */
export function useSubscriptions() {
  const list = ref([])
  const loading = ref(false)
  const syncing = ref(false)

  const searchText = ref('')
  const filterTab = ref('active')

  // 前端分页
  const page = ref(1)
  const pageSize = ref(20)

  const filteredList = computed(() => {
    let items = list.value
    if (filterTab.value === 'active') {
      items = items.filter((i) => !i.completed)
    } else if (filterTab.value === 'completed') {
      items = items.filter((i) => i.completed)
    } else if (filterTab.value === 'unsynced') {
      items = items.filter((i) => !i.completed && !i.nf_subscribed)
    }
    if (searchText.value.trim()) {
      const kw = searchText.value.trim().toLowerCase()
      items = items.filter((i) => i.title?.toLowerCase().includes(kw))
    }
    return items
  })

  const totalPages = computed(() => Math.max(1, Math.ceil(filteredList.value.length / pageSize.value)))

  const pagedList = computed(() => {
    const start = (page.value - 1) * pageSize.value
    return filteredList.value.slice(start, start + pageSize.value)
  })

  async function loadList() {
    loading.value = true
    try {
      const { data } = await getSubscriptions()
      list.value = Array.isArray(data) ? data : []
    } finally { loading.value = false }
  }

  function handlePageChange(p) {
    page.value = p
  }

  async function handleSync() {
    syncing.value = true
    try {
      const { data } = await syncSubscriptions()
      await loadList()
      window.$message?.success(`同步完成，共 ${list.value.length} 条订阅`)
      await loadList()
    } finally { syncing.value = false }
  }

  async function handleDelete(row) {
    try {
      await deleteSubscription(row.id)
      window.$message?.success(`已取消订阅「${row.title}」`)
      list.value = list.value.filter(i => i.id !== row.id)
    } catch {
      window.$message?.error(`取消订阅「${row.title}」失败`)
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
    handlePageChange,
  }
}