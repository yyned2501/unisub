<script setup>
import { ref, reactive, onMounted } from 'vue'
import { getTaskStatus, triggerTask, updateTaskConfig } from '@/service/api/tasks'

defineOptions({ name: 'TaskSettings' })

const loading = ref(false)
const saving = ref(false)
const triggering = ref(false)

const config = reactive({
  interval: 1800,
  mp_enabled: true,
})

function formatInterval(seconds) {
  if (seconds < 60) return `${seconds}秒`
  if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`
  return `${(seconds / 3600).toFixed(1)}小时`
}

async function load() {
  loading.value = true
  try {
    const { data } = await getTaskStatus()
    if (data) {
      config.interval = data.interval || 1800
      config.mp_enabled = data.mp_enabled !== false
    }
  } catch {} finally { loading.value = false }
}

async function handleSave() {
  saving.value = true
  try {
    await updateTaskConfig({ interval: config.interval, mp_enabled: config.mp_enabled })
    window.$message?.success('任务配置已保存')
  } catch {} finally { saving.value = false }
}

async function handleTrigger() {
  triggering.value = true
  try {
    await triggerTask()
    window.$message?.success('已触发编排任务')
  } catch {} finally { triggering.value = false }
}

onMounted(() => load())
</script>

<template>
  <div>
    <h2 class="text-lg font-bold mb-4">定时任务</h2>

    <n-card :bordered="true" size="small" style="max-width: 480px;">
      <n-spin :show="loading">
        <div class="flex flex-col gap-5">
          <div class="flex flex-col gap-1.5">
            <label class="text-xs opacity-50 font-medium">轮询间隔</label>
            <div class="flex items-center gap-2.5">
              <n-input-number v-model:value="config.interval" :min="60" :max="86400" :step="60" size="small" style="width: 140px;">
                <template #suffix><span class="text-xs opacity-40">秒</span></template>
              </n-input-number>
              <span class="text-xs opacity-50">{{ formatInterval(config.interval) }}</span>
            </div>
          </div>

          <div class="flex items-center justify-between">
            <label class="text-xs opacity-50 font-medium">启用 MP 补充</label>
            <n-switch v-model:value="config.mp_enabled" />
          </div>

          <div class="flex gap-2 pt-2" style="border-top: 1px solid var(--n-border-color);">
            <n-button size="small" type="primary" :loading="saving" @click="handleSave">
              <template #icon><i class="ri-save-line"></i></template>
              保存配置
            </n-button>
            <n-button size="small" :loading="triggering" @click="handleTrigger">
              <template #icon><i class="ri-flashlight-line"></i></template>
              手动触发
            </n-button>
          </div>
        </div>
      </n-spin>
    </n-card>
  </div>
</template>
