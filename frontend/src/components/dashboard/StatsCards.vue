<script setup lang="ts">
defineProps<{
  totalSubscriptions: number
  missingCount: number
  completedCount: number
  tmdbCachedTotal: number
  tmdbDataFilled: number
}>()
</script>

<template>
  <div class="grid grid-cols-4 gap-4 mb-5">
    <n-card :bordered="true" size="small">
      <div class="flex items-center gap-4">
        <div
          class="flex items-center justify-center w-12 h-12 rounded-xl"
          style="background: rgba(59, 130, 246, 0.15); color: rgb(59, 130, 246)"
        >
          <i class="ri-film-line text-xl"></i>
        </div>
        <div>
          <div class="text-3xl font-bold leading-none">{{ totalSubscriptions }}</div>
          <div class="text-xs mt-1 opacity-50">总订阅数</div>
        </div>
      </div>
    </n-card>
    <n-card :bordered="true" size="small">
      <div class="flex items-center gap-4">
        <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-amber/15 text-amber">
          <i class="ri-error-warning-line text-xl"></i>
        </div>
        <div>
          <div class="text-3xl font-bold leading-none">{{ missingCount }}</div>
          <div class="text-xs mt-1 opacity-50">缺集数</div>
        </div>
      </div>
    </n-card>
    <n-card :bordered="true" size="small">
      <div class="flex items-center gap-4">
        <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-emerald/15 text-emerald">
          <i class="ri-check-double-line text-xl"></i>
        </div>
        <div>
          <div class="text-3xl font-bold leading-none">{{ completedCount }}</div>
          <div class="text-xs mt-1 opacity-50">已完成数</div>
        </div>
      </div>
    </n-card>
    <n-card :bordered="true" size="small">
      <div class="flex items-center gap-4">
        <div
          class="flex items-center justify-center w-12 h-12 rounded-xl"
          style="background: rgba(99, 102, 241, 0.15); color: rgb(99, 102, 241)"
        >
          <i class="ri-database-2-line text-xl"></i>
        </div>
        <div>
          <div class="text-3xl font-bold leading-none">
            {{ tmdbCachedTotal > 0 ? Math.round((tmdbDataFilled / tmdbCachedTotal) * 100) + '%' : '-' }}
          </div>
          <div class="text-xs mt-1 opacity-50">TMDB 覆盖 {{ tmdbDataFilled }}/{{ tmdbCachedTotal }}</div>
        </div>
      </div>
    </n-card>
  </div>
</template>
