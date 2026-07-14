<script setup>
import { ref, reactive, onMounted } from 'vue'
import { getStats, getPlatformStatus, getActivities, getNextFindQuota } from '@/service/api/dashboard'

defineOptions({ name: 'DashboardView' })

const stats = reactive({
  total_subscriptions: 0,
  missing_count: 0,
  completed_count: 0,
})

const platforms = ref([])
const activities = ref([])
const nfQuota = ref(null)

const loading = reactive({
  platforms: false,
  activities: false,
})

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

function formatTime(ts) {
  if (!ts) return '-'
  const d = new Date(ts)
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function loadStats() {
  try {
    const { data } = await getStats()
    if (data) Object.assign(stats, data)
  } catch {}
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

onMounted(() => {
  loadStats()
  loadPlatformData()
  loadActivities()
})
</script>

<template>
  <div>
    <!-- 统计卡片 -->
    <div class="grid grid-cols-3 gap-4 mb-5">
      <n-card :bordered="true" size="small">
        <div class="flex items-center gap-4">
          <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-[var(--n-color-target)]" style="--n-color-target: rgba(59,130,246,0.15); color: var(--n-color-target-text);">
            <i class="ri-film-line text-xl"></i>
          </div>
          <div>
            <div class="text-3xl font-bold leading-none">{{ stats.total_subscriptions }}</div>
            <div class="text-xs mt-1 opacity-50">总订阅数</div>
          </div>
        </div>
      </n-card>
      <n-card :bordered="true" size="small">
        <div class="flex items-center gap-4">
          <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-amber/15 text-amber">
            <i class="ri-error-warning-line text-xl"></i>
          </div>
          <div>
            <div class="text-3xl font-bold leading-none">{{ stats.missing_count }}</div>
            <div class="text-xs mt-1 opacity-50">缺集数</div>
          </div>
        </div>
      </n-card>
      <n-card :bordered="true" size="small">
        <div class="flex items-center gap-4">
          <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-emerald/15 text-emerald">
            <i class="ri-check-double-line text-xl"></i>
          </div>
          <div>
            <div class="text-3xl font-bold leading-none">{{ stats.completed_count }}</div>
            <div class="text-xs mt-1 opacity-50">已完成数</div>
          </div>
        </div>
      </n-card>
    </div>

    <!-- 平台状态 + 活动日志 -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <n-card title="平台状态" :bordered="true" size="small">
        <template #header-extra>
          <n-button secondary size="tiny" :loading="loading.platforms" @click="loadPlatformData">
            <template #icon><i class="ri-refresh-line"></i></template>
            刷新
          </n-button>
        </template>

        <n-spin :show="loading.platforms">
          <template v-if="platforms.length > 0">
            <div v-for="p in platforms" :key="p.id" class="flex items-center justify-between py-2.5 border-b last:border-b-0 border-[var(--n-border-color)]">
              <div>
                <div class="text-sm font-medium capitalize">{{ p.name === 'nextfind' ? 'NextFind' : 'MoviePilot' }}</div>
                <div class="text-xs opacity-50 font-mono">{{ p.base_url }}</div>
              </div>
              <div class="flex items-center gap-3">
                <span v-if="p.name === 'nextfind' && nfQuota !== null" class="text-xs opacity-60">
                  剩余 <strong class="opacity-100">{{ nfQuota }}</strong>
                </span>
                <n-tag :type="p.enabled ? 'success' : 'error'" size="tiny" round>
                  {{ p.enabled ? '已连接' : '未连接' }}
                </n-tag>
              </div>
            </div>
          </template>
          <n-empty v-else description="暂无平台配置" size="small">
            <template #extra>
              <router-link to="/settings"><n-button size="tiny">去设置</n-button></router-link>
            </template>
          </n-empty>
        </n-spin>
      </n-card>

      <n-card title="最近活动" :bordered="true" size="small">
        <template #header-extra>
          <n-button secondary size="tiny" :loading="loading.activities" @click="loadActivities">
            <template #icon><i class="ri-refresh-line"></i></template>
            刷新
          </n-button>
        </template>

        <n-spin :show="loading.activities">
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
    </div>
  </div>
</template>
