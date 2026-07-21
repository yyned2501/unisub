<script setup lang="ts">
import { computed, h } from 'vue'
import { NTag, NButton, NPopconfirm } from 'naive-ui'
import { useSubscriptions } from '@/composables/useSubscriptions'
import { onImgError } from '@/utils/format'
import type { Subscription } from '@/types'
import type { DataTableColumns } from 'naive-ui'

defineOptions({ name: 'SubscriptionsView' })

function subStatus(row: Subscription) {
  if (!row.nf_subscribed) return { label: '未同步', type: 'warning' as const }
  return { label: '订阅中', type: 'primary' as const }
}

function embyStatus(row: Subscription) {
  if (row.completed) return { label: '已完成', type: 'success' as const }
  if (row.aired_complete) return { label: '已入库', type: 'primary' as const }
  if (row.media_type === 'tv' && row.nf_missing_eps > 0)
    return { label: `缺 ${row.nf_missing_eps} 集`, type: 'info' as const }
  if (row.nf_subscribed && row.nf_missing_eps === 0)
    return { label: '已入库', type: 'primary' as const }
  return { label: '未入库', type: 'default' as const }
}

const {
  loading,
  syncing,
  searchText,
  filterTab,
  pagedList,
  page,
  pageSize,
  totalPages,
  handleSync,
  handleDelete,
  handlePageChange,
} = useSubscriptions()

const columns = computed<DataTableColumns<Subscription>>(() => [
  {
    title: '海报',
    key: 'poster_url',
    width: 60,
    render(row) {
      if (row.poster_url)
        return h('img', { src: row.poster_url, class: 'w-10 h-14 rounded object-cover block', onError: onImgError })
      return h(
        'div',
        { class: 'w-10 h-14 rounded flex items-center justify-center', style: 'background: var(--n-border-color);' },
        () => h('i', { class: 'ri-film-line text-lg opacity-30' })
      )
    },
  },
  {
    title: '标题',
    key: 'title',
    ellipsis: { tooltip: true },
    minWidth: 200,
    render(row) {
      return h('span', { class: 'font-medium' }, row.title)
    },
  },
  {
    title: '类型',
    key: 'media_type',
    width: 70,
    render(row) {
      return h(
        NTag,
        { type: row.media_type === 'tv' ? 'primary' : 'success', size: 'tiny', round: true },
        { default: () => (row.media_type === 'tv' ? '剧集' : '电影') }
      )
    },
  },
  {
    title: '年份',
    key: 'year',
    width: 54,
    render(row) {
      return h('span', { class: 'opacity-50' }, row.year || '-')
    },
  },
  {
    title: 'TMDB',
    key: 'tmdb_id',
    width: 90,
    render(row) {
      if (!row.tmdb_id) return h('span', { class: 'opacity-30' }, '-')
      return h(
        'a',
        {
          href: `https://www.themoviedb.org/${row.media_type || 'movie'}/${row.tmdb_id}`,
          target: '_blank',
          class: 'text-primary hover:underline cursor-pointer',
        },
        row.tmdb_id
      )
    },
  },
  {
    title: '订阅状态',
    key: 'sub_status',
    width: 80,
    render(row) {
      const s = subStatus(row)
      return h(NTag, { type: s.type, size: 'tiny', round: true }, { default: () => s.label })
    },
  },
  {
    title: 'Emby 状态',
    key: 'emby_status',
    width: 90,
    render(row) {
      const s = embyStatus(row)
      return h(NTag, { type: s.type, size: 'tiny', round: true }, { default: () => s.label })
    },
  },
  {
    title: '来源',
    key: 'source',
    width: 80,
    render(row) {
      if (!row.source) return '-'
      const labels: Record<string, string> = {
        manual: '手动',
        forward: 'Forward',
        auto_subscribe: '自动订阅',
        nextfind: 'NF同步',
      }
      return h('span', { class: 'text-xs opacity-50' }, labels[row.source] || row.source)
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 60,
    align: 'right',
    render(row) {
      return h(
        NPopconfirm,
        { onPositiveClick: () => handleDelete(row), positiveText: '确认', negativeText: '取消' },
        {
          default: () => '确认取消订阅？',
          trigger: () =>
            h(
              NButton,
              { size: 'tiny', quaternary: true, type: 'error' },
              { default: () => h('i', { class: 'ri-delete-bin-6-line text-sm' }) }
            ),
        }
      )
    },
  },
])
</script>

<template>
  <div>
    <n-card :bordered="true" size="small" class="!rounded-2xl mb-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex flex-wrap items-center gap-3">
          <n-radio-group v-model:value="filterTab" size="small">
            <n-radio-button value="active">订阅中</n-radio-button>
            <n-radio-button value="completed">已完成</n-radio-button>
            <n-radio-button value="unsynced">未同步</n-radio-button>
            <n-radio-button value="all">全部</n-radio-button>
          </n-radio-group>
          <n-input v-model:value="searchText" placeholder="搜索标题..." size="small" clearable style="width: 200px">
            <template #prefix><i class="ri-search-line opacity-40"></i></template>
          </n-input>
        </div>
        <div class="flex gap-2">
          <n-button size="small" :loading="syncing" @click="handleSync">
            <template #icon><i class="ri-refresh-line"></i></template>
            同步
          </n-button>
        </div>
      </div>
    </n-card>

    <n-card :bordered="true" size="small">
      <n-spin :show="loading">
        <n-data-table
          v-if="pagedList.length > 0"
          :columns="columns"
          :data="pagedList"
          :bordered="false"
          :single-line="false"
          size="small"
          :row-key="(row) => row.id"
        />
        <n-empty v-else description="暂无活跃订阅" class="py-15" />
      </n-spin>
    </n-card>

    <div v-if="totalPages > 1" class="flex justify-center mt-4">
      <n-pagination :page="page" :page-count="totalPages" :page-size="pageSize" @update:page="handlePageChange" />
    </div>
  </div>
</template>
