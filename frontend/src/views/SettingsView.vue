<template>
  <div class="settings-view">
    <el-row :gutter="20">
      <!-- 平台配置 -->
      <el-col :span="16">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>平台配置</span>
              <el-button type="primary" size="small" @click="openAddDialog">
                添加平台
              </el-button>
            </div>
          </template>

          <div v-loading="loading.platforms">
            <div v-if="platforms.length === 0" class="empty-hint">
              <el-empty description="暂无平台配置，点击「添加平台」开始" :image-size="80" />
            </div>

            <div v-for="p in platforms" :key="p.id" class="platform-item">
              <div class="platform-main" @click="openEditDialog(p)">
                <div class="platform-info">
                  <h4 class="platform-name">
                    {{ platformDisplayName(p.name) }}
                    <el-switch
                      v-model="p.enabled"
                      size="small"
                      @click.stop
                      @change="(val) => handleToggle(p, val)"
                    />
                  </h4>
                  <p class="platform-url">{{ p.base_url }}</p>
                  <p class="platform-key">API Key: {{ maskKey(p.api_key) }}</p>
                </div>
                <div class="platform-status-area">
                  <PlatformStatus
                    :platform="p"
                    :connected="p.enabled"
                    :quota="p.name === 'nextfind' ? nfQuota : null"
                  />
                </div>
              </div>
              <div class="platform-actions">
                <el-button size="small" :loading="testingId === p.id" @click.stop="handleTest(p)">
                  测试连接
                </el-button>
                <el-button size="small" type="primary" @click.stop="openEditDialog(p)">
                  编辑
                </el-button>
                <el-popconfirm
                  title="确定删除此平台配置？"
                  confirm-button-text="确定"
                  cancel-button-text="取消"
                  @confirm="handleDelete(p.id)"
                >
                  <template #reference>
                    <el-button size="small" type="danger">删除</el-button>
                  </template>
                </el-popconfirm>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 任务配置 -->
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>
            <span>定时任务配置</span>
          </template>

          <el-form label-width="100px" size="small" v-loading="loading.taskConfig">
            <el-form-item label="轮询间隔（秒）">
              <el-input-number
                v-model="taskConfig.interval"
                :min="60"
                :max="86400"
                :step="60"
              />
            </el-form-item>
            <el-form-item label="启用 MP 补充">
              <el-switch v-model="taskConfig.mp_enabled" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingTask" @click="handleSaveTaskConfig">
                保存配置
              </el-button>
              <el-button :loading="triggering" @click="handleTrigger">
                手动触发一次
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <!-- 添加/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingPlatform ? '编辑平台' : '添加平台'"
      width="500px"
      :close-on-click-modal="false"
      @close="resetForm"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-width="80px"
      >
        <el-form-item label="平台名称" prop="name">
          <el-select v-model="form.name" placeholder="选择平台" :disabled="!!editingPlatform">
            <el-option label="NextFind" value="nextfind" />
            <el-option label="MoviePilot" value="moviepilot" />
          </el-select>
        </el-form-item>
        <el-form-item label="地址" prop="base_url">
          <el-input v-model="form.base_url" placeholder="http://192.168.31.10:8092" />
        </el-form-item>
        <el-form-item label="API Key" prop="api_key">
          <el-input
            v-model="form.api_key"
            placeholder="输入 API Key"
            show-password
            type="password"
          />
        </el-form-item>
        <el-form-item label="启用" prop="enabled">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingForm" @click="handleSavePlatform">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getPlatforms,
  createPlatform,
  updatePlatform,
  deletePlatform,
  testPlatform,
} from '../api/platforms'
import { getTaskStatus, triggerTask, updateTaskConfig } from '../api/tasks'
import { getNextFindQuota } from '../api/dashboard'
import PlatformStatus from '../components/PlatformStatus.vue'

const platforms = ref([])
const nfQuota = ref(null)
const testingId = ref(null)
const triggering = ref(false)
const savingTask = ref(false)

const loading = reactive({
  platforms: false,
  taskConfig: false,
})

// 任务配置
const taskConfig = reactive({
  interval: 1800,
  mp_enabled: true,
})

// 表单
const dialogVisible = ref(false)
const editingPlatform = ref(null)
const savingForm = ref(false)
const formRef = ref(null)

const form = reactive({
  name: '',
  base_url: '',
  api_key: '',
  enabled: true,
})

const formRules = {
  name: [{ required: true, message: '请选择平台', trigger: 'change' }],
  base_url: [{ required: true, message: '请输入 API 地址', trigger: 'blur' }],
  api_key: [{ required: true, message: '请输入 API Key', trigger: 'blur' }],
}

function platformDisplayName(name) {
  const map = { nextfind: 'NextFind', moviepilot: 'MoviePilot' }
  return map[name] || name
}

function maskKey(key) {
  if (!key) return '未设置'
  if (key.length <= 8) return '*'.repeat(key.length)
  return key.slice(0, 4) + '****' + key.slice(-4)
}

async function loadPlatforms() {
  loading.platforms = true
  try {
    const { data } = await getPlatforms()
    platforms.value = Array.isArray(data) ? data : []
  } finally {
    loading.platforms = false
  }
}

async function loadTaskConfig() {
  loading.taskConfig = true
  try {
    const { data } = await getTaskStatus()
    if (data) {
      taskConfig.interval = data.interval || 1800
      taskConfig.mp_enabled = data.mp_enabled !== false
    }
  } catch {
    // 使用默认值
  } finally {
    loading.taskConfig = false
  }
}

async function loadNfQuota() {
  try {
    const { data } = await getNextFindQuota()
    nfQuota.value = data?.remaining ?? data?.quota ?? null
  } catch {
    nfQuota.value = null
  }
}

function openAddDialog() {
  editingPlatform.value = null
  form.name = ''
  form.base_url = ''
  form.api_key = ''
  form.enabled = true
  dialogVisible.value = true
}

function openEditDialog(platform) {
  editingPlatform.value = platform
  form.name = platform.name
  form.base_url = platform.base_url
  form.api_key = platform.api_key
  form.enabled = platform.enabled
  dialogVisible.value = true
}

function resetForm() {
  editingPlatform.value = null
  formRef.value?.resetFields()
}

async function handleSavePlatform() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  savingForm.value = true
  try {
    const payload = { ...form }
    if (editingPlatform.value) {
      await updatePlatform(editingPlatform.value.id, payload)
      ElMessage.success('平台已更新')
    } else {
      await createPlatform(payload)
      ElMessage.success('平台已添加')
    }
    dialogVisible.value = false
    await loadPlatforms()
  } finally {
    savingForm.value = false
  }
}

async function handleTest(platform) {
  testingId.value = platform.id
  try {
    await testPlatform(platform.id)
    ElMessage.success(`${platformDisplayName(platform.name)} 连接成功`)
  } catch {
    // 错误已由拦截器处理
  } finally {
    testingId.value = null
  }
}

async function handleToggle(platform, enabled) {
  try {
    await updatePlatform(platform.id, { ...platform, enabled })
    ElMessage.success(`${platformDisplayName(platform.name)} 已${enabled ? '启用' : '禁用'}`)
  } catch {
    platform.enabled = !enabled // 回滚
  }
}

async function handleDelete(id) {
  try {
    await deletePlatform(id)
    ElMessage.success('平台已删除')
    platforms.value = platforms.value.filter((p) => p.id !== id)
  } catch {
    // 错误已由拦截器处理
  }
}

async function handleSaveTaskConfig() {
  savingTask.value = true
  try {
    await updateTaskConfig({
      interval: taskConfig.interval,
      mp_enabled: taskConfig.mp_enabled,
    })
    ElMessage.success('任务配置已保存')
  } finally {
    savingTask.value = false
  }
}

async function handleTrigger() {
  triggering.value = true
  try {
    await triggerTask()
    ElMessage.success('已触发编排任务')
  } finally {
    triggering.value = false
  }
}

onMounted(() => {
  loadPlatforms()
  loadTaskConfig()
  loadNfQuota()
})
</script>

<style scoped>
.settings-view {
  max-width: 1200px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.platform-item {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  transition: border-color 0.2s;
}

.platform-item:hover {
  border-color: #409eff;
}

.platform-main {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  cursor: pointer;
}

.platform-info {
  flex: 1;
}

.platform-name {
  font-size: 15px;
  color: #303133;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.platform-url {
  font-size: 13px;
  color: #909399;
  margin-bottom: 4px;
}

.platform-key {
  font-size: 12px;
  color: #c0c4cc;
  font-family: monospace;
}

.platform-status-area {
  margin-left: 16px;
}

.platform-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.empty-hint {
  padding: 20px 0;
}
</style>
