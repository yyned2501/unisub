import { reactive, ref, onMounted, onUnmounted } from 'vue'
import { getStats, getPlatformStatus, getActivities, getNextFindQuota } from '@/service/api/dashboard'
import { getTaskStatus } from '@/service/api/tasks'
import { getEmbyScanStatus } from '@/service/api/emby'

/**
 * 看板页面数据管理
 * - 统计卡片、平台状态、活动列表、扫描进度、自动补缺状态
 */
export function useDashboard() {
  const stats = reactive({
    total_subscriptions: 0,
    missing_count: 0,
    completed_count: 0,
    tmdb_cached_total: 0,
    tmdb_data_filled: 0,
  })

  const platforms = ref([])
  const activities = ref([])
  const nfQuota = ref(null)
  const loading = reactive({ platforms: false, activities: false })

  // 扫描进度
  const scanStatus = ref(null)
  let scanPollTimer = null

  // 自动补缺状态
  const autoFillStatus = reactive({
    enabled: false,
    lastRun: null,
    cursor: null,
    progress: null,
  })
  let autoFillPollTimer = null

  async function loadStats() {
    try {
      const { data } = await getStats()
      if (data) Object.assign(stats, data)
    } catch {
      window.$message?.error('加载仪表盘数据失败')
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
        platforms.value = platformRes.value.data ?? []
      }
      if (quotaRes.status === 'fulfilled') {
        nfQuota.value = quotaRes.value.data?.remaining ?? quotaRes.value.data?.quota ?? null
      }
    } finally {
      loading.platforms = false
    }
  }

  async function loadActivities() {
    loading.activities = true
    try {
      const { data } = await getActivities()
      activities.value = data ?? []
    } finally {
      loading.activities = false
    }
  }

  async function pollScanStatus() {
    try {
      const { data } = await getEmbyScanStatus()
      scanStatus.value = data
    } catch {
      // 轮询类偶发失败不打扰用户，静默重置状态即可
      scanStatus.value = null
    }
  }

  function startScanPolling() {
    stopScanPolling()
    scanPollTimer = setInterval(pollScanStatus, 3000)
  }

  function stopScanPolling() {
    if (scanPollTimer) {
      clearInterval(scanPollTimer)
      scanPollTimer = null
    }
  }

  async function loadAutoFillStatus() {
    try {
      const { data } = await getTaskStatus()
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

  function startAutoFillPolling() {
    stopAutoFillPolling()
    autoFillPollTimer = setInterval(loadAutoFillStatus, 5000)
  }

  function stopAutoFillPolling() {
    if (autoFillPollTimer) {
      clearInterval(autoFillPollTimer)
      autoFillPollTimer = null
    }
  }

  onMounted(() => {
    loadStats()
    loadPlatformData()
    loadActivities()
    loadAutoFillStatus()
    startAutoFillPolling()
    pollScanStatus()
    startScanPolling()
  })

  onUnmounted(() => {
    stopScanPolling()
    stopAutoFillPolling()
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