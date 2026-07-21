<script setup lang="ts">
import { ref } from 'vue'
import { useSearch } from '@/composables/useSearch'
import MediaCard from '@/components/MediaCard.vue'
import SubDialog from '@/components/SubDialog.vue'
import type { SearchResultItem } from '@/types'

defineOptions({ name: 'SearchView' })

const {
  keyword,
  searchType,
  loading,
  searched,
  currentPage,
  totalPages,
  pagedResults,
  isSubscribed,
  clearSearch,
  handleSearch,
  handleSubscribe,
  setPage,
} = useSearch()

const subDialogVisible = ref(false)
const selectedMedia = ref<SearchResultItem | null>(null)

const typeOptions = [
  { label: '全部', value: 'all' },
  { label: '电影', value: 'movie' },
  { label: '剧集', value: 'tv' },
] as const

function openSubDialog(media: SearchResultItem) {
  selectedMedia.value = media
  subDialogVisible.value = true
}
</script>

<template>
  <div>
    <!-- 搜索栏 -->
    <n-card :bordered="true" size="small" class="!rounded-2xl mb-6">
      <div class="flex gap-2 mb-3">
        <n-button
          v-for="t in typeOptions"
          :key="t.value"
          size="tiny"
          :type="searchType === t.value ? 'primary' : 'default'"
          :secondary="searchType !== t.value"
          @click="searchType = t.value"
        >
          {{ t.label }}
        </n-button>
      </div>
      <n-input
        v-model:value="keyword"
        placeholder="搜索电影、电视剧、TMDB ID..."
        size="large"
        clearable
        @keyup.enter="handleSearch"
        @clear="clearSearch"
      >
        <template #suffix>
          <n-button
            size="small"
            :type="loading ? 'default' : 'primary'"
            :loading="loading"
            @click="handleSearch"
            class="!rounded-lg"
          >
            <template #icon><i :class="loading ? 'ri-loader-4-line animate-spin' : 'ri-search-line'"></i></template>
          </n-button>
        </template>
      </n-input>
    </n-card>

    <!-- 搜索结果 -->
    <n-spin :show="loading">
      <n-empty v-if="searched && pagedResults.length === 0" description="未找到相关结果" class="py-20" />
      <n-empty v-else-if="!searched" description="输入关键词开始搜索" class="py-20">
        <template #icon><i class="ri-search-line text-6xl opacity-30"></i></template>
      </n-empty>

      <template v-else>
        <div
          class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 2xl:grid-cols-10 gap-2.5"
        >
          <MediaCard
            v-for="item in pagedResults"
            :key="item.tmdb_id"
            :media="item"
            :subscribed="isSubscribed(item.tmdb_id)"
            @click="openSubDialog"
            @subscribe="openSubDialog"
          />
        </div>

        <div v-if="pagedResults.length > 0 && totalPages > 1" class="flex items-center justify-center gap-4 mt-7 py-3">
          <span class="text-xs opacity-50">{{ pagedResults.length }} 条结果</span>
          <n-pagination
            :page="currentPage"
            :page-count="totalPages"
            :page-slot="5"
            size="small"
            @update:page="setPage"
          />
        </div>
      </template>
    </n-spin>

    <SubDialog v-model="subDialogVisible" :media="selectedMedia" @confirm="handleSubscribe" />
  </div>
</template>
