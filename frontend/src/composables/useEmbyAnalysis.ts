import { ref, computed, onMounted } from 'vue'
import {
  getEmbyLibraryAnalysis,
  syncEmbyCache,
  backfillOverview,
  triggerEmbyScan,
  getEmbyScanStatus,
  addToBlacklist,
  removeFromBlacklist,
  subscribeFromEmby,
  deleteEmbyItem,
} from '@/service/api/emby'
import { useIdSet } from '@/composables/useIdSet'
import { usePolling } from '@/composables/usePolling'
import { msg, confirmDialog } from '@/utils/message'
import type { AxiosError } from 'axios'
import type { EmbyMissingAnalysis, EmbyCacheResponse } from '@/types'

/**
 * Emby 缺集分析页业务逻辑
 * - 缺集列表加载/分页/筛选、缓存同步、全量扫描轮询、黑名单、订阅
 */
export function useEmbyAnalysis() {
  const loading = ref(false)
  const syncing = ref(false)
  const backfilling = ref(false)
  const analysis = ref<EmbyMissingAnalysis | null>(null)
  const searchText = ref('')
  const showHidden = ref(false)
  const hidingIds = useIdSet()
  const subscribingIds = useIdSet()
  const deletingIds = useIdSet()

  // 分页
  const page = ref(1)
  const pageSize = ref(50)
  const libraryFilter = ref('')

  // 扫描进度
  const scanRunning = ref(false)
  const scanProgress = ref(0)
  const scanStepName = ref('')
  const scanItem = ref('')

  const libraries = computed(() => analysis.value?.libraries || [])

  const filteredSeries = computed(() => {
    if (!analysis.value) return []
    let items = analysis.value.series || []
    if (searchText.value.trim()) {
      const kw = searchText.value.trim().toLowerCase()
      items = items.filter((s) => (s.emby_series_name || '').toLowerCase().includes(kw))
    }
    if (!showHidden.value) {
      items = items.filter((s) => !s.is_blacklisted)
    }
    return items
  })

  async function load() {
    loading.value = true
    try {
      const params: { page: number; page_size: number; library?: string } = {
        page: page.value,
        page_size: pageSize.value,
      }
      if (libraryFilter.value) {
        params.library = libraryFilter.value
      }
      analysis.value = await getEmbyLibraryAnalysis(params)
    } catch {
      analysis.value = null
    } finally {
      loading.value = false
    }
  }

  function handlePageChange(p: number) {
    page.value = p
    load()
  }

  function handleLibraryChange(val: string | null) {
    libraryFilter.value = val || ''
    page.value = 1
    load()
  }

  async function handleSync() {
    syncing.value = true
    try {
      await syncEmbyCache()
      msg.success('Emby 缓存同步完成')
      await load()
    } catch {
      msg.error('同步失败')
    } finally {
      syncing.value = false
    }
  }

  async function handleBackfillOverview() {
    backfilling.value = true
    try {
      const data = await backfillOverview()
      msg.success(data?.message || '描述补充完成')
      await load()
    } catch {
      msg.error('补充描述失败')
    } finally {
      backfilling.value = false
    }
  }

  // 扫描进度轮询 — 默认不启动，handleFullScan 时 resume；完成/出错时 pause
  const scanPolling = usePolling(async () => {
    try {
      const data = await getEmbyScanStatus()
      if (data) {
        scanRunning.value = data.running
        scanProgress.value = data.progress || 0
        scanStepName.value = data.step_name || ''
        scanItem.value = String(data.current_item || '')
        if (data.error) {
          msg.error(`扫描出错: ${data.error}`)
          scanPolling.pause()
        }
        if (!data.running && scanProgress.value >= 100) {
          scanPolling.pause()
          msg.success('全量扫描完成')
          await load()
        }
        if (!data.running && data.error) {
          scanPolling.pause()
          await load()
        }
      }
    } catch {
      scanPolling.pause()
    }
  }, 1500)

  async function handleFullScan() {
    try {
      await triggerEmbyScan()
      scanRunning.value = true
      scanProgress.value = 0
      scanStepName.value = '正在启动扫描...'
      scanPolling.resume()
      msg.success('全量扫描已启动')
    } catch (e: unknown) {
      msg.error((e as AxiosError<{ detail?: string }>)?.response?.data?.detail || '启动扫描失败')
    }
  }

  async function handleHide(tmdbId: number) {
    hidingIds.add(tmdbId)
    try {
      await addToBlacklist(tmdbId)
      const s = analysis.value?.series.find((item) => item.tmdb_id === tmdbId)
      if (s) s.is_blacklisted = true
      msg.success('已隐藏')
    } catch {
      msg.error('隐藏失败')
    } finally {
      hidingIds.remove(tmdbId)
    }
  }

  async function handleUnhide(tmdbId: number) {
    hidingIds.add(tmdbId)
    try {
      await removeFromBlacklist(tmdbId)
      const s = analysis.value?.series.find((item) => item.tmdb_id === tmdbId)
      if (s) s.is_blacklisted = false
      msg.success('已取消隐藏')
    } catch {
      msg.error('取消隐藏失败')
    } finally {
      hidingIds.remove(tmdbId)
    }
  }

  async function handleSubscribe(s: EmbyCacheResponse) {
    subscribingIds.add(s.tmdb_id)
    try {
      const data = await subscribeFromEmby(s.tmdb_id, s.emby_series_name || '未知', 'tv', s.poster_url, s.emby_year)
      if (data?.success) {
        const item = analysis.value?.series.find((x) => x.tmdb_id === s.tmdb_id)
        if (item) item.is_subscribed = true
        msg.success(data.message || '订阅成功')
      } else {
        msg.error(data?.message || '订阅失败')
      }
    } catch (e: unknown) {
      msg.error((e as AxiosError<{ detail?: string }>)?.response?.data?.detail || '订阅失败')
    } finally {
      subscribingIds.remove(s.tmdb_id)
    }
  }

  async function handleDelete(s: EmbyCacheResponse) {
    try {
      await confirmDialog({
        title: '从 Emby 删除',
        content: `确定要从 Emby 删除「${s.emby_series_name || '未知'}」吗？此操作不可逆，将同时删除媒体文件。`,
        positiveText: '删除',
      })
    } catch {
      return // 用户取消
    }
    deletingIds.add(s.tmdb_id)
    try {
      const data = await deleteEmbyItem(s.tmdb_id)
      if (data?.success) {
        if (analysis.value) {
          analysis.value.series = analysis.value.series.filter((x) => x.tmdb_id !== s.tmdb_id)
        }
        msg.success(data.message || '已从 Emby 删除')
      } else {
        msg.error(data?.message || '删除失败')
      }
    } catch (e: unknown) {
      msg.error((e as AxiosError<{ detail?: string }>)?.response?.data?.detail || '删除失败')
    } finally {
      deletingIds.remove(s.tmdb_id)
    }
  }

  onMounted(() => load())

  return {
    loading,
    syncing,
    backfilling,
    analysis,
    searchText,
    showHidden,
    libraryFilter,
    hidingIds,
    subscribingIds,
    deletingIds,
    libraries,
    filteredSeries,
    scanRunning,
    scanProgress,
    scanStepName,
    scanItem,
    load,
    handlePageChange,
    handleLibraryChange,
    handleSync,
    handleBackfillOverview,
    handleFullScan,
    handleHide,
    handleUnhide,
    handleSubscribe,
    handleDelete,
  }
}
