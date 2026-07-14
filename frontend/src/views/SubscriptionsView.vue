<script setup>
import { ref, computed, h, onMounted } from 'vue'
import { NTag, NButton, NPopconfirm } from 'naive-ui'
import { getSubscriptions, deleteSubscription, syncSubscriptions } from '@/service/api/subscriptions'
import { triggerTask } from '@/service/api/tasks'
import StatusBadge from '@/components/StatusBadge.vue'

defineOptions({ name: 'SubscriptionsView' })

const list = ref([])
const loading = ref(false)
const syncing = ref(false)
const triggering = ref(false)

const filterType = ref('all')
const filterStatus = ref('all')
const searchText = ref('')

const filteredList = computed(() => {
  let items = list.value
  if (filterType.value && filterType.value !== 'all') {
    items = items.filter((i) => i.media_type === filterType.value)
  }
  if (filterStatus.value && filterStatus.value !== 'all') {
    if (filterStatus.value === 'active') items = items.filter((i) => i.nf_status === 'active')
    else if (filterStatus.value === 'missing') items = items.filter((i) => i.nf_status === 'missing_fill' || i.nf_missing_eps > 0)
    else if (filterStatus.value === 'completed') items = items.filter((i) => i.completed || i.nf_status === 'completed')
  }
  if (searchText.value.trim()) {
    const kw = searchText.value.trim().toLowerCase()
    items = items.filter((i) => i.title?.toLowerCase().includes(kw))
  }
  return items
})

const columns = computed(() => [
  {
    title: '海报', key: 'poster_url', width: 60,
    render(row) {
      if (row.poster_url) return h('img', { src: row.poster_url, class: 'w-10 h-14 rounded object-cover block', onError: (e) => { e.target.style.display = 'none' } })
      return h('div', { class: 'w-10 h-14 rounded flex items-center justify-center', style: 'background: var(--n-border-color);' },
        () => h('i', { class: 'ri-film-line text-lg opacity-30' }))
    },
  },
  {
    title: '标题', key: 'title', ellipsis: { tooltip: true }, width: 200,
    render(row) { return h('span', { class: 'font-medium' }, row.title) },
  },
  {
    title: '类型', key: 'media_type', width: 70,
    render(row) { return h(NTag, { type: row.media_type === 'tv' ? 'primary' : 'success', size: 'tiny', round: true }, { default: () => row.media_type === 'tv' ? '剧集' : '电影' }) },
  },
  {
    title: 'NF 状态', key: 'nf_status', width: 90,
    render(row) { return h(StatusBadge, { status: row.nf_status, type: 'nf' }) },
  },
  {
    title: '缺集', key: 'nf_missing_eps', width: 50, align: 'center',
    render(row) {
      if (row.nf_missing_eps > 0) return h(NTag, { type: 'warning', size: 'tiny', round: true }, { default: () => String(row.nf_missing_eps) })
      return h('span', { class: 'opacity-30' }, '0')
    },
  },
  {
    title: '完成', key: 'completed', width: 50, align: 'center',
    render(row) {
      if (row.completed) return h(NTag, { type: 'success', size: 'tiny', round: true }, { default: () => '✓' })
      return h('span', { class: 'opacity-30' }, '-')
    },
  },
  {
    title: '年份', key: 'year', width: 54,
    render(row) { return h('span', { class: 'opacity-50' }, row.year || '-') },
  },
  {
    title: '操作', key: 'actions', width: 90, align: 'right',
    render(row) {
      return h('div', { class: 'flex gap-1 justify-end' }, [
        h(NButton, { size: 'tiny', quaternary: true, onClick: () => handleRefresh(row) },
          { default: () => h('i', { class: 'ri-refresh-line text-sm' }) }),
        h(NPopconfirm, { onPositiveClick: () => handleDelete(row), positiveText: '确认', negativeText: '取消' }, {
          default: () => '确认取消订阅？',
          trigger: () => h(NButton, { size: 'tiny', quaternary: true, type: 'error' },
            { default: () => h('i', { class: 'ri-delete-bin-6-line text-sm' }) }),
        }),
      ])
    },
  },
])

async function loadList() {
  loading.value = true
  try {
    const { data } = await getSubscriptions()
    list.value = Array.isArray(data) ? data : []
  } finally { loading.value = false }
}

async function handleSync() {
  syncing.value = true
  try {
    const { data } = await syncSubscriptions()
    window.$message?.success(`同步完成，更新了 ${Array.isArray(data) ? data.length : 0} 条订阅记录`)
    await loadList()
  } finally { syncing.value = false }
}

async function handleTriggerMP() {
  triggering.value = true
  try {
    await triggerTask()
    window.$message?.success('已触发 MoviePilot 补充任务')
  } finally { triggering.value = false }
}

async function handleDelete(row) {
  try {
    await deleteSubscription(row.id)
    window.$message?.success(`已取消订阅「${row.title}」`)
    list.value = list.value.filter(i => i.id !== row.id)
  } catch {}
}

function handleRefresh(row) {
  window.$message?.info(`刷新「${row.title}」状态（功能开发中）`)
}

onMounted(async () => {
  await loadList()
  // 页面加载后自动触发双向同步，不阻塞列表显示
  handleSync()
})
</script>

<template>
  <div>
    <n-card :bordered="true" size="small" class="!rounded-2xl mb-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex flex-wrap items-center gap-2">
          <n-select v-model:value="filterType" size="small" style="width: 110px;"
            :options="[
              { label: '全部类型', value: 'all' }, { label: '电影', value: 'movie' }, { label: '剧集', value: 'tv' },
            ]" />
          <n-select v-model:value="filterStatus" size="small" style="width: 110px;"
            :options="[
              { label: '全部状态', value: 'all' }, { label: '活跃', value: 'active' }, { label: '缺集中', value: 'missing' }, { label: '已完成', value: 'completed' },
            ]" />
          <n-input v-model:value="searchText" placeholder="搜索标题..." size="small" clearable style="width: 180px;">
            <template #prefix><i class="ri-search-line opacity-40"></i></template>
          </n-input>
        </div>
        <div class="flex gap-2">
          <n-button size="small" :loading="syncing" @click="handleSync">
            <template #icon><i class="ri-refresh-line"></i></template>
            同步
          </n-button>
          <n-button size="small" :loading="triggering" @click="handleTriggerMP">
            <template #icon><i class="ri-flashlight-line"></i></template>
            MP 补充
          </n-button>
        </div>
      </div>
    </n-card>

    <n-card :bordered="true" size="small">
      <n-spin :show="loading">
        <n-data-table v-if="filteredList.length > 0"
          :columns="columns" :data="filteredList" :bordered="false" :single-line="false" size="small"
          :row-key="(row) => row.id" />
        <n-empty v-else description="暂无订阅" class="py-15" />
      </n-spin>
    </n-card>
  </div>
</template>
