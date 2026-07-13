<template>
  <div class="platform-status">
    <div class="status-row">
      <span
        class="status-dot"
        :class="connected ? 'status-dot--connected' : 'status-dot--disconnected'"
      ></span>
      <span class="status-label">{{ connected ? '已连接' : '未连接' }}</span>
    </div>
    <div v-if="platform.name === 'nextfind' && quota !== null" class="quota-info">
      <span class="quota-label">剩余额度：</span>
      <span class="quota-value">{{ quota }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  platform: {
    type: Object,
    required: true,
  },
  connected: {
    type: Boolean,
    default: false,
  },
  quota: {
    type: [Number, String],
    default: null,
  },
})
</script>

<style scoped>
.platform-status {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}

.status-dot--connected {
  background-color: #67c23a;
  box-shadow: 0 0 4px rgba(103, 194, 58, 0.5);
}

.status-dot--disconnected {
  background-color: #f56c6c;
  box-shadow: 0 0 4px rgba(245, 108, 108, 0.5);
}

.status-label {
  font-size: 13px;
  color: #606266;
}

.quota-info {
  font-size: 12px;
  color: #909399;
}

.quota-value {
  font-weight: 600;
  color: #409eff;
}
</style>
