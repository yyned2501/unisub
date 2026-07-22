<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { getTaskStatus, updateTaskConfig } from '@/service/api/tasks'
import { msg } from '@/utils/message'

defineOptions({ name: 'TaskSettings' })

const loading = ref(false)
const saving = ref(false)

const config = reactive({
  interval: 1800,
})

function formatInterval(seconds: number): string {
  if (seconds < 60) return `${seconds}秒`
  if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`
  return `${(seconds / 3600).toFixed(1)}小时`
}

async function load() {
  loading.value = true
  try {
    const data = await getTaskStatus()
    if (data) {
      config.interval = data.config?.interval || 1800
    }
  } catch {
    msg.error('加载任务配置失败')
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saving.value = true
  try {
    await updateTaskConfig({
      interval: config.interval,
    })
    msg.success('任务配置已保存')
  } catch {
    msg.error('保存任务配置失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => load())
</script>

<template>
  <div>
    <h2 class="text-lg font-bold mb-4">定时任务</h2>

    <n-card :bordered="true" size="small" style="max-width: 480px">
      <n-spin :show="loading">
        <div class="flex flex-col gap-5">
          <div class="flex flex-col gap-1.5">
            <label class="text-xs opacity-50 font-medium">全量扫描间隔</label>
            <div class="flex items-center gap-2.5">
              <n-input-number
                v-model:value="config.interval"
                :min="60"
                :max="86400"
                :step="60"
                size="small"
                style="width: 140px"
              >
                <template #suffix><span class="text-xs opacity-40">秒</span></template>
              </n-input-number>
              <span class="text-xs opacity-50">{{ formatInterval(config.interval) }}</span>
            </div>
          </div>

          <div class="flex pt-2" style="border-top: 1px solid var(--n-border-color)">
            <n-button size="small" type="primary" :loading="saving" @click="handleSave">
              <template #icon><i class="ri-save-line"></i></template>
              保存配置
            </n-button>
          </div>
        </div>
      </n-spin>
    </n-card>
  </div>
</template>
