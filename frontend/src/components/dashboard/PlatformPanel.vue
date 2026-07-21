<script setup lang="ts">
import type { PlatformStatus } from '@/types'

defineProps<{
  platforms: PlatformStatus[]
  nfQuota: number | string | null
  loading: boolean
}>()

const emit = defineEmits<{
  refresh: []
}>()
</script>

<template>
  <n-card title="平台状态" :bordered="true" size="small">
    <template #header-extra>
      <n-button secondary size="tiny" :loading="loading" @click="emit('refresh')">
        <template #icon><i class="ri-refresh-line"></i></template>
        刷新
      </n-button>
    </template>

    <n-spin :show="loading">
      <template v-if="platforms.length > 0">
        <div
          v-for="p in platforms"
          :key="p.name"
          class="flex items-center justify-between py-2.5 border-b last:border-b-0 border-[var(--n-border-color)]"
        >
          <div>
            <div class="text-sm font-medium capitalize">{{ p.name === 'nextfind' ? 'NextFind' : 'MoviePilot' }}</div>
            <div class="text-xs opacity-50 font-mono">{{ p.message }}</div>
          </div>
          <div class="flex items-center gap-3">
            <span v-if="p.name === 'nextfind' && nfQuota !== null" class="text-xs opacity-60">
              剩余 <strong class="opacity-100">{{ nfQuota }}</strong>
            </span>
            <n-tag :type="p.enabled ? 'success' : 'error'" size="tiny" round>
              {{ p.enabled ? '已连接' : '未连接' }}
            </n-tag>
          </div>
        </div>
      </template>
      <n-empty v-else description="暂无平台配置" size="small">
        <template #extra>
          <router-link to="/settings"><n-button size="tiny">去设置</n-button></router-link>
        </template>
      </n-empty>
    </n-spin>
  </n-card>
</template>
