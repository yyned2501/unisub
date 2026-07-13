<template>
  <el-card class="media-card" :body-style="{ padding: '0' }" shadow="hover">
    <div class="poster-wrapper">
      <el-image
        :src="media.poster_url"
        fit="cover"
        class="poster-image"
        @error="handleImageError"
      >
        <template #error>
          <div class="poster-fallback">
            <el-icon :size="48"><VideoCamera /></el-icon>
            <span>暂无海报</span>
          </div>
        </template>
        <template #placeholder>
          <div class="poster-loading">
            <el-icon :size="32" class="is-loading"><Loading /></el-icon>
          </div>
        </template>
      </el-image>
      <el-tag
        class="type-badge"
        :type="media.media_type === 'tv' ? 'primary' : 'success'"
        size="small"
        effect="dark"
      >
        {{ media.media_type === 'tv' ? '剧集' : '电影' }}
      </el-tag>
    </div>
    <div class="card-body">
      <h4 class="media-title" :title="media.title">{{ media.title }}</h4>
      <div class="card-footer">
        <span v-if="media.year" class="media-year">{{ media.year }}</span>
        <span v-else class="media-year media-year--na">未知年份</span>
        <el-button
          type="primary"
          size="small"
          :disabled="subscribed"
          @click="$emit('subscribe', media)"
        >
          {{ subscribed ? '已订阅' : '订阅' }}
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { VideoCamera, Loading } from '@element-plus/icons-vue'

defineProps({
  media: {
    type: Object,
    required: true,
  },
  subscribed: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['subscribe'])

function handleImageError(e) {
  // 图片加载失败时触发 Element Plus Image 的 error slot
}
</script>

<style scoped>
.media-card {
  width: 200px;
  border-radius: 8px;
  overflow: hidden;
  transition: transform 0.2s, box-shadow 0.2s;
}

.media-card:hover {
  transform: translateY(-4px);
}

.poster-wrapper {
  position: relative;
  width: 100%;
  height: 280px;
  overflow: hidden;
  background: #f5f5f5;
}

.poster-image {
  width: 100%;
  height: 100%;
}

.poster-image :deep(img) {
  object-fit: cover;
}

.poster-fallback {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #c0c4cc;
  background: #f5f5f5;
  gap: 8px;
  font-size: 13px;
}

.poster-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #c0c4cc;
}

.type-badge {
  position: absolute;
  top: 8px;
  left: 8px;
}

.card-body {
  padding: 12px;
}

.media-title {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 10px;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.media-year {
  font-size: 13px;
  color: #909399;
}

.media-year--na {
  font-style: italic;
}
</style>
