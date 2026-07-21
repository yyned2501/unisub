<script setup lang="ts">
import type { EmbyScanStatus } from '@/types'

defineProps<{
  scanStatus: EmbyScanStatus | null
}>()
</script>

<template>
  <n-card v-if="scanStatus && scanStatus.running" size="small" :bordered="true" class="mb-4">
    <div class="flex flex-col gap-2">
      <div class="flex items-center justify-between text-xs">
        <div class="flex items-center gap-2">
          <n-spin size="small" />
          <span class="opacity-70">{{ scanStatus.step_name }}</span>
          <span v-if="scanStatus.current_item" class="opacity-40"
            >({{ scanStatus.current_item }}/{{ scanStatus.total_items }})</span
          >
        </div>
        <span class="font-medium">{{ Math.round(scanStatus.progress) }}%</span>
      </div>
      <n-progress
        type="line"
        :percentage="Math.round(scanStatus.progress)"
        :height="16"
        :processing="true"
        color="#3b82f6"
      />
    </div>
  </n-card>
</template>
