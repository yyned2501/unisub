import { reactive, ref, onMounted } from 'vue'
import { getStats, getPlatformStatus, getActivities, getNextFindQuota } from '@/service/api/dashboard'
import { getEmbyScanStatus } from '@/service/api/emby'
import { usePolling } from '@/composables/usePolling'
import { msg } from '@/utils/message'
import type { DashboardStats, PlatformStatus, ActivityLog, EmbyScanStatus } from '@/types'

/**
 * 看板页面数据管理
 * - 统计卡片、平台状态、活动列表、扫描进度
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
      const [platformRes, quotaRes] = await Promise.allSettled([getPlatformStatus(), getNextFindQuota()])
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

  onMounted(() => {
    loadStats()
    loadPlatformData()
    loadActivities()
    // 轮询扫描进度（3s）— usePolling 自动在卸载时清理
    usePolling(pollScanStatus, 3000, { immediate: true })
  })

  return {
    stats,
    platforms,
    activities,
    nfQuota,
    loading,
    scanStatus,
    loadStats,
    loadPlatformData,
    loadActivities,
  }
}
