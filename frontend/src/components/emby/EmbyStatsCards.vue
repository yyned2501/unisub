<script setup>
defineProps({
  analysis: { type: Object, required: true },
})

const hiddenCount = (analysis) => analysis.series.filter(s => s.is_blacklisted).length

const cards = [
  { key: 'total_series', label: 'Emby 剧集总数', icon: 'ri-tv-2-line', bg: 'rgba(59,130,246,0.12)', color: 'rgb(96,165,250)' },
  { key: 'subscribed_count', label: '已订阅', icon: 'ri-rss-line', bg: 'rgba(34,197,94,0.12)', color: 'rgb(74,222,128)' },
  { key: 'missing_count', label: '缺集', icon: 'ri-error-warning-line', bg: 'rgba(251,146,60,0.12)', color: 'rgb(251,146,60)' },
]
</script>

<template>
  <div class="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-4">
    <n-card v-for="c in cards" :key="c.key" size="small" :bordered="true">
      <div class="flex items-center gap-3">
        <div class="flex items-center justify-center w-10 h-10 rounded-lg shrink-0" :style="{ background: c.bg }">
          <i :class="c.icon" class="text-lg" :style="{ color: c.color }"></i>
        </div>
        <div>
          <div class="text-xs opacity-50">{{ c.label }}</div>
          <div class="text-xl font-bold">{{ analysis[c.key] }}</div>
        </div>
      </div>
    </n-card>
    <n-card size="small" :bordered="true">
      <div class="flex items-center gap-3">
        <div class="flex items-center justify-center w-10 h-10 rounded-lg shrink-0" style="background: rgba(239,68,68,0.12);">
          <i class="ri-eye-off-line text-lg" style="color: rgb(248,113,113);"></i>
        </div>
        <div>
          <div class="text-xs opacity-50">已隐藏</div>
          <div class="text-xl font-bold">{{ hiddenCount(analysis) }}</div>
        </div>
      </div>
    </n-card>
  </div>
</template>
