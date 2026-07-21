<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { getEmbyLibraryAnalysis, syncEmbyCache, triggerEmbyScan, getEmbyScanStatus, addToBlacklist, removeFromBlacklist, subscribeFromEmby, fillMissingFromEmby } from '@/service/api/emby'
import { onImgError } from '@/utils/format'

defineOptions({ name: 'EmbyAnalysis' })

const loading = ref(false)
const syncing = ref(false)
const analysis = ref(null)
const searchText = ref('')
const showHidden = ref(false)
const hidingIds = ref(new Set())
const subscribingIds = ref(new Set())
const fillingIds = ref(new Set())

// 分页
const page = ref(1)
const pageSize = ref(50)
const libraryFilter = ref('')

// 扫描进度
const scanRunning = ref(false)
const scanProgress = ref(0)
const scanStepName = ref('')
const scanItem = ref('')
let pollTimer = null

const libraries = computed(() => {
  if (!analysis.value) return []
  return analysis.value.libraries || []
})

const filteredSeries = computed(() => {
  if (!analysis.value) return []
  let items = analysis.value.series || []

  // 搜索过滤
  if (searchText.value.trim()) {
    const kw = searchText.value.trim().toLowerCase()
    items = items.filter(s =>
      (s.emby_series_name || '').toLowerCase().includes(kw)
    )
  }

  // 黑名单过滤
  if (!showHidden.value) {
    items = items.filter(s => !s.is_blacklisted)
  }

  return items
})

async function load() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
    }
    if (libraryFilter.value) {
      params.library = libraryFilter.value
    }
    const { data } = await getEmbyLibraryAnalysis(params)
    analysis.value = data
  } catch {
    analysis.value = null
  } finally {
    loading.value = false
  }
}

function handlePageChange(p) {
  page.value = p
  load()
}

function handleLibraryChange(val) {
  libraryFilter.value = val || ''
  page.value = 1
  load()
}

async function handleSync() {
  syncing.value = true
  try {
    await syncEmbyCache()
    window.$message?.success('Emby 缓存同步完成')
    await load()
  } catch {
    window.$message?.error('同步失败')
  } finally {
    syncing.value = false
  }
}

async function handleFullScan() {
  try {
    await triggerEmbyScan()
    scanRunning.value = true
    scanProgress.value = 0
    scanStepName.value = '正在启动扫描...'
    startPolling()
    window.$message?.success('全量扫描已启动')
  } catch (e) {
    window.$message?.error(e.response?.data?.detail || '启动扫描失败')
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const { data } = await getEmbyScanStatus()
      if (data) {
        scanRunning.value = data.running
        scanProgress.value = data.progress || 0
        scanStepName.value = data.step_name || ''
        scanItem.value = data.current_item || ''
        if (data.error) {
          window.$message?.error(`扫描出错: ${data.error}`)
          stopPolling()
        }
        if (!data.running && scanProgress.value >= 100) {
          stopPolling()
          window.$message?.success('全量扫描完成')
          await load()
        }
        if (!data.running && data.error) {
          stopPolling()
          await load()
        }
      }
    } catch {
      stopPolling()
    }
  }, 1500)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function handleHide(tmdbId) {
  hidingIds.value = new Set([...hidingIds.value, tmdbId])
  try {
    await addToBlacklist(tmdbId)
    if (analysis.value) {
      const s = analysis.value.series.find(item => item.tmdb_id === tmdbId)
      if (s) s.is_blacklisted = true
    }
    window.$message?.success('已隐藏')
  } catch {
    window.$message?.error('隐藏失败')
  } finally {
    const next = new Set(hidingIds.value)
    next.delete(tmdbId)
    hidingIds.value = next
  }
}

async function handleUnhide(tmdbId) {
  hidingIds.value = new Set([...hidingIds.value, tmdbId])
  try {
    await removeFromBlacklist(tmdbId)
    if (analysis.value) {
      const s = analysis.value.series.find(item => item.tmdb_id === tmdbId)
      if (s) s.is_blacklisted = false
    }
    window.$message?.success('已取消隐藏')
  } catch {
    window.$message?.error('取消隐藏失败')
  } finally {
    const next = new Set(hidingIds.value)
    next.delete(tmdbId)
    hidingIds.value = next
  }
}

async function handleSubscribe(s) {
  subscribingIds.value = new Set([...subscribingIds.value, s.tmdb_id])
  try {
    const { data } = await subscribeFromEmby(s.tmdb_id, s.emby_series_name || s.title || '未知', 'tv', s.poster_url, s.emby_year)
    if (data?.success) {
      if (analysis.value) {
        const item = analysis.value.series.find(x => x.tmdb_id === s.tmdb_id)
        if (item) item.is_subscribed = true
      }
      window.$message?.success(data.message || '订阅成功')
    } else {
      window.$message?.error(data?.message || '订阅失败')
    }
  } catch (e) {
    window.$message?.error(e.response?.data?.detail || '订阅失败')
  } finally {
    const next = new Set(subscribingIds.value)
    next.delete(s.tmdb_id)
    subscribingIds.value = next
  }
}

async function handleFillMissing(tmdbId) {
  fillingIds.value = new Set([...fillingIds.value, tmdbId])
  try {
    const { data } = await fillMissingFromEmby(tmdbId)
    if (data?.success) {
      window.$message?.success(data.message || '补缺集已触发')
    } else {
      window.$message?.error(data?.message || '补缺集失败')
    }
  } catch (e) {
    window.$message?.error(e.response?.data?.detail || '补缺集失败')
  } finally {
    const next = new Set(fillingIds.value)
    next.delete(tmdbId)
    fillingIds.value = next
  }
}

onMounted(() => load())
onUnmounted(() => stopPolling())
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-bold">Emby 缺集分析</h2>
      <div class="flex items-center gap-2">
        <n-button size="small" secondary :loading="syncing" @click="handleSync">
          <template #icon><i class="ri-download-line"></i></template>
          同步缓存
        </n-button>
        <n-button size="small" type="primary" :disabled="scanRunning" :loading="scanRunning" @click="handleFullScan">
          <template #icon><i class="ri-refresh-line"></i></template>
          TMDB 全量扫描
        </n-button>
        <n-button size="small" secondary :loading="loading" @click="load">
          <template #icon><i class="ri-refresh-line"></i></template>
          刷新
        </n-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div v-if="analysis" class="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-4">
      <n-card size="small" :bordered="true">
        <div class="flex items-center gap-3">
          <div class="flex items-center justify-center w-10 h-10 rounded-lg shrink-0" style="background: rgba(59,130,246,0.12);">
            <i class="ri-tv-2-line text-lg" style="color: rgb(96,165,250);"></i>
          </div>
          <div>
            <div class="text-xs opacity-50">Emby 剧集总数</div>
            <div class="text-xl font-bold">{{ analysis.total_series }}</div>
          </div>
        </div>
      </n-card>
      <n-card size="small" :bordered="true">
        <div class="flex items-center gap-3">
          <div class="flex items-center justify-center w-10 h-10 rounded-lg shrink-0" style="background: rgba(34,197,94,0.12);">
            <i class="ri-rss-line text-lg" style="color: rgb(74,222,128);"></i>
          </div>
          <div>
            <div class="text-xs opacity-50">已订阅</div>
            <div class="text-xl font-bold">{{ analysis.subscribed_count }}</div>
          </div>
        </div>
      </n-card>
      <n-card size="small" :bordered="true">
        <div class="flex items-center gap-3">
          <div class="flex items-center justify-center w-10 h-10 rounded-lg shrink-0" style="background: rgba(251,146,60,0.12);">
            <i class="ri-error-warning-line text-lg" style="color: rgb(251,146,60);"></i>
          </div>
          <div>
            <div class="text-xs opacity-50">缺集</div>
            <div class="text-xl font-bold">{{ analysis.missing_count }}</div>
          </div>
        </div>
      </n-card>
      <n-card size="small" :bordered="true">
        <div class="flex items-center gap-3">
          <div class="flex items-center justify-center w-10 h-10 rounded-lg shrink-0" style="background: rgba(239,68,68,0.12);">
            <i class="ri-eye-off-line text-lg" style="color: rgb(248,113,113);"></i>
          </div>
          <div>
            <div class="text-xs opacity-50">已隐藏</div>
            <div class="text-xl font-bold">{{ analysis.series.filter(s => s.is_blacklisted).length }}</div>
          </div>
        </div>
      </n-card>
    </div>

    <!-- 工具栏 -->
    <div v-if="analysis" class="flex items-center gap-3 mb-4 flex-wrap">
      <n-input v-model:value="searchText" placeholder="搜索剧集名称..." clearable size="small" style="max-width: 300px;">
        <template #prefix><i class="ri-search-line opacity-40"></i></template>
      </n-input>

      <n-select
        v-model:value="libraryFilter"
        :options="libraries.map(l => ({ label: l, value: l }))"
        placeholder="全部媒体库"
        clearable
        size="small"
        style="max-width: 180px;"
        @update:value="handleLibraryChange"
      />

      <div class="flex items-center gap-2 text-xs opacity-60">
        <n-switch v-model:value="showHidden" size="small" />
        <span>显示已隐藏</span>
      </div>

      <div class="text-xs opacity-40 ml-auto">
        共 {{ analysis.missing_count }} 条缺集记录
      </div>
    </div>

    <!-- 扫描进度条 -->
    <n-card v-if="scanRunning" size="small" :bordered="true" class="mb-4">
      <div class="flex flex-col gap-2">
        <div class="flex items-center justify-between text-xs">
          <span class="opacity-70">{{ scanStepName }}</span>
          <span class="font-medium">{{ Math.round(scanProgress) }}%</span>
        </div>
        <n-progress
          type="line"
          :percentage="Math.round(scanProgress)"
          :height="18"
          :processing="scanRunning"
          color="#3b82f6"
        />
        <div v-if="scanItem" class="text-xs opacity-40 truncate">
          当前: {{ scanItem }}
        </div>
      </div>
    </n-card>

    <n-spin :show="loading || syncing">
      <!-- 缓存为空时的提示 -->
      <n-empty v-if="analysis && analysis.total_series === 0 && !loading"
        description="缓存为空，请先同步 Emby 数据" size="small" class="py-12">
        <template #extra>
          <n-button size="small" :loading="syncing" @click="handleSync">
            <template #icon><i class="ri-download-line"></i></template>
            立即同步
          </n-button>
        </template>
      </n-empty>

      <!-- 无缺集 -->
      <n-empty v-else-if="analysis && filteredSeries.length === 0 && !loading"
        description="没有缺集的剧集" size="small" class="py-8" />

      <!-- 剧集列表 -->
      <n-card v-else-if="analysis && analysis.total_series > 0" size="small" :bordered="true" class="mb-4">
        <div class="divide-y" :style="{ 'border-bottom': '1px solid var(--n-border-color)' }">
          <template v-for="s in filteredSeries" :key="s.tmdb_id">
            <div class="flex items-start gap-3 py-2.5 px-1"
              :class="{ 'opacity-50': s.is_blacklisted }">

              <!-- 海报 -->
              <img v-if="s.emby_image_url" :src="s.emby_image_url" :alt="s.emby_series_name"
                class="w-10 h-14 rounded object-cover shrink-0"
                @error="onImgError" />
              <img v-else-if="s.poster_url" :src="s.poster_url" :alt="s.emby_series_name"
                class="w-10 h-14 rounded object-cover shrink-0" />
              <div v-else class="w-10 h-14 rounded flex items-center justify-center shrink-0"
                :style="{ background: 'var(--n-action-color)' }">
                <i class="ri-film-line opacity-40"></i>
              </div>

              <!-- 信息 -->
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-0.5">
                  <span class="text-sm font-medium truncate">{{ s.emby_series_name || '未知' }}</span>
                  <span v-if="s.emby_year" class="text-xs opacity-40 shrink-0">({{ s.emby_year }})</span>
                  <n-tag v-if="s.emby_library_name" size="tiny" type="info" round class="shrink-0">{{ s.emby_library_name }}</n-tag>
                </div>

                <div class="flex items-center gap-2 text-xs">
                  <n-tag v-if="s.is_subscribed" size="tiny" type="success" round>已订阅</n-tag>
                  <n-tag v-else size="tiny" type="default" round>未订阅</n-tag>

                  <span class="opacity-40">|</span>

                  <span class="opacity-50">Emby: {{ s.emby_episode_count ?? 0 }} 集</span>

                  <template v-if="s.tmdb_aired_eps !== null">
                    <span class="opacity-40">|</span>
                    <span class="text-green-500">已播出 {{ s.tmdb_aired_eps }} 集</span>
                  </template>
                  <template v-else-if="s.tmdb_total_eps !== null">
                    <span class="opacity-40">|</span>
                    <span class="text-green-500">TMDB 共 {{ s.tmdb_total_eps }} 集</span>
                  </template>

                  <span v-if="s.adjusted_missing !== null && s.adjusted_missing > 0"
                    class="text-yellow-500 font-medium">
                    | 缺: {{ s.adjusted_missing }}
                  </span>

                  <span v-if="s.tmdb_next_air_date" class="opacity-40">
                    | 下一集: {{ s.tmdb_next_air_date }}
                  </span>
                </div>

                <div v-if="s.overview" class="text-xs opacity-30 mt-0.5 truncate">{{ s.overview }}</div>
              </div>

              <!-- 操作按钮 -->
              <div class="flex items-center gap-1 shrink-0">
                <n-button v-if="!s.is_subscribed" size="tiny" type="primary" secondary
                  :loading="subscribingIds.has(s.tmdb_id)"
                  @click="handleSubscribe(s)">
                  <template #icon><i class="ri-add-line"></i></template>
                  添加订阅
                </n-button>
                <n-button v-if="s.adjusted_missing > 0" size="tiny" type="warning" secondary
                  :loading="fillingIds.has(s.tmdb_id)"
                  @click="handleFillMissing(s.tmdb_id)">
                  <template #icon><i class="ri-refresh-line"></i></template>
                  立即补缺
                </n-button>
                <n-button v-if="!s.is_blacklisted" size="tiny" quaternary
                  :loading="hidingIds.has(s.tmdb_id)"
                  @click="handleHide(s.tmdb_id)">
                  <template #icon><i class="ri-eye-off-line"></i></template>
                </n-button>
                <n-button v-else size="tiny" quaternary type="warning"
                  :loading="hidingIds.has(s.tmdb_id)"
                  @click="handleUnhide(s.tmdb_id)">
                  <template #icon><i class="ri-eye-line"></i></template>
                </n-button>
              </div>
            </div>
          </template>
        </div>
      </n-card>

      <!-- 分页 -->
      <div v-if="analysis && analysis.total_pages > 1" class="flex justify-center">
        <n-pagination
          :page="analysis.page"
          :page-count="analysis.total_pages"
          :page-size="analysis.page_size"
          @update:page="handlePageChange"
        />
      </div>

      <!-- 未配置 Emby -->
      <n-empty v-if="!analysis && !loading && !syncing" description="Emby 平台未配置，请在平台配置中添加 Emby" size="small" class="py-12">
        <template #extra>
          <n-button size="small" @click="$router.push('/settings/platforms')">
            前往配置
          </n-button>
        </template>
      </n-empty>
    </n-spin>
  </div>
</template>