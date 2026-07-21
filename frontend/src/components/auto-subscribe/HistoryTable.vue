<script setup lang="ts">
import { h } from 'vue'
import { NCard, NButton, NTag, NDataTable, NEmpty, NSpin } from 'naive-ui'
import { formatDateTime } from '@/utils/format'
import type { AutoSubHistoryItem } from '@/types'

defineOptions({ name: 'HistoryTable' })

const props = defineProps<{
  history: AutoSubHistoryItem[]
  loading: boolean
  lastRun: string
  statusLabels: Record<string, string>
}>()

const emit = defineEmits<{
  'clear-history': []
}>()

function rowKey(row: AutoSubHistoryItem): string {
  return row.key
}

const columns = [
  { title: '标题', key: 'key', ellipsis: { tooltip: true }, minWidth: 200 },
  {
    title: '状态',
    key: 'status',
    width: 100,
    render: (row: AutoSubHistoryItem) =>
      h(
        NTag,
        {
          size: 'tiny',
          type: row.status === 'subscribed' ? 'success' : 'default',
          round: true,
        },
        { default: () => props.statusLabels[row.status] || row.status }
      ),
  },
  {
    title: 'TMDB ID',
    key: 'tmdb_id',
    width: 100,
    render: (row: AutoSubHistoryItem) => (row.tmdb_id != null ? String(row.tmdb_id) : '-'),
  },
  {
    title: '类别',
    key: 'media_type',
    width: 80,
    render: (row: AutoSubHistoryItem) => (row.media_type === 'movie' ? '电影' : row.media_type === 'tv' ? '剧集' : '-'),
  },
  { title: '时间', key: 'time', width: 180, render: (row: AutoSubHistoryItem) => formatDateTime(row.time) },
]
</script>

<template>
  <n-card size="small" :bordered="true">
    <template #header>
      <div class="flex items-center justify-between">
        <span class="text-sm font-medium">处理历史</span>
        <div class="flex items-center gap-2">
          <span v-if="lastRun" class="text-xs opacity-40">上次运行: {{ formatDateTime(lastRun) }}</span>
          <n-button size="tiny" quaternary @click="emit('clear-history')">
            <template #icon><i class="ri-delete-bin-line"></i></template>
            清空
          </n-button>
        </div>
      </div>
    </template>
    <n-spin :show="loading">
      <n-data-table
        v-if="history.length > 0"
        :columns="columns"
        :data="history"
        :bordered="false"
        :single-line="false"
        :scroll-x="660"
        size="small"
        :row-key="rowKey"
      />
      <n-empty v-else description="暂无处理记录" class="py-8" size="small" />
    </n-spin>
  </n-card>
</template>
