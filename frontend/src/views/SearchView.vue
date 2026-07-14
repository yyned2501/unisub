<script setup>
import { ref, computed } from 'vue'
import { searchMedia } from '@/service/api/search'
import { createSubscription } from '@/service/api/subscriptions'
import SubDialog from '@/components/SubDialog.vue'

defineOptions({ name: 'SearchView' })

const keyword = ref('')
const searchType = ref('all')
const results = ref([])
const loading = ref(false)
const searched = ref(false)

const subDialogVisible = ref(false)
const selectedMedia = ref(null)
const subscribedIds = ref(new Set())

const currentPage = ref(1)
const pageSize = 20

const totalPages = computed(() => Math.ceil(results.value.length / pageSize))

const pagedResults = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return results.value.slice(start, start + pageSize)
})

function isSubscribed(tmdbId) {
  return subscribedIds.value.has(tmdbId)
}

function clearSearch() {
  keyword.value = ''
  results.value = []
  searched.value = false
  currentPage.value = 1
}

async function handleSearch() {
  if (!keyword.value.trim()) {
    window.$message?.warning('请输入搜索关键词')
    return
  }
  loading.value = true
  searched.value = true
  currentPage.value = 1
  try {
    const { data } = await searchMedia(keyword.value.trim(), searchType.value)
    results.value = Array.isArray(data) ? data : data?.items || []
  } catch {
    results.value = []
  } finally {
    loading.value = false
  }
}

function openSubDialog(media) {
  selectedMedia.value = media
  subDialogVisible.value = true
}

async function handleSubscribe(media, done) {
  try {
    await createSubscription({
      tmdb_id: media.tmdb_id,
      media_type: media.media_type,
      title: media.title,
      poster_url: media.poster_url || '',
      year: media.year || null,
    })
    subscribedIds.value.add(media.tmdb_id)
    window.$message?.success(`已订阅「${media.title}」`)
    done(true)
  } catch {
    done(false)
  }
}
</script>

<template>
  <div>
    <!-- 搜索栏 -->
    <n-card :bordered="true" size="small" class="!rounded-2xl mb-6">
      <div class="flex gap-2 mb-3">
        <n-button v-for="t in [{ label: '全部', value: 'all' }, { label: '电影', value: 'movie' }, { label: '剧集', value: 'tv' }]"
          :key="t.value" size="tiny"
          :type="searchType === t.value ? 'primary' : 'default'"
          :secondary="searchType !== t.value"
          @click="searchType = t.value">
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
          <n-button size="small" :type="loading ? 'default' : 'primary'" :loading="loading" @click="handleSearch" class="!rounded-lg">
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
        <div class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 2xl:grid-cols-10 gap-2.5">
          <div v-for="item in pagedResults" :key="item.tmdb_id"
            class="rounded-xl p-0.5 cursor-pointer transition-colors hover:bg-[var(--n-action-color)]"
            @click="openSubDialog(item)">
            <div class="relative w-full pb-[150%] rounded-lg overflow-hidden bg-[var(--n-border-color)]">
              <img
                :src="item.poster_url || ''"
                class="absolute inset-0 w-full h-full object-cover"
                :alt="item.title"
                @error="$event.target.src = 'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22300%22><rect fill=%22%2327272a%22 width=%22200%22 height=%22300%22/><text fill=%22%236b7280%22 font-size=%2230%22 x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 dy=%22.3em%22>%3F</text></svg>'"
              />
              <n-tag :type="item.media_type === 'tv' ? 'primary' : 'success'" size="tiny" class="!absolute top-1.5 left-1.5" round>
                {{ item.media_type === 'tv' ? '剧集' : '电影' }}
              </n-tag>
              <div v-if="isSubscribed(item.tmdb_id)" class="absolute bottom-1.5 left-1.5 w-7 h-7 rounded-full bg-black/50 flex items-center justify-center">
                <i class="ri-rss-fill text-sm" style="color: rgb(96,165,250);"></i>
              </div>
            </div>
            <div class="px-0.5 pt-1.5 text-center">
              <div class="text-xs truncate font-medium">{{ item.title }}</div>
              <div class="text-xs mt-0.5 opacity-40">{{ item.year || '未知年份' }}</div>
            </div>
          </div>
        </div>

        <div v-if="results.length > pageSize" class="flex items-center justify-center gap-4 mt-7 py-3">
          <span class="text-xs opacity-50">{{ results.length }} 条结果</span>
          <n-pagination :page="currentPage" :page-count="totalPages" :page-slot="5" size="small" @update:page="currentPage = $event" />
        </div>
      </template>
    </n-spin>

    <SubDialog v-model="subDialogVisible" :media="selectedMedia" @confirm="handleSubscribe" />
  </div>
</template>
