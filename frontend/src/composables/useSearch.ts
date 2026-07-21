import { ref, computed } from 'vue'
import { searchMedia } from '@/service/api/search'
import { createSubscription } from '@/service/api/subscriptions'
import { msg } from '@/utils/message'
import type { SearchResultItem, MediaType } from '@/types'

/**
 * 搜索页面业务逻辑
 * - 搜索媒体、分页、订阅状态管理
 */
export function useSearch() {
  const keyword = ref('')
  const searchType = ref<'all' | MediaType>('all')
  const results = ref<SearchResultItem[]>([])
  const loading = ref(false)
  const searched = ref(false)

  const subscribedIds = ref<Set<number>>(new Set())

  const currentPage = ref(1)
  const pageSize = 20

  const totalPages = computed(() => Math.ceil(results.value.length / pageSize))

  const pagedResults = computed(() => {
    const start = (currentPage.value - 1) * pageSize
    return results.value.slice(start, start + pageSize)
  })

  function isSubscribed(tmdbId: number): boolean {
    return subscribedIds.value.has(tmdbId)
  }

  function clearSearch() {
    keyword.value = ''
    results.value = []
    searched.value = false
    currentPage.value = 1
  }

  async function handleSearch() {
    if (!keyword.value.trim()) {
      msg.warning('请输入搜索关键词')
      return
    }
    loading.value = true
    searched.value = true
    currentPage.value = 1
    try {
      const data = await searchMedia(keyword.value.trim(), searchType.value)
      results.value = Array.isArray(data) ? data : data?.items || []
    } catch {
      results.value = []
    } finally {
      loading.value = false
    }
  }

  async function handleSubscribe(media: SearchResultItem, done: (ok: boolean) => void) {
    try {
      await createSubscription({
        tmdb_id: media.tmdb_id,
        media_type: media.media_type,
        title: media.title,
        poster_url: media.poster_url || '',
        year: media.year || null,
      })
      subscribedIds.value.add(media.tmdb_id)
      msg.success(`已订阅「${media.title}」`)
      done(true)
    } catch {
      done(false)
    }
  }

  return {
    keyword,
    searchType,
    results,
    loading,
    searched,
    subscribedIds,
    currentPage,
    totalPages,
    pagedResults,
    isSubscribed,
    clearSearch,
    handleSearch,
    handleSubscribe,
  }
}
