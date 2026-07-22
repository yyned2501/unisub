<script setup lang="ts">
import { computed, h } from 'vue'
import { NTag, NButton, NPopconfirm } from 'naive-ui'
import { useSubscriptions } from '@/composables/useSubscriptions'
import { onImgError } from '@/utils/format'
import type { Subscription } from '@/types'
import type { DataTableColumns } from 'naive-ui'

defineOptions({ name: 'SubscriptionsView' })

/** 状态栏：显示入库/已播/全集 和完成标记 */
function statusCell(row: Subscription) {
  // 电影：0/1 或 1/1
  if (row.media_type === 'movie') {
    const label = row.completed ? '1/1' : '0/1'
    const type = row.completed ? 'success' as const : 'default' as const
    return h(NTag, { type, size: 'tiny', round: true }, { default: () => label })
  }
  // 剧集：emby入库 / 已播出 / 总集数
  const parts: string[] = []
  parts.push(row.emby_episode_count != null ? String(row.emby_episode_count) : '-')
  parts.push(row.tmdb_aired_eps != null ? String(row.tmdb_aired_eps) : '-')
  parts.push(row.tmdb_total_eps != null ? String(row.tmdb_total_eps) : '-')
  const label = parts.join('/')
  let type: 'success' | 'primary' | 'default' = 'default'
  if (row.completed) type = 'success'
  else if (row.aired_complete) type = 'primary'
  return h(NTag, { type, size: 'tiny', round: true }, { default: () => label })
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
    className: 'hidden sm:table-cell',
    titleClassName: 'hidden sm:table-cell',
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
    className: 'hidden sm:table-cell',
    titleClassName: 'hidden sm:table-cell',
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
    className: 'hidden sm:table-cell',
    titleClassName: 'hidden sm:table-cell',
    render(row) {
      return h('span', { class: 'opacity-50' }, row.year || '-')
    },
  },
  {
    title: 'TMDB',
    key: 'tmdb_id',
    width: 90,
    className: 'hidden sm:table-cell',
    titleClassName: 'hidden sm:table-cell',
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
    title: '状态',
    key: 'status',
    width: 120,
    render(row) {
      return statusCell(row)
    },
  },
  {
    title: '来源',
    key: 'source',
    width: 80,
    className: 'hidden sm:table-cell',
    titleClassName: 'hidden sm:table-cell',
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
          <n-input v-model:value="searchText" placeholder="搜索标题..." size="small" clearable class="w-full sm:w-50">
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
          :scroll-x="900"
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
