<template>
  <el-tag
    :type="tagType"
    :effect="effect"
    size="small"
    :class="['status-badge', `status-badge--${type}`]"
  >
    {{ label }}
  </el-tag>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** 状态值 */
  status: {
    type: String,
    default: '',
  },
  /** 标签类型: nf（NextFind状态）、sub（订阅状态）、general（通用） */
  type: {
    type: String,
    default: 'general',
    validator: (v) => ['nf', 'sub', 'general'].includes(v),
  },
  /** 效果 */
  effect: {
    type: String,
    default: 'light',
  },
})

/** NF 状态映射 */
const NF_STATUS_MAP = {
  active: { label: '活跃', type: '' },
  missing_fill: { label: '缺集', type: 'warning' },
  completed: { label: '已完成', type: 'success' },
}

/** 订阅状态映射 */
const SUB_STATUS_MAP = {
  subscribed: { label: '已订阅', type: 'success' },
  unsubscribed: { label: '未订阅', type: 'info' },
  completed: { label: '已完成', type: 'success' },
}

/** 通用状态映射 */
const GENERAL_STATUS_MAP = {
  connected: { label: '已连接', type: 'success' },
  disconnected: { label: '未连接', type: 'danger' },
  enabled: { label: '已启用', type: 'success' },
  disabled: { label: '已禁用', type: 'info' },
}

const label = computed(() => {
  if (props.type === 'nf') {
    return NF_STATUS_MAP[props.status]?.label || props.status || '未知'
  }
  if (props.type === 'sub') {
    return SUB_STATUS_MAP[props.status]?.label || props.status || '未知'
  }
  return GENERAL_STATUS_MAP[props.status]?.label || props.status || '未知'
})

const tagType = computed(() => {
  if (props.type === 'nf') {
    return NF_STATUS_MAP[props.status]?.type || 'info'
  }
  if (props.type === 'sub') {
    return SUB_STATUS_MAP[props.status]?.type || 'info'
  }
  return GENERAL_STATUS_MAP[props.status]?.type || 'info'
})
</script>

<style scoped>
.status-badge {
  text-transform: none;
}
</style>
