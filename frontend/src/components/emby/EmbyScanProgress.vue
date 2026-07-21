<script setup>
defineProps({
  running: { type: Boolean, default: false },
  progress: { type: Number, default: 0 },
  stepName: { type: String, default: '' },
  currentItem: { type: String, default: '' },
})
</script>

<template>
  <n-card v-if="running" size="small" :bordered="true" class="mb-4">
    <div class="flex flex-col gap-2">
      <div class="flex items-center justify-between text-xs">
        <span class="opacity-70">{{ stepName }}</span>
        <span class="font-medium">{{ Math.round(progress) }}%</span>
      </div>
      <n-progress
        type="line"
        :percentage="Math.round(progress)"
        :height="18"
        :processing="running"
        color="#3b82f6"
      />
      <div v-if="currentItem" class="text-xs opacity-40 truncate">
        当前: {{ currentItem }}
      </div>
    </div>
  </n-card>
</template>
