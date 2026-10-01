<script setup lang="ts">
import { ref, watch } from 'vue'
import { NButton, NCard, NSwitch, NInput, NInputNumber, NSelect, NSpin } from 'naive-ui'
import { useSettingsForm } from '@/composables/useSettingsForm'
import { getAiConfig, updateAiConfig, fetchAIModels } from '@/service/api/ai'
import type { AiConfig } from '@/types'

defineOptions({ name: 'AiSettings' })

const { config, loading, saving, saveConfig } = useSettingsForm<AiConfig>({
  defaults: {
    ai_assist_enabled: false,
    ai_api_base: '',
    ai_api_key: '',
    ai_model: 'gpt-4o-mini',
    ai_enable_search: false,
    jev_decision_enabled: false,
    jev_decision_shadow: true,
    jev_api_base: 'https://api.typesafe.ai',
    jev_api_key: '',
    jev_model: 'jev-1.13.0',
    jev_same_work_threshold: 0.5,
  },
  fetch: async () => {
    const response = await getAiConfig()
    const c = response.config
    return {
      ai_assist_enabled: Boolean(c.ai_assist_enabled),
      ai_api_base: String(c.ai_api_base || ''),
      ai_api_key: String(c.ai_api_key || ''),
      ai_model: String(c.ai_model || 'gpt-4o-mini'),
      ai_enable_search: Boolean(c.ai_enable_search),
      jev_decision_enabled: Boolean(c.jev_decision_enabled),
      jev_decision_shadow: Boolean(c.jev_decision_shadow ?? true),
      jev_api_base: String(c.jev_api_base || 'https://api.typesafe.ai'),
      jev_api_key: String(c.jev_api_key || ''),
      jev_model: String(c.jev_model || 'jev-1.13.0'),
      jev_same_work_threshold: Number(c.jev_same_work_threshold ?? 0.5),
    }
  },
  persist: (c) => updateAiConfig({ config: { ...c } }),
  saveSuccessText: 'AI 配置已保存',
})

const aiModels = ref<{ value: string; label: string }[]>([])
const fetchingModels = ref(false)

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

      <n-card title="JEV 采纳闸门（自动订阅兜底判定）" size="small" :bordered="true" class="mb-4">
        <div class="flex flex-col gap-4">
          <div class="flex items-center justify-between">
            <label class="text-xs opacity-50 font-medium">启用采纳闸门（默认关）</label>
            <n-switch v-model:value="config.jev_decision_enabled" />
          </div>
          <div class="flex items-center justify-between">
            <label class="text-xs opacity-50 font-medium">
              影子模式（只记录 JEV 判定与实际采纳的差异，不影响下单）
            </label>
            <n-switch v-model:value="config.jev_decision_shadow" />
          </div>
          <div class="text-xs opacity-40 leading-relaxed">
            仅复核启发式兜底（阶段 4/5）选中的候选：same_work 低于阈值才放弃订阅；
            JEV 不可用/超时一律回退旧启发式，不改变下单行为。
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs opacity-50 font-medium">API 地址</label>
            <n-input
              v-model:value="config.jev_api_base"
              placeholder="https://api.typesafe.ai"
              size="small"
              style="max-width: 400px"
            />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs opacity-50 font-medium">API Key（留空则用后端 .env 的 UNISUB_JEV_API_KEY）</label>
            <n-input
              v-model:value="config.jev_api_key"
              placeholder="ts-..."
              size="small"
              type="password"
              show-password-on="click"
              style="max-width: 400px"
            />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs opacity-50 font-medium">模型（须 pin 到具体版本，禁用 jev-latest）</label>
            <n-input
              v-model:value="config.jev_model"
              placeholder="jev-1.13.0"
              size="small"
              style="max-width: 400px"
            />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs opacity-50 font-medium">same_work 拦截阈值（0.5 = Phase 4A 标定值）</label>
            <n-input-number
              v-model:value="config.jev_same_work_threshold"
              :min="0.05"
              :max="1"
              :step="0.05"
              :precision="2"
              size="small"
              style="max-width: 200px"
            />
          </div>
        </div>
      </n-card>

      <n-button type="primary" :loading="saving" @click="saveConfig">
        <template #icon><i class="ri-save-line"></i></template>
        保存配置
      </n-button>
    </n-spin>
  </div>
</template>