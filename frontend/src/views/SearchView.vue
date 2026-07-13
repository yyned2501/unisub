<template>
  <div class="search-view">
    <!-- 搜索栏 -->
    <el-card shadow="never" class="search-bar-card">
      <div class="search-bar">
        <el-select v-model="searchType" placeholder="类型" style="width: 120px">
          <el-option label="全部" value="all" />
          <el-option label="电影" value="movie" />
          <el-option label="剧集" value="tv" />
        </el-select>
        <el-input
          v-model="keyword"
          placeholder="输入关键词搜索..."
          clearable
          class="search-input"
          @keyup.enter="handleSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" :loading="loading" @click="handleSearch">
          搜索
        </el-button>
      </div>
    </el-card>

    <!-- 搜索结果 -->
    <div class="results-section" v-loading="loading">
      <div v-if="!loading && searched && results.length === 0" class="empty-result">
        <el-empty description="未找到相关结果" />
      </div>

      <div v-if="!loading && !searched" class="empty-result">
        <el-empty description="输入关键词开始搜索" />
      </div>

      <div v-if="results.length > 0" class="results-grid">
        <MediaCard
          v-for="item in results"
          :key="item.tmdb_id"
          :media="item"
          :subscribed="isSubscribed(item.tmdb_id)"
          @subscribe="openSubDialog"
        />
      </div>
    </div>

    <!-- 订阅确认弹窗 -->
    <SubDialog
      v-model="subDialogVisible"
      :media="selectedMedia"
      @confirm="handleSubscribe"
    />

    <!-- 分页 -->
    <div v-if="results.length > pageSize" class="pagination-wrap">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="results.length"
        layout="prev, pager, next"
        background
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { searchMedia } from '../api/search'
import { createSubscription } from '../api/subscriptions'
import MediaCard from '../components/MediaCard.vue'
import SubDialog from '../components/SubDialog.vue'

const keyword = ref('')
const searchType = ref('all')
const results = ref([])
const loading = ref(false)
const searched = ref(false)

const subDialogVisible = ref(false)
const selectedMedia = ref(null)

/** 已订阅的 TMDB ID 集合（简单前端去重，实际以后端为准） */
const subscribedIds = ref(new Set())

// 分页
const currentPage = ref(1)
const pageSize = 20

const pagedResults = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return results.value.slice(start, start + pageSize)
})

function isSubscribed(tmdbId) {
  return subscribedIds.value.has(tmdbId)
}

async function handleSearch() {
  if (!keyword.value.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  loading.value = true
  searched.value = true
  currentPage.value = 1
  try {
    const { data } = await searchMedia(keyword.value.trim(), searchType.value)
    results.value = Array.isArray(data) ? data : data.results || []
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
    ElMessage.success(`已订阅「${media.title}」`)
    done(true)
  } catch {
    done(false)
  }
}
</script>

<style scoped>
.search-view {
  max-width: 1200px;
}

.search-bar-card {
  margin-bottom: 20px;
}

.search-bar {
  display: flex;
  gap: 12px;
  align-items: center;
}

.search-input {
  flex: 1;
}

.results-section {
  min-height: 200px;
}

.results-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.empty-result {
  display: flex;
  justify-content: center;
  padding: 60px 0;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}
</style>
