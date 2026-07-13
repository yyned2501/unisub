<template>
  <div class="dashboard-view">
    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="8">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-inner">
            <div class="stat-icon stat-icon--primary">
              <el-icon :size="28"><Collection /></el-icon>
            </div>
            <div class="stat-body">
              <p class="stat-label">总订阅数</p>
              <p class="stat-value">{{ stats.total_subscriptions }}</p>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-inner">
            <div class="stat-icon stat-icon--warning">
              <el-icon :size="28"><WarningFilled /></el-icon>
            </div>
            <div class="stat-body">
              <p class="stat-label">缺集数</p>
              <p class="stat-value">{{ stats.missing_count }}</p>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-inner">
            <div class="stat-icon stat-icon--success">
              <el-icon :size="28"><CircleCheckFilled /></el-icon>
            </div>
            <div class="stat-body">
              <p class="stat-label">已完成数</p>
              <p class="stat-value">{{ stats.completed_count }}</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 平台状态 + 活动日志 -->
    <el-row :gutter="20" class="content-row">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>平台状态</span>
              <el-button size="small" :loading="loading.platforms" @click="loadPlatformData">
                刷新
              </el-button>
            </div>
          </template>
          <el-table :data="platforms" stripe size="small" v-loading="loading.platforms">
            <el-table-column prop="name" label="平台" width="120">
              <template #default="{ row }">
                <span style="text-transform: capitalize">{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="base_url" label="地址" min-width="180" show-overflow-tooltip />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <PlatformStatus
                  :platform="row"
                  :connected="row.enabled"
                  :quota="row.name === 'nextfind' ? nfQuota : null"
                />
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!loading.platforms && platforms.length === 0" class="empty-hint">
            暂无平台配置，前往
            <router-link to="/settings">设置</router-link>
            添加
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>最近活动</span>
              <el-button size="small" :loading="loading.activities" @click="loadActivities">
                刷新
              </el-button>
            </div>
          </template>
          <el-table :data="activities" stripe size="small" v-loading="loading.activities" max-height="320">
            <el-table-column prop="action" label="操作" width="120">
              <template #default="{ row }">
                <el-tag size="small" :type="actionTagType(row.action)">
                  {{ actionLabel(row.action) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="message" label="详情" min-width="180" show-overflow-tooltip />
            <el-table-column prop="created_at" label="时间" width="160">
              <template #default="{ row }">
                {{ formatTime(row.created_at) }}
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!loading.activities && activities.length === 0" class="empty-hint">
            暂无活动记录
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Collection, WarningFilled, CircleCheckFilled } from '@element-plus/icons-vue'
import { getStats, getPlatformStatus, getActivities, getNextFindQuota } from '../api/dashboard'
import PlatformStatus from '../components/PlatformStatus.vue'

const stats = reactive({
  total_subscriptions: 0,
  missing_count: 0,
  completed_count: 0,
})

const platforms = ref([])
const activities = ref([])
const nfQuota = ref(null)

const loading = reactive({
  stats: false,
  platforms: false,
  activities: false,
})

/** 操作标签类型映射 */
function actionTagType(action) {
  const map = {
    subscribe: 'success',
    unsubscribe: 'danger',
    mp_search: 'warning',
    mp_downloaded: '',
    sync: 'info',
    system: 'info',
  }
  return map[action] || 'info'
}

/** 操作中文标签 */
function actionLabel(action) {
  const map = {
    subscribe: '订阅',
    unsubscribe: '取消订阅',
    mp_search: 'MP 搜索',
    mp_downloaded: 'MP 下载',
    sync: '同步',
    system: '系统',
  }
  return map[action] || action
}

/** 格式化时间 */
function formatTime(ts) {
  if (!ts) return '-'
  const d = new Date(ts)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function loadStats() {
  loading.stats = true
  try {
    const { data } = await getStats()
    Object.assign(stats, data)
  } finally {
    loading.stats = false
  }
}

async function loadPlatformData() {
  loading.platforms = true
  try {
    const [platformRes, quotaRes] = await Promise.allSettled([
      getPlatformStatus(),
      getNextFindQuota(),
    ])
    if (platformRes.status === 'fulfilled') {
      platforms.value = platformRes.value.data
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
    activities.value = data
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

<style scoped>
.dashboard-view {
  max-width: 1200px;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  border-radius: 8px;
}

.stat-inner {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-icon--primary {
  background: #ecf5ff;
  color: #409eff;
}

.stat-icon--warning {
  background: #fdf6ec;
  color: #e6a23c;
}

.stat-icon--success {
  background: #f0f9eb;
  color: #67c23a;
}

.stat-body {
  flex: 1;
}

.stat-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
}

.content-row {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.empty-hint {
  text-align: center;
  padding: 24px;
  color: #909399;
  font-size: 14px;
}

.empty-hint a {
  color: #409eff;
}
</style>
