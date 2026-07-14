<script setup>
defineProps({
  platform: { type: Object, required: true },
  connected: { type: Boolean, default: false },
  quota: { type: [Number, String], default: null },
})
</script>

<template>
  <div class="flex flex-col items-end gap-0.5">
    <n-tag :type="connected ? 'success' : 'error'" size="tiny" round>
      {{ connected ? '已连接' : '未连接' }}
    </n-tag>
    <div v-if="platform.name === 'nextfind' && quota !== null" class="text-xs opacity-50">
      剩余 <strong class="opacity-100">{{ quota }}</strong>
    </div>
  </div>
</template>
