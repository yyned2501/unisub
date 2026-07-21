<script setup lang="ts">
import { useEmbyAnalysis } from '@/composables/useEmbyAnalysis'
import EmbyStatsCards from '@/components/emby/EmbyStatsCards.vue'
import EmbyScanProgress from '@/components/emby/EmbyScanProgress.vue'
import EmbySeriesItem from '@/components/emby/EmbySeriesItem.vue'

defineOptions({ name: 'EmbyAnalysis' })

const {
  loading,
  syncing,
  analysis,
  searchText,
  showHidden,
  libraryFilter,
  hidingIds,
  subscribingIds,
  fillingIds,
  libraries,
  filteredSeries,
  scanRunning,
  scanProgress,
  scanStepName,
  scanItem,
  load,
  handlePageChange,
  handleLibraryChange,
  handleSync,
  handleFullScan,
  handleHide,
  handleUnhide,
  handleSubscribe,
  handleFillMissing,
} = useEmbyAnalysis()
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
    <EmbyStatsCards v-if="analysis" :analysis="analysis" />

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
    <EmbyScanProgress
      :running="scanRunning"
      :progress="scanProgress"
      :step-name="scanStepName"
      :current-item="scanItem"
    />

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
          <EmbySeriesItem
            v-for="s in filteredSeries"
            :key="s.tmdb_id"
            :s="s"
            :hiding="hidingIds.has(s.tmdb_id)"
            :subscribing="subscribingIds.has(s.tmdb_id)"
            :filling="fillingIds.has(s.tmdb_id)"
            @hide="handleHide"
            @unhide="handleUnhide"
            @subscribe="handleSubscribe"
            @fill="handleFillMissing"
          />
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