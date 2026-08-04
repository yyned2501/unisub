<script setup lang="ts">
defineProps<{
  running: boolean
  progress: number
  stepName: string
  currentItem?: string
  totalItems?: number
}>()
</script>

<template>
  <n-card v-if="running" size="small" :bordered="true" class="mb-4">
    <div class="flex flex-col gap-2">
      <div class="flex items-center justify-between text-xs">
        <div class="flex items-center gap-2">
          <n-spin size="small" />
          <span class="opacity-70">{{ stepName }}</span>
          <span v-if="currentItem && totalItems !== undefined" class="opacity-40"
            >({{ currentItem }}/{{ totalItems }})</span
          >
        </div>
        <span class="font-medium">{{ Math.round(progress) }}%</span>
      </div>
      <n-progress
        type="line"
        :percentage="Math.round(progress)"
        :height="16"
        :processing="true"
        color="#3b82f6"
      />
      <div v-if="currentItem && totalItems === undefined" class="text-xs opacity-40 truncate">当前: {{ currentItem }}</div>
    </div>
  </n-card>
</template>
