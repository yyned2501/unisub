<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: '' },
  type: {
    type: String,
    default: 'general',
    validator: (v) => ['nf', 'sub', 'general'].includes(v),
  },
})

const NF_STATUS_MAP = {
  active: { label: '活跃', type: 'primary' },
  missing_fill: { label: '缺集', type: 'warning' },
  completed: { label: '已完成', type: 'success' },
}

const SUB_STATUS_MAP = {
  subscribed: { label: '已订阅', type: 'success' },
  unsubscribed: { label: '未订阅', type: 'default' },
  completed: { label: '已完成', type: 'success' },
}

const GENERAL_STATUS_MAP = {
  connected: { label: '已连接', type: 'success' },
  disconnected: { label: '未连接', type: 'error' },
  enabled: { label: '已启用', type: 'success' },
  disabled: { label: '已禁用', type: 'default' },
}

const map = computed(() => {
  if (props.type === 'nf') return NF_STATUS_MAP
  if (props.type === 'sub') return SUB_STATUS_MAP
  return GENERAL_STATUS_MAP
})

const tagInfo = computed(() => {
  const info = map.value[props.status]
  return info || { label: props.status || '未知', type: 'default' }
})
</script>

<template>
  <n-tag :type="tagInfo.type" size="small" round>
    {{ tagInfo.label }}
  </n-tag>
</template>
