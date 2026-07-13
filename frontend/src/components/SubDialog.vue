<template>
  <el-dialog
    v-model="visible"
    title="确认订阅"
    width="420px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <div class="sub-dialog-body" v-if="media">
      <div class="media-info">
        <el-image
          :src="media.poster_url"
 fit="cover"
          class="dialog-poster"
          v-if="media.poster_url"
        >
          <template #error>
            <div class="dialog-poster-fallback">
              <el-icon :size="40"><VideoCamera /></el-icon>
            </div>
          </template>
        </el-image>
        <div class="dialog-poster-fallback" v-else>
          <el-icon :size="40"><VideoCamera /></el-icon>
        </div>
        <div class="media-detail">
          <h4>{{ media.title }}</h4>
          <p>{{ media.year || '未知年份' }} · {{ media.media_type === 'tv' ? '剧集' : '电影' }}</p>
          <el-tag size="small">{{ media.tmdb_id ? `TMDB ${media.tmdb_id}` : '' }}</el-tag>
        </div>
      </div>
      <el-alert
        title="订阅后，系统将通过 NextFind 自动搜索资源并追更"
        type="info"
        :closable="false"
        show-icon
        style="margin-top: 16px"
      />
    </div>

    <template #footer>
      <el-button @click="visible = false" :disabled="loading">取消</el-button>
      <el-button type="primary" @click="handleConfirm" :loading="loading">
        确认订阅
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoCamera } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  media: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const visible = ref(props.modelValue)
const loading = ref(false)

watch(() => props.modelValue, (val) => {
  visible.value = val
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

function handleClose() {
  loading.value = false
}

async function handleConfirm() {
  if (!props.media) return
  loading.value = true
  emit('confirm', props.media, (success) => {
    loading.value = false
    if (success) {
      visible.value = false
    }
  })
}
</script>

<style scoped>
.media-info {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.dialog-poster {
  width: 100px;
  height: 140px;
  border-radius: 6px;
  flex-shrink: 0;
}

.dialog-poster-fallback {
  width: 100px;
  height: 140px;
  border-radius: 6px;
  background: #f5f5f5;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
  flex-shrink: 0;
}

.media-detail h4 {
  font-size: 16px;
  margin-bottom: 6px;
  color: #303133;
}

.media-detail p {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}
</style>
