<script setup lang="ts">
import { useDashboard } from '@/composables/useDashboard'
import StatsCards from '@/components/dashboard/StatsCards.vue'
import ScanProgress from '@/components/dashboard/ScanProgress.vue'
import PlatformPanel from '@/components/dashboard/PlatformPanel.vue'
import ActivityList from '@/components/dashboard/ActivityList.vue'

defineOptions({ name: 'DashboardView' })

const { stats, platforms, activities, nfQuota, loading, scanStatus, loadPlatformData, loadActivities } =
  useDashboard()
</script>

<template>
  <div>
    <StatsCards
      :total-subscriptions="stats.total_subscriptions"
      :missing-count="stats.missing_count"
      :completed-count="stats.completed_count"
      :tmdb-cached-total="stats.tmdb_cached_total"
      :tmdb-data-filled="stats.tmdb_data_filled"
    />

    <ScanProgress :scan-status="scanStatus" />

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <PlatformPanel
        :platforms="platforms"
        :nf-quota="nfQuota"
        :loading="loading.platforms"
        @refresh="loadPlatformData"
      />
    </div>

    <div class="grid grid-cols-1 gap-4 mt-4">
      <ActivityList :activities="activities" :loading="loading.activities" @refresh="loadActivities" />
    </div>
  </div>
</template>
