import { defineStore } from 'pinia'
import { getPlatforms } from '@/service/api/platforms'
import { getStats } from '@/service/api/dashboard'

/**
 * 应用全局状态
 * - 平台配置列表
 * - 看板统计
 */
export const useAppStore = defineStore('app', () => {
  const platforms = ref([])
  const stats = reactive({
    total_subscriptions: 0,
    missing_count: 0,
    completed_count: 0,
  })
  const loading = reactive({
    platforms: false,
    stats: false,
  })

  async function loadPlatforms() {
    loading.platforms = true
    try {
      const { data } = await getPlatforms()
      platforms.value = data ?? []
    } finally {
      loading.platforms = false
    }
  }

  async function loadStats() {
    loading.stats = true
    try {
      const { data } = await getStats()
      if (data) Object.assign(stats, data)
    } finally {
      loading.stats = false
    }
  }

  return {
    platforms,
    stats,
    loading,
    loadPlatforms,
    loadStats,
  }
})
