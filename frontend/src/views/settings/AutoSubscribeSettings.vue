<script setup>
import { ref, reactive, onMounted, h } from 'vue'
import { NTag, NButton } from 'naive-ui'
import { formatDateTime } from '@/utils/format'
import {
  getAutoSubConfig,
  updateAutoSubConfig,
  triggerAutoSubRun,
  getAutoSubHistory,
  clearAutoSubHistory,
  getAutoSubMeta,
} from '@/service/api/autoSubscribe'

defineOptions({ name: 'AutoSubscribeSettings' })

const DEFAULT_CONFIG = {
  enabled: false,
  min_year: 0,
  min_vote: 0,
  media_type: 'all',
  schedule_cron: '0 8 * * *',
  douban_enabled: false,
  douban_ranks: ['movie-hot-gaia', 'tv-hot'],
  douban_rsshub: 'https://rsshub.app',
  douban_rss_custom: '',
  mikan_enabled: false,
  mikan_season: '当前',
  mikan_year: 0,
  mikan_resolve_detail: true,
  maoyan_enabled: false,
  maoyan_movie_box: true,
  maoyan_web_platforms: [],
  maoyan_web_types: [],
  maoyan_num: 10,
  proxy_url: '',
}

const DEFAULT_META = {
  douban_ranks: [
    { value: 'movie-ustop', label: '北美票房榜' },
    { value: 'movie-weekly', label: '一周口碑榜' },
    { value: 'movie-top250', label: 'Top250' },
    { value: 'movie-hot-gaia', label: '热门电影' },
    { value: 'tv-hot', label: '热门剧集' },
    { value: 'tv-variety-show', label: '综艺' },
    { value: 'movie-real-time', label: '实时热门电影' },
  ],
  maoyan_platforms: [
    { value: '腾讯视频', label: '腾讯视频' },
    { value: '爱奇艺', label: '爱奇艺' },
    { value: '优酷', label: '优酷' },
    { value: '芒果TV', label: '芒果TV' },
    { value: '哔哩哔哩', label: '哔哩哔哩' },
    { value: '抖音', label: '抖音' },
    { value: '快手', label: '快手' },
    { value: '西瓜视频', label: '西瓜视频' },
  ],
  maoyan_media_types: [
    { value: 'tv', label: '电视剧' },
    { value: 'movie', label: '电影' },
    { value: '动漫', label: '动漫' },
  ],
  seasons: [
    { value: '当前', label: '当前季' },
    { value: '春', label: '春季' },
    { value: '夏', label: '夏季' },
    { value: '秋', label: '秋季' },
    { value: '冬', label: '冬季' },
  ],
}

const loading = ref(false)
const saving = ref(false)
const running = ref(false)
const config = reactive({ ...DEFAULT_CONFIG })
const meta = ref(DEFAULT_META)
const history = ref([])
const lastRun = ref('')
const lastStats = ref(null)
const statusLabels = ref({})
const sourceNames = ref({})
const scheduleRunning = ref(false)
const scheduleError = ref('')
const activeTab = ref('config')

function toggleArray(arr, val) {
  if (!Array.isArray(arr)) return
  const idx = arr.indexOf(val)
  if (idx >= 0) arr.splice(idx, 1)
  else arr.push(val)
}

async function load() {
  loading.value = true
  try {
    const [cfgRes, metaRes, histRes] = await Promise.all([
      getAutoSubConfig(),
      getAutoSubMeta(),
      getAutoSubHistory(),
    ])
    Object.assign(config, DEFAULT_CONFIG, cfgRes.data.config || {})
    for (const key of [
      'douban_ranks',
      'maoyan_web_platforms',
      'maoyan_web_types',
    ]) {
      if (!Array.isArray(config[key])) config[key] = [...DEFAULT_CONFIG[key]]
    }
    statusLabels.value = cfgRes.data.status_labels || {}
    sourceNames.value = cfgRes.data.source_names || {}
    lastRun.value = cfgRes.data.last_run
    lastStats.value = cfgRes.data.last_stats
    scheduleRunning.value = Boolean(cfgRes.data.running)
    scheduleError.value = cfgRes.data.last_error || ''
    const remoteMeta = metaRes.data || {}
    meta.value = {
      ...DEFAULT_META,
      ...remoteMeta,
      douban_ranks: remoteMeta.douban_ranks?.length ? remoteMeta.douban_ranks : DEFAULT_META.douban_ranks,
      maoyan_platforms: remoteMeta.maoyan_platforms?.length ? remoteMeta.maoyan_platforms : DEFAULT_META.maoyan_platforms,
      maoyan_media_types: remoteMeta.maoyan_media_types?.length ? remoteMeta.maoyan_media_types : DEFAULT_META.maoyan_media_types,
      seasons: remoteMeta.seasons?.length ? remoteMeta.seasons : DEFAULT_META.seasons,
    }
    history.value = histRes.data.items || []
  } catch (error) {
    window.$message?.error(error.response?.data?.detail || '自动订阅配置加载失败')
  }
  finally { loading.value = false }
}

async function handleSave() {
  saving.value = true
  try {
    await updateAutoSubConfig({ config: { ...config } })
    window.$message?.success('配置已保存')
  } catch (error) { window.$message?.error(error.response?.data?.detail || '保存失败') }
  finally { saving.value = false }
}

async function handleRun() {
  running.value = true
  try {
    const { data } = await triggerAutoSubRun()
    window.$message?.success(data.message || '自动订阅已启动')
    await load()
  } catch (e) { window.$message?.error(e.response?.data?.detail || '启动失败') }
  finally { running.value = false }
}

async function handleClearHistory() {
  try {
    await clearAutoSubHistory()
    history.value = []
    window.$message?.success('历史已清空')
  } catch { window.$message?.error('清空失败') }
}

onMounted(() => load())
</script>

<template>
  <div>
    <h2 class="text-lg font-bold mb-4">自动订阅</h2>

    <n-tabs v-model:value="activeTab" type="line" animated>
      <n-tab-pane name="config" tab="配置">
        <n-spin :show="loading">
          <!-- 全局设置 -->
          <n-card title="全局设置" size="small" :bordered="true" class="mb-4">
            <div class="flex flex-col gap-4">
              <div class="flex items-center justify-between">
                <label class="text-xs opacity-50 font-medium">启用自动订阅</label>
                <n-switch v-model:value="config.enabled" />
              </div>

              <div class="flex flex-wrap items-center gap-2">
                <span class="text-xs opacity-50">最小年份</span>
                <n-input-number v-model:value="config.min_year" :min="0" :max="2100" size="small" style="width: 110px;" />
                <span class="text-xs opacity-50">最小评分</span>
                <n-input-number v-model:value="config.min_vote" :min="0" :max="10" :step="0.5" size="small" style="width: 110px;" />
                <span class="text-xs opacity-50">类型</span>
                <n-select v-model:value="config.media_type" :options="[
                  { value: 'all', label: '全部' },
                  { value: 'movie', label: '电影' },
                  { value: 'tv', label: '剧集' },
                ]" size="small" style="width: 100px;" />
              </div>

              <div class="flex flex-col gap-1.5">
                <label class="text-xs opacity-50 font-medium">定时表达式 (Cron)</label>
                <n-input v-model:value="config.schedule_cron" placeholder="0 8 * * *" size="small" style="max-width: 200px;" />
                <span v-if="scheduleRunning" class="text-xs text-warning">自动订阅正在运行</span>
                <span v-else-if="scheduleError" class="text-xs text-error">上次运行异常: {{ scheduleError }}</span>
              </div>
              <div class="flex flex-col gap-1.5">
                <label class="text-xs opacity-50 font-medium">代理地址（可选，如 http://192.168.31.10:7890）</label>
                <n-input v-model:value="config.proxy_url" placeholder="http://192.168.31.10:7890" size="small" style="max-width: 300px;" />
              </div>
            </div>
          </n-card>

          <!-- 豆瓣 -->
          <n-card title="豆瓣榜单" size="small" :bordered="true" class="mb-4">
            <div class="flex flex-col gap-4">
              <div class="flex items-center justify-between">
                <label class="text-xs opacity-50 font-medium">启用</label>
                <n-switch v-model:value="config.douban_enabled" />
              </div>
              <div v-if="config.douban_enabled" class="flex flex-col gap-4">
                <div class="flex flex-col gap-1.5">
                  <label class="text-xs opacity-50 font-medium">榜单类型</label>
                  <div class="flex flex-wrap gap-2">
                    <label v-for="r in (meta?.douban_ranks || [])" :key="r.value"
                      class="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded cursor-pointer"
                      :class="config.douban_ranks?.includes(r.value) ? 'bg-blue-500 text-white' : 'bg-gray-100 dark:bg-gray-800'"
                      @click="toggleArray(config.douban_ranks, r.value)">
                      {{ r.label }}
                    </label>
                  </div>
                </div>
                <div class="flex flex-col gap-1.5">
                  <label class="text-xs opacity-50 font-medium">RSSHub 地址</label>
                  <n-input v-model:value="config.douban_rsshub" placeholder="https://rsshub.app" size="small" style="max-width: 300px;" />
                </div>
                <div class="flex flex-col gap-1.5">
                  <label class="text-xs opacity-50 font-medium">自定义 RSS（可选，每行一个）</label>
                  <n-input v-model:value="config.douban_rss_custom" type="textarea" :rows="2" placeholder="可选" size="small" style="max-width: 400px;" />
                </div>
              </div>
            </div>
          </n-card>

          <!-- Mikan -->
          <n-card title="Mikan 新番" size="small" :bordered="true" class="mb-4">
            <div class="flex flex-col gap-4">
              <div class="flex items-center justify-between">
                <label class="text-xs opacity-50 font-medium">启用</label>
                <n-switch v-model:value="config.mikan_enabled" />
              </div>
              <div v-if="config.mikan_enabled" class="flex flex-col gap-4">
                <div class="flex flex-wrap items-center gap-3">
                  <div class="flex items-center gap-1.5">
                    <span class="text-xs opacity-50">季度</span>
                    <n-select v-model:value="config.mikan_season" :options="meta?.seasons || []" size="small" style="width: 110px;" />
                  </div>
                  <div class="flex items-center gap-1.5">
                    <span class="text-xs opacity-50">年份（0=自动）</span>
                    <n-input-number v-model:value="config.mikan_year" :min="0" :max="2100" size="small" style="width: 110px;" />
                  </div>
                  <div class="flex items-center gap-2">
                    <n-switch v-model:value="config.mikan_resolve_detail" size="small" />
                    <span class="text-xs opacity-50">解析详情</span>
                  </div>
                </div>
              </div>
            </div>
          </n-card>

          <!-- 猫眼 -->
          <n-card title="猫眼榜单" size="small" :bordered="true" class="mb-4">
            <div class="flex flex-col gap-4">
              <div class="flex items-center justify-between">
                <label class="text-xs opacity-50 font-medium">启用</label>
                <n-switch v-model:value="config.maoyan_enabled" />
              </div>
              <div v-if="config.maoyan_enabled" class="flex flex-col gap-4">
                <div class="flex items-center gap-2">
                  <n-switch v-model:value="config.maoyan_movie_box" size="small" />
                  <span class="text-xs opacity-50">实时票房榜</span>
                </div>
                <div class="flex items-center gap-1.5">
                  <span class="text-xs opacity-50">网播榜条数</span>
                  <n-input-number v-model:value="config.maoyan_num" :min="1" :max="50" size="small" style="width: 100px;" />
                </div>
                <div class="flex flex-col gap-1.5">
                  <label class="text-xs opacity-50 font-medium">平台</label>
                  <div class="flex flex-wrap gap-2">
                    <label v-for="p in (meta?.maoyan_platforms || [])" :key="p.value"
                      class="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded cursor-pointer"
                      :class="config.maoyan_web_platforms?.includes(p.value) ? 'bg-blue-500 text-white' : 'bg-gray-100 dark:bg-gray-800'"
                      @click="toggleArray(config.maoyan_web_platforms, p.value)">
                      {{ p.label }}
                    </label>
                  </div>
                </div>
                <div class="flex flex-col gap-1.5">
                  <label class="text-xs opacity-50 font-medium">媒体类型</label>
                  <div class="flex flex-wrap gap-2">
                    <label v-for="t in (meta?.maoyan_media_types || [])" :key="t.value"
                      class="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded cursor-pointer"
                      :class="config.maoyan_web_types?.includes(t.value) ? 'bg-blue-500 text-white' : 'bg-gray-100 dark:bg-gray-800'"
                      @click="toggleArray(config.maoyan_web_types, t.value)">
                      {{ t.label }}
                    </label>
                  </div>
                </div>
              </div>
            </div>
          </n-card>

          <!-- 操作按钮 -->
          <div class="flex items-center gap-2 mb-4">
            <n-button type="primary" :loading="saving" @click="handleSave">
              <template #icon><i class="ri-save-line"></i></template>
              保存配置
            </n-button>
            <n-button :loading="running" :disabled="scheduleRunning" @click="handleRun">
              <template #icon><i class="ri-play-line"></i></template>
              手动运行
            </n-button>
          </div>
        </n-spin>
      </n-tab-pane>

      <n-tab-pane name="history" tab="订阅历史">
        <n-card size="small" :bordered="true">
          <template #header>
            <div class="flex items-center justify-between">
              <span class="text-sm font-medium">处理历史</span>
              <div class="flex items-center gap-2">
                <span v-if="lastRun" class="text-xs opacity-40">上次运行: {{ formatDateTime(lastRun) }}</span>
                <n-button size="tiny" quaternary @click="handleClearHistory">
                  <template #icon><i class="ri-delete-bin-line"></i></template>
                  清空
                </n-button>
              </div>
            </div>
          </template>
          <n-spin :show="loading">
            <n-data-table v-if="history.length > 0"
              :columns="[
                { title: '标题', key: 'key', ellipsis: { tooltip: true }, minWidth: 200 },
                { title: '状态', key: 'status', width: 100,
                  render: (row) => h('n-tag', { size: 'tiny', type: row.status === 'subscribed' ? 'success' : 'default', round: true }, { default: () => statusLabels[row.status] || row.status }),
                },
                { title: 'TMDB ID', key: 'tmdb_id', width: 100, render: (row) => row.tmdb_id || '-' },
                { title: '类别', key: 'media_type', width: 80,
                  render: (row) => row.media_type === 'movie' ? '电影' : row.media_type === 'tv' ? '剧集' : '-',
                },
                { title: '时间', key: 'time', width: 180, render: (row) => formatDateTime(row.time) },
              ]"
              :data="history" :bordered="false" :single-line="false" size="small"
              :row-key="(row) => row.key" />
            <n-empty v-else description="暂无处理记录" class="py-8" size="small" />
          </n-spin>
        </n-card>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>