<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { NButton, NCard, NSwitch, NInput, NSelect, NSpin } from 'naive-ui'
import { getAiConfig, updateAiConfig, fetchAIModels } from '@/service/api/ai'
import { msg } from '@/utils/message'
import type { AiConfig } from '@/types'

defineOptions({ name: 'AiSettings' })

const loading = ref(false)
const saving = ref(false)
const config = reactive<AiConfig>({
  ai_assist_enabled: false,
  ai_api_base: '',
  ai_api_key: '',
  ai_model: 'gpt-4o-mini',
  ai_enable_search: false,
})
const aiModels = ref<{ value: string; label: string }[]>([])
const fetchingModels = ref(false)

async function load() {
  loading.value = true
  try {
    const response = await getAiConfig()
    const c = response.config
    config.ai_assist_enabled = Boolean(c.ai_assist_enabled)
    config.ai_api_base = String(c.ai_api_base || '')
    config.ai_api_key = String(c.ai_api_key || '')
    config.ai_model = String(c.ai_model || 'gpt-4o-mini')
    config.ai_enable_search = Boolean(c.ai_enable_search)
  } catch (error: unknown) {
    msg.error(
      (error as import('axios').AxiosError<{ detail?: string }>)?.response?.data?.detail || 'AI 配置加载失败'
    )
  } finally {
    loading.value = false
  }
}

async function fetchModels() {
  const base = config.ai_api_base?.trim()
  const key = config.ai_api_key?.trim()
  if (!base || !key) return
  fetchingModels.value = true
  try {
    const res = await fetchAIModels({ api_base: base, api_key: key })
    aiModels.value = (res.models || []).map((m: { id: string }) => ({
      value: m.id,
      label: m.id,
    }))
  } catch {
    aiModels.value = []
  } finally {
    fetchingModels.value = false
  }
}

watch(
  () => [config.ai_api_base, config.ai_api_key] as const,
  ([base, key]) => {
    if (base?.trim() && key?.trim()) {
      fetchModels()
    } else {
      aiModels.value = []
    }
  },
  { immediate: false }
)

async function handleSave() {
  saving.value = true
  try {
    await updateAiConfig({
      config: { ...config },
    })
    msg.success('AI 配置已保存')
  } catch (error: unknown) {
    msg.error((error as import('axios').AxiosError<{ detail?: string }>)?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => load())
</script>

<template>
  <div>
    <h2 class="text-lg font-bold mb-4">AI 辅助识别</h2>

    <n-spin :show="loading">
      <n-card title="AI 配置" size="small" :bordered="true" class="mb-4">
        <div class="flex flex-col gap-4">
          <div class="flex items-center justify-between">
            <label class="text-xs opacity-50 font-medium">启用 AI 辅助识别</label>
            <n-switch v-model:value="config.ai_assist_enabled" />
          </div>
          <div class="flex items-center justify-between">
            <label class="text-xs opacity-50 font-medium">联网搜索（Qwen 专用，会减慢响应速度）</label>
            <n-switch v-model:value="config.ai_enable_search" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs opacity-50 font-medium">API 地址</label>
            <n-input
              v-model:value="config.ai_api_base"
              placeholder="https://api.openai.com"
              size="small"
              style="max-width: 400px"
            />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs opacity-50 font-medium">API Key</label>
            <n-input
              v-model:value="config.ai_api_key"
              placeholder="sk-..."
              size="small"
              type="password"
              show-password-on="click"
              style="max-width: 400px"
            />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs opacity-50 font-medium">模型名称</label>
            <div class="flex items-center gap-2">
              <n-select
                v-model:value="config.ai_model"
                :options="aiModels"
                :loading="fetchingModels"
                :placeholder="aiModels.length ? '选择模型' : '填入 API 地址和 Key 后自动获取'"
                filterable
                tag
                clearable
                size="small"
                style="max-width: 300px"
              />
              <n-button
                size="tiny"
                quaternary
                :loading="fetchingModels"
                :disabled="!config.ai_api_base?.trim() || !config.ai_api_key?.trim()"
                @click="fetchModels"
              >
                <template #icon><i class="ri-refresh-line"></i></template>
              </n-button>
            </div>
          </div>
        </div>
      </n-card>

      <n-button type="primary" :loading="saving" @click="handleSave">
        <template #icon><i class="ri-save-line"></i></template>
        保存配置
      </n-button>
    </n-spin>
  </div>
</template>