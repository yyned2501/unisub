import { ref, reactive } from 'vue'
import { defineStore } from 'pinia'
import { getPlatforms } from '@/service/api/platforms'
import { getStats } from '@/service/api/dashboard'
import type { PlatformConfig, DashboardStats } from '@/types'

/**
 * 应用全局状态
 * - 平台配置列表
 * - 看板统计
 */
export const useAppStore = defineStore('app', () => {
  const platforms = ref<PlatformConfig[]>([])
  const stats = reactive<DashboardStats>({
    total_subscriptions: 0,
    movie_count: 0,
    tv_count: 0,
    missing_count: 0,
    completed_count: 0,
    tmdb_cached_total: 0,
    tmdb_data_filled: 0,
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