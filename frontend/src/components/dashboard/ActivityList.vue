<script setup>
import { formatTime } from '@/utils/format'

defineProps({
  activities: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

defineEmits(['refresh'])

const iconMap = {
  subscribe: 'ri-rss-fill',
  unsubscribe: 'ri-close-circle-line',
  mp_search: 'ri-search-eye-line',
  mp_downloaded: 'ri-download-2-line',
  sync: 'ri-refresh-line',
  system: 'ri-settings-3-line',
}

const tagTypeMap = {
  subscribe: 'success',
  unsubscribe: 'error',
  mp_search: 'warning',
  mp_downloaded: 'primary',
  sync: 'info',
  system: 'default',
}

const actionLabelMap = {
  subscribe: '订阅',
  unsubscribe: '取消订阅',
  mp_search: 'MP 搜索',
  mp_downloaded: 'MP 下载',
  sync: '同步',
  system: '系统',
}
</script>

<template>
  <n-card title="最近活动" :bordered="true" size="small">
    <template #header-extra>
      <n-button secondary size="tiny" :loading="loading" @click="$emit('refresh')">
        <template #icon><i class="ri-refresh-line"></i></template>
        刷新
      </n-button>
    </template>

    <n-spin :show="loading">
      <template v-if="activities.length > 0">
        <div v-for="a in activities" :key="a.id" class="flex gap-3 py-2.5 border-b last:border-b-0 border-[var(--n-border-color)]">
          <div class="flex items-center justify-center w-8 h-8 rounded-lg shrink-0" style="background: rgba(59,130,246,0.1);">
            <i :class="iconMap[a.action] || 'ri-information-line'" class="text-sm" style="color: rgb(96,165,250);"></i>
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center justify-between gap-2">
              <n-tag :type="tagTypeMap[a.action] || 'default'" size="tiny">{{ actionLabelMap[a.action] || a.action }}</n-tag>
              <span class="text-xs opacity-50 shrink-0">{{ formatTime(a.created_at) }}</span>
            </div>
            <div class="text-xs opacity-60 truncate mt-0.5">{{ a.message }}</div>
          </div>
        </div>
      </template>
      <n-empty v-else description="暂无活动记录" size="small" />
    </n-spin>
  </n-card>
</template>
