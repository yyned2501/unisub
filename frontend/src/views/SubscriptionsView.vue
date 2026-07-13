<template>
  <div class="subscriptions-view">
    <!-- 筛选 & 操作栏 -->
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="filters">
          <el-select v-model="filterType" placeholder="类型" style="width: 120px" clearable>
            <el-option label="全部" value="all" />
            <el-option label="电影" value="movie" />
            <el-option label="剧集" value="tv" />
          </el-select>
          <el-select v-model="filterStatus" placeholder="状态" style="width: 140px" clearable>
            <el-option label="全部" value="all" />
            <el-option label="活跃" value="active" />
            <el-option label="缺集中" value="missing" />
            <el-option label="已完成" value="completed" />
          </el-select>
          <el-input
            v-model="searchText"
            placeholder="搜索标题..."
            clearable
            style="width: 200px"
            :prefix-icon="Search"
          />
        </div>
        <div class="actions">
          <el-button :loading="syncing" @click="handleSync">
            <el-icon><Refresh /></el-icon>
            同步
          </el-button>
          <el-button type="warning" :loading="triggering" @click="handleTriggerMP">
            <el-icon><Connection /></el-icon>
            触发 MP 补充
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 订阅列表 -->
    <el-card shadow="never" v-loading="loading">
      <el-table :data="filteredList" stripe style="width: 100%">
        <el-table-column label="海报" width="80">
          <template #default="{ row }">
            <el-image
              :src="row.poster_url"
              fit="cover"
              style="width: 48px; height: 64px; border-radius: 4px"
              v-if="row.poster_url"
            >
              <template #error>
                <div class="table-poster-fallback">
                  <el-icon :size="20"><VideoCamera /></el-icon>
                </div>
              </template>
            </el-image>
            <div class="table-poster-fallback" v-else>
              <el-icon :size="20"><VideoCamera /></el-icon>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column label="类型" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.media_type === 'tv' ? 'primary' : 'success'">
              {{ row.media_type === 'tv' ? '剧集' : '电影' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="NF 状态" width="100">
          <template #default="{ row }">
            <StatusBadge :status="row.nf_status" type="nf" />
          </template>
        </el-table-column>
        <el-table-column label="缺集数" width="80" align="center">
          <template #default="{ row }">
            <span :class="{ 'missing-count': row.nf_missing_eps > 0 }">
              {{ row.nf_missing_eps ?? 0 }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="已完成" width="80" align="center">
          <template #default="{ row }">
            <el-icon v-if="row.completed" style="color: #67c23a"><CircleCheckFilled /></el-icon>
            <span v-else style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="年份" width="70">
          <template #default="{ row }">
            {{ row.year || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="handleRefresh(row)">
              刷新
            </el-button>
            <el-popconfirm
              title="确定取消订阅？"
              confirm-button-text="确定"
              cancel-button-text="取消"
              @confirm="handleDelete(row)"
            >
              <template #reference>
                <el-button size="small" text type="danger">取消订阅</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!loading && list.length === 0" class="empty-hint">
        <el-empty description="暂无订阅" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Refresh, Connection, VideoCamera, CircleCheckFilled } from '@element-plus/icons-vue'
import { getSubscriptions, deleteSubscription, syncSubscriptions } from '../api/subscriptions'
import { triggerTask } from '../api/tasks'
import StatusBadge from '../components/StatusBadge.vue'

const list = ref([])
const loading = ref(false)
const syncing = ref(false)
const triggering = ref(false)

// 筛选
const filterType = ref('all')
const filterStatus = ref('all')
const searchText = ref('')

const filteredList = computed(() => {
  let items = list.value

  // 类型筛选
  if (filterType.value && filterType.value !== 'all') {
    items = items.filter((i) => i.media_type === filterType.value)
  }

  // 状态筛选
  if (filterStatus.value && filterStatus.value !== 'all') {
    if (filterStatus.value === 'active') {
      items = items.filter((i) => i.nf_status === 'active')
    } else if (filterStatus.value === 'missing') {
      items = items.filter((i) => i.nf_status === 'missing_fill' || i.nf_missing_eps > 0)
    } else if (filterStatus.value === 'completed') {
      items = items.filter((i) => i.completed || i.nf_status === 'completed')
    }
  }

  // 标题搜索
  if (searchText.value.trim()) {
    const kw = searchText.value.trim().toLowerCase()
    items = items.filter((i) => i.title?.toLowerCase().includes(kw))
  }

  return items
})

async function loadList() {
  loading.value = true
  try {
    const { data } = await getSubscriptions()
    list.value = Array.isArray(data) ? data : []
  } finally {
    loading.value = false
  }
}

async function handleSync() {
  syncing.value = true
  try {
    await syncSubscriptions()
    ElMessage.success('同步完成')
    await loadList()
  } finally {
    syncing.value = false
  }
}

async function handleTriggerMP() {
  triggering.value = true
  try {
    await triggerTask()
    ElMessage.success('已触发 MoviePilot 补充任务')
  } finally {
    triggering.value = false
  }
}

async function handleDelete(row) {
  try {
    await deleteSubscription(row.id)
    ElMessage.success(`已取消订阅「${row.title}」`)
    list.value = list.value.filter((i) => i.id !== row.id)
  } catch {
    // 错误已由拦截器处理
  }
}

function handleRefresh(row) {
  ElMessage.info(`刷新「${row.title}」的状态（功能开发中）`)
}

onMounted(() => {
  loadList()
})
</script>

<style scoped>
.subscriptions-view {
  max-width: 1200px;
}

.toolbar-card {
  margin-bottom: 20px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.filters {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.actions {
  display: flex;
  gap: 8px;
}

.missing-count {
  color: #e6a23c;
  font-weight: 600;
}

.table-poster-fallback {
  width: 48px;
  height: 64px;
  border-radius: 4px;
  background: #f5f5f5;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
}

.empty-hint {
  padding: 40px 0;
}
</style>
