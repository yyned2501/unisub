<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { NButton, NCard, NSwitch, NInput, NInputNumber, NSelect, NSpin, NTabs, NTabPane } from 'naive-ui'
import {
  getAutoSubConfig,
  updateAutoSubConfig,
  triggerAutoSubRun,
  getAutoSubHistory,
  clearAutoSubHistory,
  getAutoSubMeta,
} from '@/service/api/autoSubscribe'
import { DEFAULT_CONFIG, DEFAULT_META } from '@/components/auto-subscribe/defaults'
import SourceConfigPanel from '@/components/auto-subscribe/SourceConfigPanel.vue'
import HistoryTable from '@/components/auto-subscribe/HistoryTable.vue'
import { msg } from '@/utils/message'
import type { AutoSubConfig, AutoSubMetaResponse, AutoSubHistoryItem, SelectOption } from '@/types'

defineOptions({ name: 'AutoSubscribeSettings' })

/* ---------- state ---------- */
const loading = ref(false)
const saving = ref(false)
const running = ref(false)
const config = reactive<AutoSubConfig>({ ...DEFAULT_CONFIG } as AutoSubConfig)
const meta = ref<AutoSubMetaResponse>(DEFAULT_META as AutoSubMetaResponse)
const history = ref<AutoSubHistoryItem[]>([])
const lastRun = ref('')
const lastStats = ref<Record<string, unknown> | null>(null)
const statusLabels = ref<Record<string, string>>({})
const sourceNames = ref<Record<string, string>>({})
const scheduleRunning = ref(false)
const scheduleError = ref('')
const activeTab = ref('config')

/* ---------- helpers ---------- */
function toggleArray(key: string, val: string) {
  const arr = config[key]
  if (!Array.isArray(arr)) return
  const idx = arr.indexOf(val)
  if (idx >= 0) arr.splice(idx, 1)
  else arr.push(val)
}

/* ---------- data loading ---------- */
async function load() {
  loading.value = true
  try {
    const [cfg, remoteMeta, hist] = await Promise.all([
      getAutoSubConfig(),
      getAutoSubMeta(),
      getAutoSubHistory(),
    ])
    Object.assign(config, DEFAULT_CONFIG, cfg.config || {})
    for (const key of [
      'douban_ranks',
      'maoyan_web_platforms',
      'maoyan_web_types',
    ] as const) {
      if (!Array.isArray(config[key])) config[key] = [...DEFAULT_CONFIG[key]]
    }
    statusLabels.value = cfg.status_labels || {}
    sourceNames.value = cfg.source_names || {}
    lastRun.value = cfg.last_run ?? ''
    lastStats.value = cfg.last_stats
    scheduleRunning.value = Boolean(cfg.running)
    scheduleError.value = cfg.last_error || ''
    const metaPayload = remoteMeta || {}
    meta.value = {
      ...DEFAULT_META,
      ...metaPayload,
      douban_ranks: metaPayload.douban_ranks?.length ? metaPayload.douban_ranks : DEFAULT_META.douban_ranks,
      maoyan_platforms: metaPayload.maoyan_platforms?.length ? metaPayload.maoyan_platforms : DEFAULT_META.maoyan_platforms,
      maoyan_media_types: metaPayload.maoyan_media_types?.length ? metaPayload.maoyan_media_types : DEFAULT_META.maoyan_media_types,
      seasons: metaPayload.seasons?.length ? metaPayload.seasons : DEFAULT_META.seasons,
    }
    history.value = hist.items || []
  } catch (error: unknown) {
    msg.error((error as import('axios').AxiosError<{ detail?: string }>)?.response?.data?.detail || '自动订阅配置加载失败')
  } finally {
    loading.value = false
  }
}

/* ---------- actions ---------- */
async function handleSave() {
  saving.value = true
  try {
    await updateAutoSubConfig({ config: { ...config } })
    msg.success('配置已保存')
  } catch (error: unknown) {
    msg.error((error as import('axios').AxiosError<{ detail?: string }>)?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleRun() {
  running.value = true
  try {
    const data = await triggerAutoSubRun()
    msg.success(data.message || '自动订阅已启动')
    await load()
  } catch (e: unknown) {
    msg.error((e as import('axios').AxiosError<{ detail?: string }>)?.response?.data?.detail || '启动失败')
  } finally {
    running.value = false
  }
}

async function handleClearHistory() {
  try {
    await clearAutoSubHistory()
    history.value = []
    msg.success('历史已清空')
  } catch {
    msg.error('清空失败')
  }
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
          <SourceConfigPanel
            source="douban"
            :config="config"
            :meta="meta"
            title="豆瓣榜单"
            @toggle-array="toggleArray"
          />

          <!-- Mikan -->
          <SourceConfigPanel
            source="mikan"
            :config="config"
            :meta="meta"
            title="Mikan 新番"
            @toggle-array="toggleArray"
          />

          <!-- 猫眼 -->
          <SourceConfigPanel
            source="maoyan"
            :config="config"
            :meta="meta"
            title="猫眼榜单"
            @toggle-array="toggleArray"
          />

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
        <HistoryTable
          :history="history"
          :loading="loading"
          :last-run="lastRun"
          :status-labels="statusLabels"
          @clear-history="handleClearHistory"
        />
      </n-tab-pane>
    </n-tabs>
  </div>
</template>