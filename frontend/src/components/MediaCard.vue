<script setup lang="ts">
import type { SearchResultItem } from '@/types'

defineProps<{
  media: SearchResultItem
  subscribed: boolean
}>()

defineEmits<{
  click: [media: SearchResultItem]
  subscribe: [media: SearchResultItem]
}>()

function onImgError(e: Event) {
  const img = e.target as HTMLImageElement
  img.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="200" height="300"><rect fill="%2327272a" width="200" height="300"/><text fill="%236b7280" font-size="30" x="50%" y="50%" text-anchor="middle" dy=".3em">?</text></svg>'
}
</script>

<template>
  <div class="media-card" @click="$emit('click', media)">
    <div class="relative w-full pb-[150%] rounded-lg overflow-hidden" style="background: var(--n-border-color);">
      <img :src="media.poster_url || ''" class="absolute inset-0 w-full h-full object-cover transition-transform duration-300" :alt="media.title" @error="onImgError" />
      <n-tag :type="media.media_type === 'tv' ? 'primary' : 'success'" size="tiny" class="!absolute top-1.5 left-1.5" round>
        {{ media.media_type === 'tv' ? '剧集' : '电影' }}
      </n-tag>
      <div v-if="subscribed" class="absolute bottom-1.5 left-1.5 w-7 h-7 rounded-full bg-black/50 flex items-center justify-center">
        <i class="ri-rss-fill text-sm" style="color: rgb(96,165,250);"></i>
      </div>
    </div>
    <div class="px-0.5 pt-1.5 text-center">
      <h4 class="text-xs truncate font-medium">{{ media.title }}</h4>
      <div class="flex items-center justify-between">
        <span class="text-xs opacity-40">{{ media.year || '未知年份' }}</span>
        <n-button v-if="!subscribed" size="tiny" secondary type="primary" @click.stop="$emit('subscribe', media)">订阅</n-button>
        <n-tag v-else size="tiny" type="default" round class="opacity-50">已订阅</n-tag>
      </div>
    </div>
  </div>
</template>

<style scoped>
.media-card {
  border-radius: 12px;
  padding: 3px;
  cursor: pointer;
  transition: background 0.2s;
}
.media-card:hover {
  background: var(--n-action-color);
}
</style>
