import { reactive, ref, onMounted } from 'vue'
import { getStats, getPlatformStatus, getActivities, getNextFindQuota } from '@/service/api/dashboard'
import { getTaskStatus } from '@/service/api/tasks'
import { getEmbyScanStatus } from '@/service/api/emby'
import { usePolling } from '@/composables/usePolling'
import { msg } from '@/utils/message'
import type { DashboardStats, PlatformStatus, ActivityLog, EmbyScanStatus, AutoFillProgress } from '@/types'

/**
 * 看板页面数据管理
 * - 统计卡片、平台状态、活动列表、扫描进度、自动补缺状态
 */
export function useDashboard() {
  const stats = reactive<DashboardStats>({
    total_subscriptions: 0,
    movie_count: 0,
    tv_count: 0,
    missing_count: 0,
    completed_count: 0,
    tmdb_cached_total: 0,
    tmdb_data_filled: 0,
  })

  const platforms = ref<PlatformStatus[]>([])
  const activities = ref<ActivityLog[]>([])
  const nfQuota = ref<number | null>(null)
  const loading = reactive({ platforms: false, activities: false })

  // 扫描进度
  const scanStatus = ref<EmbyScanStatus | null>(null)

  // 自动补缺状态
  const autoFillStatus = reactive<{
    enabled: boolean
    lastRun: string | null
    cursor: number | null
    progress: AutoFillProgress | null
  }>({
    enabled: false,
    lastRun: null,
    cursor: null,
    progress: null,
  })

  async function loadStats() {
    try {
      const data = await getStats()
      if (data) Object.assign(stats, data)
    } catch {
      msg.error('加载仪表盘数据失败')
    }
  }

  async function loadPlatformData() {
    loading.platforms = true
    try {
      const [platformRes, quotaRes] = await Promise.allSettled([
        getPlatformStatus(),
        getNextFindQuota(),
      ])
      if (platformRes.status === 'fulfilled') {
        platforms.value = platformRes.value ?? []
      }
      if (quotaRes.status === 'fulfilled') {
        nfQuota.value = (quotaRes.value?.remaining ?? quotaRes.value?.quota ?? null) as number | null
      }
    } finally {
      loading.platforms = false
    }
  }

  async function loadActivities() {
    loading.activities = true
    try {
      const data = await getActivities()
      activities.value = data ?? []
    } finally {
      loading.activities = false
    }
  }

  async function pollScanStatus() {
    try {
      scanStatus.value = await getEmbyScanStatus()
    } catch {
      // 轮询类偶发失败不打扰用户，静默重置状态即可
      scanStatus.value = null
    }
  }

  async function loadAutoFillStatus() {
    try {
      const data = await getTaskStatus()
      if (data) {
        autoFillStatus.enabled = data.config?.auto_fill_enabled ?? false
        autoFillStatus.lastRun = data.auto_fill_last_run ?? null
        autoFillStatus.cursor = data.auto_fill_cursor ?? null
        autoFillStatus.progress = data.auto_fill_progress ?? null
      }
    } catch {
      // 轮询类偶发失败不打扰用户，静默保留上次状态
    }
  }

  onMounted(() => {
    loadStats()
    loadPlatformData()
    loadActivities()
    loadAutoFillStatus()
    // 轮询：自动补缺状态（5s）、扫描进度（3s）— usePolling 自动在卸载时清理
    usePolling(loadAutoFillStatus, 5000)
    usePolling(pollScanStatus, 3000, { immediate: true })
  })

  return {
    stats,
    platforms,
    activities,
    nfQuota,
    loading,
    scanStatus,
    autoFillStatus,
    loadStats,
    loadPlatformData,
    loadActivities,
  }
}
