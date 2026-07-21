<script setup>
import { formatTime } from '@/utils/format'

defineProps({
  autoFillEnabled: { type: Boolean, default: false },
  autoFillLastRun: { type: String, default: null },
  autoFillProgress: { type: Object, default: null },
})
</script>

<template>
  <n-card v-if="autoFillEnabled" size="small" :bordered="true" class="mb-4">
    <div class="flex flex-col gap-2">
      <div class="flex items-center justify-between text-xs">
        <div class="flex items-center gap-2">
          <n-spin v-if="autoFillProgress && autoFillProgress.total > 0" size="small" />
          <span class="opacity-70">自动补缺集</span>
          <span v-if="autoFillProgress && autoFillProgress.total > 0" class="opacity-40">
            ({{ autoFillProgress.current }}/{{ autoFillProgress.total }})
          </span>
          <span v-else class="opacity-40">等待运行...</span>
        </div>
        <span v-if="autoFillProgress && autoFillProgress.total > 0" class="font-medium">
          {{ Math.round(autoFillProgress.current / autoFillProgress.total * 100) }}%
        </span>
      </div>
      <n-progress
        v-if="autoFillProgress && autoFillProgress.total > 0"
        type="line"
        :percentage="Math.round(autoFillProgress.current / autoFillProgress.total * 100)"
        :height="16"
        :processing="true"
        color="#8b5cf6"
      />
      <div class="text-xs opacity-40 text-right">上次运行: {{ formatTime(autoFillLastRun) }}</div>
    </div>
  </n-card>
</template>