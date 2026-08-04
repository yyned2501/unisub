<script setup lang="ts">
import { useSettingsForm } from '@/composables/useSettingsForm'
import { getTaskStatus, updateTaskConfig } from '@/service/api/tasks'

defineOptions({ name: 'TaskSettings' })

const { config, loading, saving, saveConfig } = useSettingsForm({
  defaults: {
    interval_minutes: 60,
    light_interval_minutes: 10,
    sync_interval_minutes: 60,
    tmdb_interval_minutes: 60,
    mp_supplement_enabled: true,
    auto_sync_enabled: true,
  },
  fetch: async () => (await getTaskStatus()).config,
  persist: (c) => updateTaskConfig({ ...c }),
  loadErrorText: '加载任务配置失败',
  saveSuccessText: '任务配置已保存',
  saveErrorText: '保存任务配置失败',
})
</script>

<template>
  <div>
    <h2 class="text-lg font-bold mb-4">定时任务</h2>

    <n-card :bordered="true" size="small" style="max-width: 480px">
      <n-spin :show="loading">
        <div class="flex flex-col gap-5">
          <div class="flex items-center justify-between">
            <label class="text-xs opacity-50 font-medium">启用自动同步</label>
            <n-switch v-model:value="config.auto_sync_enabled" />
          </div>

          <div class="flex items-center justify-between">
            <label class="text-xs opacity-50 font-medium">MP 补充搜索</label>
            <n-switch v-model:value="config.mp_supplement_enabled" />
          </div>

          <div class="flex flex-col gap-1.5">
            <label class="text-xs opacity-50 font-medium">全量扫描间隔</label>
            <n-input-number
              v-model:value="config.interval_minutes"
              :min="5"
              :max="1440"
              :step="5"
              size="small"
              style="width: 140px"
            >
              <template #suffix><span class="text-xs opacity-40">分钟</span></template>
            </n-input-number>
          </div>

          <div class="flex flex-col gap-1.5">
            <label class="text-xs opacity-50 font-medium">轻量刷新间隔</label>
            <n-input-number
              v-model:value="config.light_interval_minutes"
              :min="1"
              :max="120"
              :step="1"
              size="small"
              style="width: 140px"
            >
              <template #suffix><span class="text-xs opacity-40">分钟</span></template>
            </n-input-number>
          </div>

          <div class="flex flex-col gap-1.5">
            <label class="text-xs opacity-50 font-medium">NF 订阅同步间隔</label>
            <n-input-number
              v-model:value="config.sync_interval_minutes"
              :min="5"
              :max="1440"
              :step="5"
              size="small"
              style="width: 140px"
            >
              <template #suffix><span class="text-xs opacity-40">分钟</span></template>
            </n-input-number>
          </div>

          <div class="flex flex-col gap-1.5">
            <label class="text-xs opacity-50 font-medium">TMDB 增量刷新间隔</label>
            <n-input-number
              v-model:value="config.tmdb_interval_minutes"
              :min="5"
              :max="1440"
              :step="5"
              size="small"
              style="width: 140px"
            >
              <template #suffix><span class="text-xs opacity-40">分钟</span></template>
            </n-input-number>
          </div>

          <div class="flex pt-2" style="border-top: 1px solid var(--n-border-color)">
            <n-button size="small" type="primary" :loading="saving" @click="saveConfig">
              <template #icon><i class="ri-save-line"></i></template>
              保存配置
            </n-button>
          </div>
        </div>
      </n-spin>
    </n-card>
  </div>
</template>