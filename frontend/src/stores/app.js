import { defineStore } from 'pinia'
import { getPlatforms as fetchPlatforms } from '../api/platforms'
import { getStats as fetchStats } from '../api/dashboard'

export const useAppStore = defineStore('app', {
  state: () => ({
    /** 平台配置列表 */
    platforms: [],
    /** 看板统计 */
    stats: {
      total_subscriptions: 0,
      missing_count: 0,
      completed_count: 0,
    },
    /** 加载状态 */
    loading: {
      platforms: false,
      stats: false,
    },
  }),

  actions: {
    /** 加载平台配置 */
    async loadPlatforms() {
      this.loading.platforms = true
      try {
        const { data } = await fetchPlatforms()
        this.platforms = data
      } finally {
        this.loading.platforms = false
      }
    },

    /** 加载看板统计 */
    async loadStats() {
      this.loading.stats = true
      try {
        const { data } = await fetchStats()
        this.stats = data
      } finally {
        this.loading.stats = false
      }
    },
  },
})
