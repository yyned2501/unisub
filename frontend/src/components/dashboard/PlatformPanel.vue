<script setup lang="ts">
import { computed } from 'vue'
import type { PlatformStatus } from '@/types'

const props = defineProps<{
  platforms: PlatformStatus[]
  nfQuota: Record<string, string> | null
  loading: boolean
}>()

const emit = defineEmits<{
  refresh: []
}>()

const PLATFORM_LABELS: Record<string, string> = {
  nextfind: 'NextFind',
  moviepilot: 'MoviePilot',
  emby: 'Emby',
  tmdb: 'TMDB',
}

/** NextFind 有效额度列表（过滤掉"未开启"的空条目） */
const nfQuotaList = computed(() => {
  if (!props.nfQuota) return []
  return Object.values(props.nfQuota).filter((v) => v && v !== '未开启')
})
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
          <div class="min-w-0 flex-1 mr-3">
            <div class="text-sm font-medium">{{ PLATFORM_LABELS[p.name] || p.name }}</div>
            <div class="text-xs opacity-50 font-mono truncate">{{ p.message }}</div>
          </div>
          <div class="flex items-center gap-3 shrink-0">
            <div v-if="p.name === 'nextfind' && nfQuotaList.length" class="text-xs opacity-60 text-right leading-relaxed">
              <div v-for="(item, idx) in nfQuotaList" :key="idx">{{ item }}</div>
            </div>
            <n-tag :type="!p.enabled ? 'default' : p.connected ? 'success' : 'error'" size="tiny" round>
              {{ !p.enabled ? '未启用' : p.connected ? '已连接' : '连接失败' }}
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
